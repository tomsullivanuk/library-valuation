import csv
import html as html_lib
import hashlib
import io
import json
import re
import shutil
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path

import pytest

from valuation.libib_catalog import StrictCatalogRepository, reconcile_inventory_catalog
from valuation.libib_inventory import import_libib_inventory
from valuation.repositories import ACQUISITION_FIELDNAMES, CATALOG_ITEMS_FIELDNAMES
from valuation.steward_presentation import (
    PRESENTATION_MODEL_VERSION,
    RegisteredReport,
    RecommendationView,
    StewardPresentationError,
    build_steward_presentation,
)
from valuation.steward_workspace import (
    ExploreQuery,
    StewardWorkspaceRenderError,
    build_recommendation_queues,
    build_report_groups,
    query_explore,
    render_steward_workspace,
)

LIBIB_FIXTURE = Path(__file__).parent / "fixtures" / "libib" / "study_export.csv"
NOW = datetime(2026, 7, 23, 12, 0, tzinfo=timezone.utc)


def blank_row(fieldnames, **values):
    row = {field: "" for field in fieldnames}
    row.update(values)
    return row


def catalog_row(catalog_id="BK000001", **values):
    row = blank_row(
        CATALOG_ITEMS_FIELDNAMES,
        catalog_item_id=catalog_id,
        isbn13="9780306406157",
        isbn10="0306406152",
        title="Example Physics",
        author="Marie Curie",
        publisher="Example Press",
        publication_year="1980",
        match_confidence="high",
    )
    row.update(values)
    return row


def write_catalog(data_dir: Path, rows):
    path = data_dir / "catalog_items.csv"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(StrictCatalogRepository(path).rendered_bytes(list(rows)))


def write_csv(path: Path, fieldnames, rows):
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def model_for(tmp_path: Path, rows):
    data_dir = tmp_path / "data"
    write_catalog(data_dir, rows)
    return build_steward_presentation(data_dir=data_dir)


def model_with_inventory(tmp_path: Path):
    libib_root = tmp_path / "input" / "libib"
    source = libib_root / "study" / "library.csv"
    source.parent.mkdir(parents=True)
    shutil.copyfile(LIBIB_FIXTURE, source)
    data_dir = tmp_path / "data"
    import_libib_inventory(
        source,
        data_dir=data_dir,
        libib_input_dir=libib_root,
        audit_scope="Study",
        audit_completeness="partial_scope",
        now=lambda: NOW,
    )
    write_catalog(data_dir, [])
    write_csv(data_dir / "acquisitions.csv", ACQUISITION_FIELDNAMES, [])
    reconcile_inventory_catalog(data_dir=data_dir, now=lambda: NOW)
    return build_steward_presentation(data_dir=data_dir)


def test_html_is_deterministic_self_contained_and_script_safe(tmp_path):
    model = model_for(
        tmp_path,
        [catalog_row(title="A </script><script>PRIVATE</script> Book")],
    )

    first = render_steward_workspace(model)
    second = render_steward_workspace(model)

    assert first == second
    assert b"</script><script>PRIVATE" not in first
    assert b"\\u003c/script\\u003e" in first
    assert b"https://" not in first
    assert b"http://127.0.0.1:8765" in first
    assert b'fetch("/api/state"' in first
    assert b"localStorage" not in first
    assert b"sessionStorage" not in first


def test_catalog_only_workspace_opens_on_library_with_read_only_primary_navigation(tmp_path):
    html = render_steward_workspace(model_for(tmp_path, [catalog_row()])).decode()

    assert 'href="#library" data-nav="library">Library</a>' in html
    assert 'aria-disabled="true" title="Import remains' in html
    assert 'href="#settings" data-nav="settings"' in html
    assert 'data-nav="recommendations"' not in html
    assert 'data-nav="reports"' in html
    assert 'data-nav="actions"' in html
    assert 'node("label", {for: "library-search"}, "Search")' in html
    assert "Export filtered CSV" in html
    assert 'grid-template-columns: 1fr;' in html
    assert "Show next 250" not in html
    assert "visibleLimit" not in html
    assert "RESULT_LIMIT" not in html
    assert "knownLocations" in html
    assert '"Not Located"' in html
    assert '"Acquired"' in html
    assert "offline view" in html
    assert "Open the local workspace to save" in html
    assert "localStorage" not in html
    assert "sessionStorage" not in html
    assert "Save disposition" in html
    assert "Export filtered XLSX" not in html
    assert "URL.createObjectURL" in html
    assert 'node("h1", {}, "Library")' not in html
    assert 'class: "search-row"' in html
    assert 'class: "filter-row"' in html
    assert html.index('class: "search-row"') < html.index('class: "filter-row"')
    assert 'class: "sort-menu"' in html
    assert 'libraryState.sort === value' in html
    assert 'libraryState.sortDirection' in html
    assert "renderBookTable" not in html
    assert 'Library view' not in html
    assert '"Estimate available"' in html
    assert '"No reliable estimate"' in html
    assert '"Not researched"' in html
    assert '"cover_url"' not in html
    assert "cover-placeholder" not in html
    card_renderer = html.split("function bookCard(book)", 1)[1].split(
        "function csvCell", 1
    )[0]
    assert '"book-title-link"' in card_renderer
    assert '"View details"' not in card_renderer


def test_estimated_value_sort_uses_direction_specific_presented_endpoints(tmp_path):
    html = render_steward_workspace(model_for(tmp_path, [catalog_row()])).decode()

    assert 'const leftLow = Number(leftLowRaw);' in html
    assert 'const leftHigh = Number(leftHighRaw);' in html
    assert 'const rightLow = Number(rightLowRaw);' in html
    assert 'const rightHigh = Number(rightHighRaw);' in html
    assert 'const valueOrder = direction === 1' in html
    assert '? (leftLow - rightLow) || (leftHigh - rightHigh)' in html
    assert ': (rightHigh - leftHigh) || (rightLow - leftLow);' in html
    assert 'return valueOrder' in html
    assert 'if (leftHasValue !== rightHasValue) return leftHasValue ? -1 : 1;' in html
    assert 'left.title.localeCompare(right.title)' in html
    assert 'left.catalog_item_id.localeCompare(right.catalog_item_id)' in html
    assert 'Number(left.estimated_value)' not in html

    records = [
        ("2", "9", "Two to Nine", "cat-5"),
        ("1.94", "1.94", "Single 1.94", "cat-4"),
        ("1", "5", "One to Five", "cat-3"),
        ("1", "1", "One to One B", "cat-2"),
        ("1", "1", "One to One A", "cat-1"),
        ("12", "20", "Twelve to Twenty", "cat-6"),
        ("20", "100", "Twenty to One Hundred", "cat-7"),
        ("187", "553", "Range 187 to 553", "cat-8"),
        ("186", "224", "Range 186 to 224", "cat-9"),
        ("183", "247", "Range 183 to 247", "cat-10"),
        ("178", "247", "Range 178 to 247", "cat-11"),
        ("176", "176", "Single 176", "cat-12"),
        ("162", "239", "Range 162 to 239", "cat-13"),
        ("162", "224", "Range 162 to 224", "cat-14"),
        ("162", "173", "Range 162 to 173", "cat-15"),
        ("", "", "Missing B", "cat-17"),
        ("", "", "Missing A", "cat-16"),
    ]

    def ordered(*, descending: bool) -> list[tuple[str, str, str, str]]:
        valued = sorted(
            (record for record in records if record[0]),
            key=(
                (lambda record: (-float(record[1]), -float(record[0]), record[2], record[3]))
                if descending
                else (lambda record: (float(record[0]), float(record[1]), record[2], record[3]))
            ),
        )
        missing = sorted(
            (record for record in records if not record[0]),
            key=lambda record: (record[2], record[3]),
        )
        return [*valued, *missing]

    ascending = ordered(descending=False)
    descending = ordered(descending=True)
    assert ascending.index(next(row for row in records if row[2] == "Range 183 to 247")) < (
        ascending.index(next(row for row in records if row[2] == "Range 186 to 224"))
    )
    assert descending.index(next(row for row in records if row[2] == "Range 183 to 247")) < (
        descending.index(next(row for row in records if row[2] == "Range 186 to 224"))
    )
    assert [row[1] for row in ascending if row[0] == "162"] == ["173", "224", "239"]
    assert [row[1] for row in descending if row[0] == "162"] == ["239", "224", "173"]
    assert ascending.index(next(row for row in records if row[2] == "Single 1.94")) < (
        ascending.index(next(row for row in records if row[2] == "Two to Nine"))
    )
    assert descending[:-2] != list(reversed(ascending[:-2]))
    assert [record[3] for record in ascending[:2]] == ["cat-1", "cat-2"]
    assert [record[3] for record in ascending[-2:]] == ["cat-16", "cat-17"]
    assert [record[3] for record in descending[-2:]] == ["cat-16", "cat-17"]


def test_card_and_filtered_csv_use_distinct_display_and_precise_fields(tmp_path):
    html = render_steward_workspace(model_for(tmp_path, [catalog_row()])).decode()

    card_renderer = html.split("function bookCard(book)", 1)[1].split(
        "function csvCell", 1
    )[0]
    export_renderer = html.split("function filteredCsvText(books)", 1)[1].split(
        "function renderBook", 1
    )[0]
    assert "book.resale_market_card_summary" in card_renderer
    assert '["Estimate Low", "estimated_value_precise_low"]' in export_renderer
    assert '["Estimate High", "estimated_value_precise_high"]' in export_renderer
    assert '["Currency", "estimated_value_currency"]' in export_renderer
    assert '["Resale Market Display", "estimated_value_display"]' in export_renderer
    assert '["Resale market", "resale_market_summary"]' not in export_renderer
    assert "for (const book of books)" in export_renderer
    assert "filteredCsvText(libraryState.visibleBooks)" in export_renderer


def test_filtered_csv_contract_preserves_precise_intervals_and_blank_missing_values(
    tmp_path,
):
    model = model_for(
        tmp_path,
        [catalog_row("BK000001"), catalog_row("BK000002", isbn13="", isbn10="")],
    )
    books = (
        replace(
            model.books[0],
            acquisition_source="Amazon",
            acquisition_month="2021-02",
            acquisition_count=1,
            estimated_value_precise_low="187.09",
            estimated_value_precise_high="552.93",
            estimated_value_currency="USD",
            estimated_value_display="$187–$553",
        ),
        replace(
            model.books[1],
            estimated_value_precise_low="",
            estimated_value_precise_high="",
            estimated_value_currency="",
            estimated_value_display="",
        ),
    )
    html = render_steward_workspace(replace(model, books=books)).decode()
    data_match = re.search(
        r'<script id="workspace-data" type="application/json">(.*?)</script>',
        html,
        re.DOTALL,
    )
    columns_match = re.search(r"const columns = (\[.*?\]);", html)
    assert data_match and columns_match
    rendered_books = json.loads(html_lib.unescape(data_match.group(1)))["books"]
    columns = json.loads(columns_match.group(1))

    stream = io.StringIO(newline="")
    writer = csv.writer(stream, lineterminator="\r\n", quoting=csv.QUOTE_ALL)
    writer.writerow([label for label, _ in columns])
    writer.writerows(
        [[book.get(key, "") for _, key in columns] for book in rendered_books]
    )
    rows = list(csv.DictReader(io.StringIO(stream.getvalue(), newline="")))

    assert list(rows[0]) == [
        "Catalog ID",
        "Title",
        "Author",
        "ISBN-13",
            "Publisher",
            "Location",
            "Acquisition Source",
            "Acquisition Month",
            "Acquisition Count",
            "Estimate Low",
        "Estimate High",
        "Currency",
        "Resale Market Display",
        "Disposition",
    ]
    assert {
        key: rows[0][key]
        for key in (
            "Acquisition Source",
            "Acquisition Month",
            "Acquisition Count",
            "Estimate Low",
            "Estimate High",
            "Currency",
            "Resale Market Display",
        )
    } == {
        "Acquisition Source": "Amazon",
        "Acquisition Month": "2021-02",
        "Acquisition Count": "1",
        "Estimate Low": "187.09",
        "Estimate High": "552.93",
        "Currency": "USD",
        "Resale Market Display": "$187–$553",
    }
    assert all(
        rows[1][key] == ""
        for key in (
            "Acquisition Source",
            "Acquisition Month",
            "Estimate Low",
            "Estimate High",
            "Currency",
            "Resale Market Display",
        )
    )
    assert rows[1]["Acquisition Count"] == "0"
    assert "Resale market" not in rows[0]
    assert "Acquired" not in rows[0]


def test_registered_reports_are_grouped_by_declared_steward_purpose(tmp_path):
    data_dir = tmp_path / "data"
    write_catalog(data_dir, [catalog_row()])
    catalog_hash = hashlib.sha256((data_dir / "catalog_items.csv").read_bytes()).hexdigest()
    report_dir = tmp_path / "generated"
    report_dir.mkdir()
    inventory = report_dir / "inventory.xlsx"
    research = report_dir / "research.pdf"
    inventory.write_bytes(b"inventory report")
    research.write_bytes(b"research report")
    model = build_steward_presentation(
        data_dir=data_dir,
        reports=(
            RegisteredReport(
                "inventory_review",
                "Inventory Review",
                "Review audit and holding questions",
                "Steward",
                "xlsx",
                inventory,
                "reports/inventory.xlsx",
                "inventory-workflow",
                catalog_hash,
                "2026-07-25T12:00:00Z",
                "Covers the latest accepted audit only.",
            ),
            RegisteredReport(
                "collection_research",
                "Collection Research",
                "Review bibliographic research",
                "Steward",
                "pdf",
                research,
                "reports/research.pdf",
                "research-workflow",
                catalog_hash,
            ),
        ),
    )

    groups = build_report_groups(model)

    assert tuple(group.category_key for group in groups) == (
        "inventory_audit",
        "catalog_research",
    )
    assert all(row.status == "current" for group in groups for row in group.reports)
    assert groups[0].reports[0].limitations == "Covers the latest accepted audit only."
    assert groups[0].reports[0].can_open


def test_report_states_distinguish_current_stale_missing_incompatible_and_unavailable(
    tmp_path,
):
    data_dir = tmp_path / "data"
    write_catalog(data_dir, [catalog_row()])
    catalog_hash = hashlib.sha256((data_dir / "catalog_items.csv").read_bytes()).hexdigest()
    current = tmp_path / "current.xlsx"
    stale = tmp_path / "stale.xlsx"
    incompatible = tmp_path / "wrong.csv"
    current.write_bytes(b"current")
    stale.write_bytes(b"stale")
    incompatible.write_bytes(b"incompatible")
    reports = (
        RegisteredReport("current", "Current", "Steward review", "Steward", "xlsx", current, "current.xlsx", "review", catalog_hash),
        RegisteredReport("stale", "Stale", "Steward review", "Steward", "xlsx", stale, "stale.xlsx", "review", "old-hash"),
        RegisteredReport("missing", "Missing", "Steward review", "Steward", "xlsx", tmp_path / "missing.xlsx", "missing.xlsx", "review", catalog_hash),
        RegisteredReport("incompatible", "Incompatible", "Steward review", "Steward", "xlsx", incompatible, "wrong.xlsx", "review", catalog_hash),
    )

    model = build_steward_presentation(data_dir=data_dir, reports=reports)
    statuses = {row.report_key: row.status for row in model.reports}
    grouped = {
        row.report_key: row
        for group in build_report_groups(model)
        for row in group.reports
    }

    assert statuses == {
        "current": "current",
        "stale": "stale",
        "missing": "missing",
        "incompatible": "incompatible",
    }
    assert grouped["current"].can_open
    assert grouped["stale"].can_open
    assert not grouped["missing"].can_open
    assert not grouped["incompatible"].can_open
    assert tuple(
        row.report_key for row in build_report_groups(model)[0].reports
    ) == ("current", "stale", "missing", "incompatible")
    assert not build_report_groups(model_for(tmp_path / "catalog-only", [catalog_row()]))


@pytest.mark.parametrize(
    "public_path",
    (
        "../private.xlsx",
        "/absolute.xlsx",
        ".",
        "https:report.xlsx",
        "report.xlsx?private=1",
        "report.xlsx#fragment",
        "reports\\report.xlsx",
        "%2e%2e/private.xlsx",
        " //example.invalid/report.xlsx",
    ),
)
def test_report_public_paths_fail_closed_when_not_safe(tmp_path, public_path):
    data_dir = tmp_path / "data"
    write_catalog(data_dir, [catalog_row()])
    report = tmp_path / "report.xlsx"
    report.write_bytes(b"report")

    with pytest.raises(StewardPresentationError, match="safe and relative"):
        build_steward_presentation(
            data_dir=data_dir,
            reports=(
                RegisteredReport(
                    "unsafe",
                    "Unsafe",
                    "Review",
                    "Steward",
                    "xlsx",
                    report,
                    public_path,
                    "test",
                ),
            ),
        )


def test_report_rendering_is_deterministic_script_safe_and_links_only_safe_artifacts(
    tmp_path,
):
    data_dir = tmp_path / "data"
    write_catalog(data_dir, [catalog_row()])
    catalog_hash = hashlib.sha256((data_dir / "catalog_items.csv").read_bytes()).hexdigest()
    report = tmp_path / "report.xlsx"
    report.write_bytes(b"report")
    model = build_steward_presentation(
        data_dir=data_dir,
        reports=(
            RegisteredReport(
                "review",
                "Steward Review",
                "Review </script><script>PRIVATE</script> questions",
                "Steward",
                "xlsx",
                report,
                "reports/review.xlsx",
                "review-workflow",
                catalog_hash,
                limitations="Does not record decisions.",
            ),
        ),
    )

    first = render_steward_workspace(model)
    second = render_steward_workspace(model)

    assert first == second
    assert b"</script><script>PRIVATE" not in first
    assert b"\\u003c/script\\u003e" in first
    assert b"reports/review.xlsx" in first
    assert b"Open report" in first
    assert b"Download a copy" in first
    assert b"source_path" not in first
    assert 'route === "report"' in first.decode()


def test_duplicate_report_registration_is_rejected_before_rendering(tmp_path):
    data_dir = tmp_path / "data"
    write_catalog(data_dir, [catalog_row()])
    report = tmp_path / "report.xlsx"
    report.write_bytes(b"report")
    duplicate = RegisteredReport(
        "same",
        "Same",
        "Review",
        "Steward",
        "xlsx",
        report,
        "report.xlsx",
        "test",
    )

    with pytest.raises(StewardPresentationError, match="unique"):
        build_steward_presentation(data_dir=data_dir, reports=(duplicate, duplicate))


def test_query_searches_allowlisted_book_and_related_identity_fields(tmp_path):
    model = model_for(
        tmp_path,
        [
            catalog_row(),
            catalog_row(
                "BK000002",
                isbn13="9780140449266",
                isbn10="0140449264",
                title="The Odyssey",
                author="Homer",
                publisher="Penguin Classics",
                publication_year="2003",
            ),
        ],
    )

    for term in ("odyssey", "homer", "9780140449266", "penguin", "BK000002"):
        assert query_explore(model, ExploreQuery(search=term)) == ("BK000002",)


def test_inventory_state_renders_holdings_and_reconciliation_deep_links(tmp_path):
    model = model_with_inventory(tmp_path)
    html = render_steward_workspace(model).decode()

    assert model.holdings
    assert model.observations
    assert model.decisions
    assert model.holdings[0].holding_id in html
    assert model.observations[0].inventory_observation_id in html
    assert model.decisions[0].decision_id in html
    assert f'holding/{model.holdings[0].holding_id}' in html
    assert '"Physical copies"' in html
    assert tuple(queue.queue_key for queue in build_recommendation_queues(model)) == (
        "physical_identity",
        "location",
        "newly_discovered",
    )


def recommendation(
    recommendation_id,
    source_kind,
    entity_id="BK000001",
    *,
    entity_type="catalog_item",
    action="Review evidence",
    explanation="Existing evidence requires review.",
    confidence="medium",
    evidence=("catalog:BK000001",),
):
    return RecommendationView(
        recommendation_id=recommendation_id,
        source_kind=source_kind,
        source_reference=entity_id,
        entity_type=entity_type,
        entity_id=entity_id,
        suggested_action=action,
        explanation=explanation,
        confidence=confidence,
        reason_codes=("review_needed",),
        evidence_references=evidence,
    )


def test_recommendations_are_grouped_into_separate_supported_queues(tmp_path):
    model = model_for(tmp_path, [catalog_row()])
    model = replace(
        model,
        recommendations=(
            recommendation("REC-4", "research_candidate"),
            recommendation("REC-2", "market_evidence"),
            recommendation("REC-1", "inventory_newly_discovered"),
            recommendation("REC-3", "steward_priority"),
        ),
    )

    queues = build_recommendation_queues(model)

    assert tuple(queue.queue_key for queue in queues) == (
        "newly_discovered",
        "market_evidence",
        "research",
        "steward_priority",
    )
    assert all(queue.recommendations for queue in queues)


def test_recommendation_order_is_confidence_then_label_then_stable_id(tmp_path):
    model = model_for(
        tmp_path,
        [
            catalog_row(),
            catalog_row(
                "BK000002",
                isbn13="9780140449266",
                isbn10="0140449264",
                title="Alpha",
                author="Homer",
            ),
        ],
    )
    model = replace(
        model,
        recommendations=(
            recommendation("REC-LOW", "market_evidence", confidence="low"),
            recommendation(
                "REC-HIGH-Z",
                "market_evidence",
                action="Z action",
                confidence="high",
            ),
            recommendation(
                "REC-HIGH-A",
                "market_evidence",
                "BK000002",
                confidence="high",
            ),
        ),
    )

    rows = build_recommendation_queues(model)[0].recommendations

    assert tuple(row.recommendation_id for row in rows) == (
        "REC-HIGH-A",
        "REC-HIGH-Z",
        "REC-LOW",
    )


def test_recommendation_reason_evidence_and_explore_links_are_preserved(tmp_path):
    model = model_for(tmp_path, [catalog_row()])
    model = replace(
        model,
        recommendations=(
            recommendation(
                "REC-1",
                "market_evidence",
                explanation="Comparable evidence conflicts.",
                evidence=("catalog:BK000001", "market:BK000001"),
            ),
        ),
    )

    row = build_recommendation_queues(model)[0].recommendations[0]
    html = render_steward_workspace(model).decode()

    assert row.primary_route == "book/BK000001"
    assert ("market:BK000001", "market/market:BK000001") in row.evidence_routes
    assert "Comparable evidence conflicts." in html
    assert "book/BK000001" in html
    assert "market/market:BK000001" in html
    assert 'route === "recommendation"' in html


def test_duplicate_recommendation_ids_are_suppressed_deterministically(tmp_path):
    model = model_for(tmp_path, [catalog_row()])
    duplicate = recommendation("REC-1", "research_candidate")
    model = replace(model, recommendations=(duplicate, duplicate))

    queues = build_recommendation_queues(model)

    assert sum(len(queue.recommendations) for queue in queues) == 1
    assert render_steward_workspace(model) == render_steward_workspace(model)


def test_recommendation_text_is_script_safe_and_uses_only_allowlisted_fields(tmp_path):
    model = model_for(tmp_path, [catalog_row()])
    model = replace(
        model,
        recommendations=(
            recommendation(
                "REC-1",
                "research_candidate",
                explanation="Review </script><script>PRIVATE</script> evidence.",
            ),
        ),
    )

    html = render_steward_workspace(model)

    assert b"</script><script>PRIVATE" not in html
    assert b"\\u003c/script\\u003e" in html
    assert b"raw_evidence" not in html
    assert b"source_path" not in html


def test_query_filters_and_sorts_without_recalculating_domain_status(tmp_path):
    model = model_for(
        tmp_path,
        [
            catalog_row(title="Zulu", author="Alpha", publication_year="2000"),
            catalog_row(
                "BK000002",
                isbn13="9780140449266",
                isbn10="0140449264",
                title="Alpha",
                author="Zulu",
                publication_year="1900",
            ),
        ],
    )

    assert query_explore(model) == ("BK000002", "BK000001")
    assert query_explore(model, ExploreQuery(sort_by="author")) == (
        "BK000001",
        "BK000002",
    )
    assert query_explore(model, ExploreQuery(sort_by="publication_year")) == (
        "BK000002",
        "BK000001",
    )
    assert query_explore(model, ExploreQuery(inventory_status="unavailable")) == (
        "BK000002",
        "BK000001",
    )
    assert query_explore(model, ExploreQuery(inventory_status="verified_present")) == ()


def test_deep_links_preserve_book_holding_and_evidence_entity_distinctions(tmp_path):
    html = render_steward_workspace(model_for(tmp_path, [catalog_row()])).decode()

    for route in (
        "book",
        "holding",
        "acquisition",
        "assessment",
        "review",
        "market",
        "observation",
        "decision",
    ):
        assert f'route === "{route}"' in html
    assert "Catalog item ID" in html
    assert "physical copy" in html
    assert "Acquisition evidence" in html
    assert "Reconciliation decisions" in html


def test_stale_and_incompatible_optional_sources_are_explained(tmp_path):
    model = model_for(tmp_path, [catalog_row()])
    sources = tuple(
        replace(
            source,
            status="stale" if source.source_key == "market_evidence" else source.status,
            explanation=(
                "Evidence was generated for another catalog snapshot."
                if source.source_key == "market_evidence"
                else source.explanation
            ),
        )
        for source in model.snapshot.sources
    )
    model = replace(model, snapshot=replace(model.snapshot, sources=sources))

    html = render_steward_workspace(model).decode()

    assert "About this data" in html
    assert "Evidence was generated for another catalog snapshot." in html
    assert "stale" in html


def test_accessibility_foundations_and_progressive_disclosure_are_present(tmp_path):
    html = render_steward_workspace(model_for(tmp_path, [catalog_row()])).decode()

    assert '<html lang="en">' in html
    assert 'class="skip-link" href="#main-content"' in html
    assert '<nav aria-label="Primary">' in html
    assert '<main id="main-content" tabindex="-1">' in html
    assert '"aria-live": "polite"' in html
    assert 'node("label", {for: "library-search"}, "Search")' in html
    assert 'node("details", {class: "sort-menu"})' in html
    assert '"aria-live": "polite"' in html
    assert 'node("details"' in html
    assert 'node("summary"' in html
    assert "<noscript>" in html


def test_steward_facing_language_hides_internal_statuses_until_detail(tmp_path):
    html = render_steward_workspace(model_for(tmp_path, [catalog_row()])).decode()

    assert "Books in the catalog" in html
    assert "Physical copies recorded" in html
    assert "Purchase records" in html
    assert "Items needing attention" in html
    assert '"Physical copies"' in html
    assert '"Acquired"' in html
    assert '"Market research"' in html
    assert "No acquisition record is linked. The book may have come from another source." in html
    assert "A useful first item from up to three different areas needing attention." in html
    assert "All areas needing attention" in html
    assert "About this report" in html
    assert "Open report" in html
    assert "Download a copy" in html
    assert "Every report shown here was registered and checked for this workspace." in html
    assert 'detailSection("Technical details"' in html
    assert "Some information is not included or may need review." in html
    assert "What information is affected" in html
    assert 'placeholder: "Title, author, ISBN, publisher, or description"' in html
    assert '"aria-label": `Open ${row.name || row.report_key}`' in html


def test_renderer_rejects_an_incompatible_presentation_contract(tmp_path):
    model = model_for(tmp_path, [catalog_row()])
    incompatible = replace(
        model,
        snapshot=replace(model.snapshot, model_version="future_model"),
    )

    with pytest.raises(StewardWorkspaceRenderError, match="Unsupported"):
        render_steward_workspace(incompatible)

    assert model.snapshot.model_version == PRESENTATION_MODEL_VERSION


def test_renderer_has_no_repository_or_durable_write_interface():
    import inspect
    import valuation.steward_workspace as workspace

    source = inspect.getsource(workspace)
    assert "StrictCatalogRepository" not in source
    assert "build_steward_presentation" not in source
    assert "write_bytes" not in source
    assert "open(" not in source


def test_real_catalog_scale_stays_within_static_artifact_budget(tmp_path):
    rows = [
        catalog_row(
            f"BK{index:06d}",
            isbn13=f"978{index:010d}",
            isbn10="",
            title=f"Book {index:04d}",
            author=f"Creator {index % 211:03d}",
            publisher=f"Publisher {index % 37:02d}",
            publication_year=str(1800 + index % 226),
        )
        for index in range(1, 3015)
    ]
    model = model_for(tmp_path, rows)

    artifact = render_steward_workspace(model)

    assert len(model.books) == 3014
    assert len(artifact) < 5_000_000
    assert artifact.count(b'"catalog_item_id":') == 3014


def test_completed_inventory_preserves_history_but_limits_recommendations(tmp_path):
    from valuation.completed_inventory import CompletedInventoryScope
    model = model_for(tmp_path, [catalog_row(), catalog_row('BK000002', title='Historical')])
    historical = RecommendationView(
        recommendation_id='history', source_kind='research_candidate', entity_type='catalog_item',
        entity_id='BK000002', suggested_action='Research', explanation='Old purchase', confidence='low',
        reason_codes=(), evidence_references=(), source_reference='fixture', advisory=True,
    )
    model = replace(model, completed_inventory=CompletedInventoryScope(
        completed=True, source_entries=1, source_copies=2, catalog_item_ids=('BK000001',)),
        recommendations=(historical,))
    assert len(model.books) == 2
    assert query_explore(model) == ('BK000001',)
    assert query_explore(model, ExploreQuery(collection_scope='history')) == ('BK000002',)
    assert len(query_explore(model, ExploreQuery(collection_scope='all'))) == 2
    assert not any(q.recommendations for q in build_recommendation_queues(model))
    html = render_steward_workspace(model).decode()
    assert 'Physically inventoried books' in html
    assert 'Historical records' in html
    assert 'completedInventory.completed ? "present"' in html
    assert '"Historical"' in html
    assert 'purchase history is preserved' in html


def test_everyday_workspace_details_and_actions_are_direct_and_script_safe(tmp_path):
    model=model_for(tmp_path,[catalog_row()])
    html=render_steward_workspace(model,action_items=[dict(id='a',title='</script><script>bad</script>')]).decode()
    assert '</script><script>bad' not in html
    book=html.split('function renderBook(',1)[1].split('function renderHolding(',1)[0]
    assert 'Steward context' not in book
    assert 'detailSection("Evidence"' not in book
    assert 'Technical provenance' not in book
    assert 'dispositionEditor(book)' in book
    assert '"Acquisition history"' in book and 'a.item_price' in book
    assert 'book.isbn13 || book.isbn10' in html
    assert 'acquisition-filter' not in html
    assert 'physically inventoried entries still need identification' not in html
    assert '"Complete"' in html and '"Dismiss"' in html and '"Defer"' in html


def test_library_result_count_labels_catalog_records(tmp_path):
    html = render_steward_workspace(model_for(tmp_path, [catalog_row()])).decode()
    assert '${books.length === 1 ? "catalog record" : "catalog records"}' in html
    assert '${books.length === 1 ? "book" : "books"}' not in html


def test_library_search_finds_description_text(tmp_path):
    model = model_for(tmp_path, [catalog_row()])
    model = replace(model, books=(replace(model.books[0], description="A study of elusive neutrinos"),))
    assert query_explore(model, ExploreQuery(search="ELUSIVE NEUTRINOS")) == ("BK000001",)
    assert query_explore(model, ExploreQuery(search="unmentioned phrase")) == ()
    html = render_steward_workspace(model).decode()
    search_client = html.split("const searchable = [", 1)[1].split("];", 1)[0]
    assert "book.description" in search_client
    assert "Title, author, ISBN, publisher, or description" in html
    assert "publisher, or ID" not in html
    assert "Your library workspace" not in html
    assert 'class: "clear-filters"' in html

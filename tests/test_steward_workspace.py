import csv
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
    build_steward_presentation,
)
from valuation.steward_workspace import (
    ExploreQuery,
    StewardWorkspaceRenderError,
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
    assert b"http://" not in first
    assert b"fetch(" not in first
    assert b"localStorage" not in first
    assert b"sessionStorage" not in first


def test_catalog_only_workspace_has_task_home_explore_and_honest_placeholders(tmp_path):
    html = render_steward_workspace(model_for(tmp_path, [catalog_row()])).decode()

    assert "What would you like to accomplish today?" in html
    assert 'href="#explore"' in html
    assert 'href="#recommendations"' in html
    assert 'href="#reports"' in html
    assert "reserved for PR4" in html
    assert "reserved for PR5" in html
    assert "unavailable" in html
    assert "Read-only" in html
    assert "does not save" in html
    assert "decisions or modify the catalog" in html


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
    assert f'holding/{model.holdings[0].holding_id}' not in html  # links are built at runtime
    assert "`holding/${encodeURIComponent(id)}`" in html


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
    assert "Physical holding" in html
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
    assert 'node("label", {for: "explore-search"}, "Search")' in html
    assert 'node("details"' in html
    assert 'node("summary"' in html
    assert "<noscript>" in html


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

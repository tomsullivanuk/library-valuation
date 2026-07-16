import csv

from library_pipeline import main
from valuation.abebooks_review_report import render_report, write_abebooks_review_report


def evidence_row(catalog_item_id, title, recommendation, **overrides):
    row = {
        "catalog_item_id": catalog_item_id,
        "isbn_13": "9780000000002",
        "title": title,
        "author": "A & B <Authors>",
        "listing_count": "3",
        "best_match_confidence": "high",
        "outlier_sensitivity": "low_outlier_sensitivity",
        "market_confidence": "moderate_confidence_market_evidence",
        "likely_low": "50",
        "likely_mid": "75.5",
        "likely_high": "100",
        "review_recommendation": recommendation,
        "review_reason": "first_reason; second_reason",
        "research_score": "30",
        "research_band": "8-10",
        "evidence_generated_at": "2026-07-15T12:00:00Z",
        "technical_field": "private technical detail",
    }
    row.update(overrides)
    return row


def test_report_contains_sections_caveats_context_and_escaped_rows():
    rows = [
        evidence_row("BK1", "Sale <Book>", "review_for_possible_sale"),
        evidence_row("BK2", "Manual Book", "manual_market_research_needed"),
        evidence_row("BK3", "Edition Book", "review_edition_or_condition"),
        evidence_row("BK4", "Fallback Book", "fallback_research_priority"),
        evidence_row("BK5", "Cleanup Book", "metadata_cleanup_needed"),
    ]
    enriched = []
    for row in rows:
        enriched.append({
            **row,
            "latest_acquired_date": "2020-01-01",
            "acquisition_year": "2020",
            "possession_confidence": "possibly_absent",
            "possession_note": "acquired before 2021; verify physical possession before sale/research",
        })
    html = render_report(enriched, summary_filename="/private/path/summary.csv")

    for heading in (
        "Library Review Report", "AbeBooks Baseline", "Possible Sale", "Manual Research",
        "Edition / Condition", "Fallback", "Metadata Cleanup", "How to Use This Report",
        "Suggested Next Step", "Field Guide", "Full Caveats",
    ):
        assert heading in html
    assert "<h1>Library Review Report</h1>" in html
    assert '<p class="subtitle">AbeBooks Baseline</p>' in html
    assert "books reviewed" not in html
    assert "AbeBooks asking prices only; not appraisals or sale estimates" in html
    assert "Asking prices are not fair market value" in html
    assert "eBay and other market sources are not included yet" in html
    assert "Sale &lt;Book&gt;" in html
    assert "A &amp; B &lt;Authors&gt;" in html
    assert "2020" in html and "Verify possession" in html
    assert "$50.00–$100.00" in html
    assert "First reason" not in html and "Second reason" not in html
    assert "summary.csv" in html and "/private/path" not in html
    assert "Report generated" in html and "Evidence generated" not in html
    assert html.index("How to Use This Report") < html.index('<nav class="tabs"')
    assert html.index("Source: <code>summary.csv</code>") > html.index("Field Guide")
    assert html.index("Source: <code>summary.csv</code>") < html.index("Full Caveats")
    assert "private technical detail" not in html
    assert "technical_field" not in html
    assert "Market Confidence" not in html
    assert "Outlier Sensitivity" not in html
    assert "Possession Confidence" not in html
    assert "Likely Low" not in html and "Likely Mid" not in html and "Likely High" not in html
    assert html.index("AbeBooks Range") < html.index("Listings")
    assert "Review Counts" not in html
    assert "tab-control" in html
    assert "Suggested Next Step</th>" not in html
    assert "Why Review" not in html
    assert "Review these first. Verify physical possession" in html
    assert "These need manual checking because the AbeBooks evidence is thin" in html
    assert "Sort Order" in html
    for sort_term in ("possession priority", "likely_mid", "likely_high", "title", "Catalog Item ID"):
        assert sort_term in html
    assert "Review Reason" not in html
    assert "The short instruction above each tab" in html
    assert "book(s)" not in html
    assert "background:transparent;color:white;border:1px solid white" in html


def test_report_is_deterministic_and_uses_latest_acquisition(tmp_path):
    row = evidence_row("BK1", "Sale Book", "review_for_possible_sale")
    acquisitions = [
        {"catalog_item_id": "BK1", "order_date": "2019-01-01"},
        {"catalog_item_id": "BK1", "order_date": "2022-05-06"},
    ]
    first = tmp_path / "first.html"
    second = tmp_path / "second.html"
    for output in (first, second):
        write_abebooks_review_report(
            output, summary_rows=[row], acquisitions=acquisitions, summary_filename="summary.csv"
        )
    assert first.read_bytes() == second.read_bytes()
    html = first.read_text(encoding="utf-8")
    assert "2022" in html
    assert "2022-05-06" not in html
    assert "likely_present" not in html


def test_report_marks_old_and_unknown_acquisitions_for_possession_verification():
    rows = [
        {**evidence_row("BK1", "Old", "review_for_possible_sale"), "acquisition_year": "2017", "possession_confidence": "possibly_absent"},
        {**evidence_row("BK2", "Unknown", "review_for_possible_sale"), "acquisition_year": "", "possession_confidence": "unknown"},
    ]
    html = render_report(rows, summary_filename="summary.csv")
    assert "2017" in html
    assert "Unknown" in html
    assert html.count("Verify possession") >= 2


def test_cli_builds_static_review_report(tmp_path, capsys):
    summary_path = tmp_path / "summary.csv"
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    output = tmp_path / "nested" / "review.html"
    rows = [evidence_row("BK1", "Sale Book", "review_for_possible_sale")]
    with summary_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    (data_dir / "acquisitions.csv").write_text(
        "catalog_item_id,order_date\nBK1,2022-01-01\n", encoding="utf-8"
    )

    assert main([
        "build-abebooks-review-report", "--summary", str(summary_path), "--output-html", str(output),
        "--data-dir", str(data_dir),
    ]) == 0
    assert output.exists()
    assert "Wrote 1 AbeBooks review rows" in capsys.readouterr().out

import csv

import library_pipeline
from library_pipeline import main, report_market_observation_coverage
from valuation.market_observation_coverage import (
    MARKET_OBSERVATION_COVERAGE_FIELDNAMES,
    build_market_observation_coverage_rows,
)


def test_build_market_observation_coverage_rows_reports_counts_percentages_and_details():
    sample_rows = [
        sample("BK000001"),
        sample("BK000002"),
        sample("BK000003"),
        sample("BK000004"),
    ]
    observation_rows = [
        observation("BK000001", "observed", "isbn13", "high", "", "", "https://example.test/1"),
        observation("BK000002", "no_results", "isbn10", "unknown", "parse_unavailable", "No parsed listing results.", "https://example.test/2"),
        observation("BK000003", "source_unavailable", "isbn13", "unknown", "tls_certificate_error", "certificate verify failed", "https://example.test/3"),
        observation("BK000004", "no_query", "none", "unknown", "no_query", "No ISBN, title, or author available.", ""),
    ]

    rows = build_market_observation_coverage_rows(sample_rows, observation_rows)
    metrics = {row["metric"]: row for row in rows if row["section"] == "summary"}

    assert metrics["sampled_books"]["count"] == "4"
    assert metrics["books_attempted"]["count"] == "4"
    assert metrics["books_attempted"]["percentage"] == "100.0%"
    assert metrics["observation_rows"]["count"] == "4"
    assert metrics["books_with_observed_listings"]["count"] == "1"
    assert metrics["books_with_observed_listings"]["percentage"] == "25.0%"
    assert metrics["observed_count"]["count"] == "1"
    assert metrics["no_results_count"]["count"] == "1"
    assert metrics["source_unavailable_count"]["count"] == "1"
    assert metrics["no_query_count"]["count"] == "1"
    assert metrics["lookup_strategy_isbn13_count"]["count"] == "2"
    assert metrics["lookup_strategy_isbn10_count"]["count"] == "1"
    assert metrics["lookup_strategy_title_author_count"]["count"] == "0"
    assert metrics["match_confidence_high_count"]["count"] == "1"
    assert metrics["match_confidence_unknown_count"]["count"] == "3"
    assert metrics["unique_sources"]["count"] == "1"
    assert metrics["unique_sources"]["source"] == "abebooks"

    detail_rows = [row for row in rows if row["section"] == "diagnostic_detail"]
    assert len(detail_rows) == 3
    tls_detail = next(row for row in detail_rows if row["diagnostic_code"] == "tls_certificate_error")
    assert tls_detail["source"] == "abebooks"
    assert tls_detail["lookup_status"] == "source_unavailable"
    assert tls_detail["lookup_strategy"] == "isbn13"
    assert tls_detail["raw_reference"] == "https://example.test/3"


def test_report_market_observation_coverage_writes_generated_report(tmp_path):
    output_dir = tmp_path / "output"
    write_rows(output_dir / "market_validation_sample.csv", ["catalog_id"], [sample("BK000001")])
    write_rows(
        output_dir / "market_observations.csv",
        observation_fieldnames(),
        [observation("BK000001", "source_unavailable", "isbn13", "unknown", "tls_certificate_error", "certificate verify failed", "https://example.test/1")],
    )

    count = report_market_observation_coverage(output_dir)

    report_path = output_dir / "market_observation_coverage_report.csv"
    assert count > 1
    assert report_path.exists()
    assert (output_dir / "market_observation_coverage_report.xlsx").exists()
    with report_path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        assert reader.fieldnames == MARKET_OBSERVATION_COVERAGE_FIELDNAMES
        rows = list(reader)
    assert any(row["metric"] == "source_unavailable_count" and row["count"] == "1" for row in rows)
    assert any(row["raw_reference"] == "https://example.test/1" for row in rows)


def test_report_market_observation_coverage_command_wiring(capsys, monkeypatch, tmp_path):
    calls = []

    def fake_report(output_dir):
        calls.append(output_dir)
        return 12

    monkeypatch.setattr(library_pipeline, "report_market_observation_coverage", fake_report)

    result = main([
        "report-market-observation-coverage",
        "--output-dir",
        str(tmp_path),
    ])

    captured = capsys.readouterr().out
    assert result == 0
    assert calls == [tmp_path]
    assert "Wrote 12 market observation coverage rows" in captured


def sample(catalog_id):
    return {"catalog_id": catalog_id}


def observation(catalog_id, lookup_status, lookup_strategy, match_confidence, diagnostic_code, match_notes, raw_reference):
    return {
        "catalog_id": catalog_id,
        "source": "abebooks",
        "lookup_status": lookup_status,
        "lookup_strategy": lookup_strategy,
        "match_confidence": match_confidence,
        "diagnostic_code": diagnostic_code,
        "match_notes": match_notes,
        "raw_reference": raw_reference,
    }


def observation_fieldnames():
    return [
        "catalog_id",
        "source",
        "lookup_status",
        "lookup_strategy",
        "match_confidence",
        "diagnostic_code",
        "match_notes",
        "raw_reference",
    ]


def write_rows(path, fieldnames, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

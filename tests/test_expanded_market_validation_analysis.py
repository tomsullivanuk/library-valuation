import csv

import library_pipeline
from library_pipeline import analyze_expanded_market_validation, main
from valuation.expanded_market_validation_analysis import (
    EXPANDED_MARKET_VALIDATION_ANALYSIS_FIELDNAMES,
    EXPANDED_RESEARCH_SIGNAL_EFFECTIVENESS_FIELDNAMES,
    build_expanded_market_validation_analysis_rows,
    build_expanded_research_signal_effectiveness_rows,
    classification_comparison,
    price_shape_interpretation,
)


def test_expanded_analysis_reports_coverage_and_original_comparison():
    rows = build_analysis_rows()
    metrics = {
        row["metric"]: row
        for row in rows
        if row["section"] == "expanded_coverage_summary"
    }

    assert metrics["expanded_sample_count"]["value"] == "6"
    assert metrics["expanded_sample_count"]["original_sample_count"] == "4"
    assert metrics["total_observation_rows"]["value"] == "8"
    assert metrics["books_with_observations"]["value"] == "6"
    assert metrics["books_without_observations"]["value"] == "0"
    assert metrics["lookup_strategy_isbn13"]["value"] == "8"
    assert metrics["lookup_status_observed"]["value"] == "8"
    assert metrics["source_failure_rows"]["value"] == "0"


def test_expanded_score_band_analysis_includes_minimum_and_sparse_empty_bands():
    rows = build_analysis_rows()
    bands = {
        row["score_band"]: row
        for row in rows
        if row["section"] == "score_band_market_analysis"
    }

    assert bands["0-1"]["books"] == "2"
    assert bands["0-1"]["minimum_asking_price"] == "10.00"
    assert bands["0-1"]["original_sample_count"] == "1"
    assert bands["2-3"]["books"] == "0"
    assert bands["2-3"]["comparison_status"] == "new_or_still_empty_band"
    assert bands["6-7"]["books"] == "1"


def test_expanded_signal_review_reports_classification_changes_and_price_shape():
    rows = build_signal_rows()
    signals = {
        row["signal"]: row
        for row in rows
        if row["section"] == "signal_summary"
    }

    university = signals["university_press"]
    assert university["sampled_books"] == "3"
    assert university["original_sampled_books"] == "1"
    assert university["original_classification"] == "insufficient_sample"
    assert university["comparison_status"] == "evidence_strengthened"
    assert university["minimum_asking_price"] == "5.00"
    assert university["price_interpretation"]


def test_median_maximum_interpretation_identifies_outlier_sensitivity():
    assert price_shape_interpretation(10, 20, 100) == "maximum_and_average_outlier_sensitive"
    assert price_shape_interpretation(10, 11, 100) == "maximum_outlier_sensitive"
    assert price_shape_interpretation(12, 13, 30) == "stronger_typical_market_signal"
    assert price_shape_interpretation(0, 0, 0) == "insufficient_price_evidence"


def test_classification_comparison_distinguishes_holds_strengthening_and_weakening():
    assert classification_comparison("moderate_market_signal", "moderate_market_signal") == "classification_holds"
    assert classification_comparison("insufficient_sample", "moderate_market_signal") == "evidence_strengthened"
    assert classification_comparison("weak_or_inconclusive_signal", "moderate_market_signal") == "evidence_strengthened"
    assert classification_comparison("moderate_market_signal", "weak_or_inconclusive_signal") == "evidence_weakened"


def test_refreshed_candidates_include_comparison_status():
    rows = build_analysis_rows()
    false_positives = [row for row in rows if row["section"] == "false_positive_candidate"]
    false_negatives = [row for row in rows if row["section"] == "false_negative_candidate"]

    assert false_positives
    assert false_positives[0]["comparison_status"] in {"still_flagged", "new_candidate"}
    assert false_negatives
    assert false_negatives[0]["comparison_status"] in {"still_flagged", "new_candidate"}


def test_analyze_expanded_market_validation_writes_all_generated_artifacts(tmp_path):
    output_dir = tmp_path / "output"
    write_inputs(output_dir)

    counts = analyze_expanded_market_validation(output_dir)

    assert counts["analysis_rows"] > 1
    assert counts["signal_rows"] > 1
    assert counts["coverage_rows"] > 1
    expected = [
        "expanded_market_validation_analysis.csv",
        "expanded_market_validation_analysis.xlsx",
        "expanded_research_signal_effectiveness_review.csv",
        "expanded_research_signal_effectiveness_review.xlsx",
        "expanded_market_observation_coverage_report.csv",
        "expanded_market_observation_coverage_report.xlsx",
    ]
    assert all((output_dir / name).exists() for name in expected)
    with (output_dir / expected[0]).open(newline="", encoding="utf-8") as handle:
        analysis_reader = csv.DictReader(handle)
        list(analysis_reader)
    with (output_dir / expected[2]).open(newline="", encoding="utf-8") as handle:
        signal_reader = csv.DictReader(handle)
        list(signal_reader)
    assert analysis_reader.fieldnames == EXPANDED_MARKET_VALIDATION_ANALYSIS_FIELDNAMES
    assert signal_reader.fieldnames == EXPANDED_RESEARCH_SIGNAL_EFFECTIVENESS_FIELDNAMES


def test_expanded_analysis_command_wiring_preserves_original_commands(capsys, monkeypatch, tmp_path):
    calls = []

    def fake_analyze(output_dir):
        calls.append(output_dir)
        return {"analysis_rows": 10, "signal_rows": 20, "coverage_rows": 5}

    monkeypatch.setattr(library_pipeline, "analyze_expanded_market_validation", fake_analyze)

    result = main(["analyze-expanded-market-validation", "--output-dir", str(tmp_path)])

    output = capsys.readouterr().out
    assert result == 0
    assert calls == [tmp_path]
    assert "Wrote 10 expanded market validation analysis rows" in output
    assert "Wrote 20 expanded signal effectiveness rows" in output
    assert "Wrote 5 expanded coverage rows" in output
    parser = library_pipeline.build_parser()
    assert parser.parse_args(["analyze-market-validation"]).command == "analyze-market-validation"
    assert parser.parse_args(["review-research-signal-effectiveness"]).command == "review-research-signal-effectiveness"


def build_analysis_rows():
    return build_expanded_market_validation_analysis_rows(
        expanded_samples(),
        expanded_observations(),
        expanded_metadata(),
        original_samples(),
        original_observations(),
        original_metadata(),
    )


def build_signal_rows():
    return build_expanded_research_signal_effectiveness_rows(
        expanded_samples(),
        expanded_observations(),
        expanded_metadata(),
        original_samples(),
        original_observations(),
        original_metadata(),
    )


def original_samples():
    return [
        sample("BK1", "1", "0-1", "missing_oclc"),
        sample("BK2", "5", "4-5", "specialist_publisher"),
        sample("BK3", "7", "6-7", "multiple_acquisitions"),
        sample("BK4", "9", "8-10", "university_press"),
    ]


def expanded_samples():
    return original_samples() + [
        sample("BK5", "1", "0-1", "missing_oclc;university_press"),
        sample("BK6", "10", "8-10", "university_press"),
    ]


def original_observations():
    return [
        observation("BK1", "10"),
        observation("BK2", "20"),
        observation("BK3", "30"),
        observation("BK4", "5"),
        observation("BK4", "7"),
    ]


def expanded_observations():
    return original_observations() + [
        observation("BK5", "100"),
        observation("BK5", "120"),
        observation("BK6", "60"),
    ]


def original_metadata():
    return [
        metadata("0-1", 1, 10),
        metadata("2-3", 0, 0),
        metadata("4-5", 1, 10),
        metadata("6-7", 1, 1),
        metadata("8-10", 1, 20),
    ]


def expanded_metadata():
    counts = {"0-1": 2, "2-3": 0, "4-5": 1, "6-7": 1, "8-10": 2}
    populations = {"0-1": 10, "2-3": 0, "4-5": 10, "6-7": 1, "8-10": 20}
    return [
        {
            "score_band": band,
            "balanced_target_floor_count": "2",
            "available_population_count": str(populations[band]),
            "expanded_sample_count": str(counts[band]),
        }
        for band in counts
    ]


def sample(catalog_id, score, band, signals):
    return {
        "catalog_id": catalog_id,
        "title": f"Title {catalog_id}",
        "author": "Author",
        "research_score": score,
        "score_band": band,
        "triggered_signals": signals,
    }


def observation(catalog_id, price):
    return {
        "catalog_id": catalog_id,
        "lookup_status": "observed",
        "lookup_strategy": "isbn13",
        "asking_price": price,
        "diagnostic_code": "",
    }


def metadata(band, actual, population):
    return {
        "score_band": band,
        "target_sample_count": "2",
        "available_population_count": str(population),
        "actual_sample_count": str(actual),
    }


def write_inputs(output_dir):
    write_rows(output_dir / "expanded_market_validation_sample.csv", sample_fields(), expanded_samples())
    write_rows(output_dir / "expanded_market_observations.csv", observation_fields(), expanded_observations())
    write_rows(
        output_dir / "expanded_market_validation_sample_metadata.csv",
        expanded_metadata_fields(),
        expanded_metadata(),
    )
    write_rows(output_dir / "market_validation_sample.csv", sample_fields(), original_samples())
    write_rows(output_dir / "market_observations.csv", observation_fields(), original_observations())
    write_rows(output_dir / "market_validation_sample_metadata.csv", original_metadata_fields(), original_metadata())


def sample_fields():
    return ["catalog_id", "title", "author", "research_score", "score_band", "triggered_signals"]


def observation_fields():
    return ["catalog_id", "lookup_status", "lookup_strategy", "asking_price", "diagnostic_code"]


def expanded_metadata_fields():
    return ["score_band", "balanced_target_floor_count", "available_population_count", "expanded_sample_count"]


def original_metadata_fields():
    return ["score_band", "target_sample_count", "available_population_count", "actual_sample_count"]


def write_rows(path, fieldnames, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

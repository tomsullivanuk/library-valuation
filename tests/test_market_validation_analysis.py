import csv

import library_pipeline
from library_pipeline import analyze_market_validation, main
from valuation.market_validation_analysis import (
    MARKET_VALIDATION_ANALYSIS_FIELDNAMES,
    build_market_validation_analysis_rows,
)


def test_build_market_validation_analysis_rows_reports_distribution_and_dataset_summary():
    rows = build_market_validation_analysis_rows(sample_rows(), observation_rows(), metadata_rows())

    distribution = [row for row in rows if row["section"] == "score_distribution"]
    band_2_3 = next(row for row in distribution if row["score_band"] == "2-3")
    band_6_7 = next(row for row in distribution if row["score_band"] == "6-7")
    metrics = {row["metric"]: row for row in rows if row["section"] == "dataset_summary"}

    assert len(distribution) == 5
    assert band_2_3["catalog_population_count"] == "0"
    assert band_2_3["empty_band"] == "yes"
    assert band_6_7["underrepresented_band"] == "yes"
    assert metrics["total_books_sampled"]["value"] == "4"
    assert metrics["books_with_abebooks_observations"]["value"] == "3"
    assert metrics["books_with_abebooks_observations"]["percentage"] == "75.0%"
    assert metrics["books_without_abebooks_observations"]["value"] == "1"
    assert metrics["total_observation_rows"]["value"] == "5"
    assert metrics["observed_listing_rows"]["value"] == "4"


def test_build_market_validation_analysis_rows_reports_score_band_market_indicators():
    rows = build_market_validation_analysis_rows(sample_rows(), observation_rows(), metadata_rows())
    band_rows = {row["score_band"]: row for row in rows if row["section"] == "score_band_market_analysis"}

    assert band_rows["0-1"]["books"] == "1"
    assert band_rows["0-1"]["books_with_observations"] == "1"
    assert band_rows["0-1"]["observation_coverage_rate"] == "100.0%"
    assert band_rows["0-1"]["median_asking_price"] == "110.00"
    assert band_rows["8-10"]["books"] == "2"
    assert band_rows["8-10"]["books_with_observations"] == "1"
    assert band_rows["8-10"]["observation_coverage_rate"] == "50.0%"
    assert band_rows["8-10"]["maximum_asking_price"] == "5.00"
    assert band_rows["2-3"]["books"] == "0"


def test_build_market_validation_analysis_rows_reports_research_signal_indicators():
    rows = build_market_validation_analysis_rows(sample_rows(), observation_rows(), metadata_rows())
    signal_rows = {row["signal"]: row for row in rows if row["section"] == "research_signal_analysis"}

    assert signal_rows["old_publication_year"]["books"] == "2"
    assert signal_rows["old_publication_year"]["percentage"] == "50.0%"
    assert signal_rows["old_publication_year"]["books_with_observations"] == "1"
    assert signal_rows["old_publication_year"]["maximum_asking_price"] == "5.00"
    assert signal_rows["missing_oclc"]["books"] == "1"
    assert signal_rows["missing_oclc"]["median_asking_price"] == "110.00"
    assert signal_rows["specialist_publisher"]["maximum_asking_price"] == "50.00"


def test_build_market_validation_analysis_rows_identifies_false_positive_and_negative_candidates():
    rows = build_market_validation_analysis_rows(sample_rows(), observation_rows(), metadata_rows())
    false_positives = [row for row in rows if row["section"] == "false_positive_candidate"]
    false_negatives = [row for row in rows if row["section"] == "false_negative_candidate"]

    assert {row["catalog_id"] for row in false_positives} == {"BK000002", "BK000003"}
    assert false_positives[0]["title"] == "High Score No Market Evidence"
    assert false_positives[0]["price_summary"] == "No observed asking prices."
    assert [row["catalog_id"] for row in false_negatives] == ["BK000001"]
    assert false_negatives[0]["maximum_asking_price"] == "120.00"


def test_analyze_market_validation_writes_generated_outputs(tmp_path):
    output_dir = tmp_path / "output"
    write_rows(output_dir / "market_validation_sample.csv", sample_fieldnames(), sample_rows())
    write_rows(output_dir / "market_observations.csv", observation_fieldnames(), observation_rows())
    write_rows(output_dir / "market_validation_sample_metadata.csv", metadata_fieldnames(), metadata_rows())

    count = analyze_market_validation(output_dir)

    analysis_path = output_dir / "market_validation_analysis.csv"
    assert count > 1
    assert analysis_path.exists()
    assert (output_dir / "market_validation_analysis.xlsx").exists()
    with analysis_path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        rows = list(reader)
    assert reader.fieldnames == MARKET_VALIDATION_ANALYSIS_FIELDNAMES
    assert any(row["section"] == "false_negative_candidate" for row in rows)
    assert any(row["section"] == "research_signal_analysis" for row in rows)


def test_analyze_market_validation_command_wiring(capsys, monkeypatch, tmp_path):
    calls = []

    def fake_analyze(output_dir):
        calls.append(output_dir)
        return 21

    monkeypatch.setattr(library_pipeline, "analyze_market_validation", fake_analyze)

    result = main([
        "analyze-market-validation",
        "--output-dir",
        str(tmp_path),
    ])

    captured = capsys.readouterr().out
    assert result == 0
    assert calls == [tmp_path]
    assert "Wrote 21 market validation analysis rows" in captured


def sample_rows():
    return [
        sample("BK000001", "Low Score Strong Evidence", "Ada Author", "1", "0-1", "missing_oclc"),
        sample("BK000002", "High Score Weak Evidence", "Bea Author", "9", "8-10", "old_publication_year;university_press"),
        sample("BK000003", "High Score No Market Evidence", "Cy Author", "10", "8-10", "old_publication_year"),
        sample("BK000004", "Middle Score Evidence", "Dee Author", "5", "4-5", "specialist_publisher"),
    ]


def observation_rows():
    return [
        observation("BK000001", "observed", "100.00"),
        observation("BK000001", "observed", "120.00"),
        observation("BK000002", "observed", "5.00"),
        observation("BK000003", "no_results", ""),
        observation("BK000004", "observed", "50.00"),
    ]


def metadata_rows():
    return [
        metadata("0-1", 20, 10, 1),
        metadata("2-3", 20, 0, 0),
        metadata("4-5", 20, 8, 1),
        metadata("6-7", 20, 3, 0),
        metadata("8-10", 20, 50, 2),
    ]


def sample(catalog_id, title, author, research_score, score_band, triggered_signals):
    return {
        "catalog_id": catalog_id,
        "title": title,
        "author": author,
        "research_score": research_score,
        "score_band": score_band,
        "triggered_signals": triggered_signals,
    }


def observation(catalog_id, lookup_status, asking_price):
    return {
        "catalog_id": catalog_id,
        "lookup_status": lookup_status,
        "asking_price": asking_price,
    }


def metadata(score_band, target, available, actual):
    return {
        "score_band": score_band,
        "target_sample_count": str(target),
        "available_population_count": str(available),
        "actual_sample_count": str(actual),
    }


def sample_fieldnames():
    return ["catalog_id", "title", "author", "research_score", "score_band", "triggered_signals"]


def observation_fieldnames():
    return ["catalog_id", "lookup_status", "asking_price"]


def metadata_fieldnames():
    return ["score_band", "target_sample_count", "available_population_count", "actual_sample_count"]


def write_rows(path, fieldnames, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

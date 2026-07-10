import csv

import library_pipeline
from library_pipeline import main, review_research_signal_effectiveness
from valuation.research_signal_effectiveness import (
    RESEARCH_SIGNAL_EFFECTIVENESS_FIELDNAMES,
    build_research_signal_effectiveness_rows,
    classify_signal,
)


def test_signal_summary_calculates_coverage_and_price_statistics():
    rows = build_research_signal_effectiveness_rows(samples(), observations(), metadata())
    signals = {row["signal"]: row for row in rows if row["section"] == "signal_summary"}

    university = signals["university_press"]
    assert university["sampled_books"] == "3"
    assert university["sample_percentage"] == "50.0%"
    assert university["books_with_observations"] == "3"
    assert university["observation_rows"] == "4"
    assert university["median_asking_price"] == "75.00"
    assert university["average_asking_price"] == "68.75"
    assert university["minimum_asking_price"] == "5.00"
    assert university["maximum_asking_price"] == "120.00"


def test_signal_classification_uses_transparent_sample_relative_rules():
    def classification(**values):
        return classify_signal(**values)[0]

    assert classification(book_count=2, median_price=100, overall_price_median=10, high_score_share=0) == "insufficient_sample"
    assert classification(book_count=3, median_price=16, overall_price_median=10, high_score_share=0) == "strong_market_signal"
    assert classification(book_count=3, median_price=10, overall_price_median=10, high_score_share=0) == "moderate_market_signal"
    assert classification(book_count=3, median_price=8, overall_price_median=10, high_score_share=0) == "weak_or_inconclusive_signal"
    assert classification(book_count=3, median_price=8, overall_price_median=10, high_score_share=0.67) == "possible_false_positive_driver"


def test_signal_combination_review_surfaces_three_market_evidence_cohorts():
    rows = build_research_signal_effectiveness_rows(samples(), observations(), metadata())
    combinations = [row for row in rows if row["section"] == "signal_combination_review"]

    cohorts = {row["cohort"] for row in combinations}
    assert cohorts == {
        "high_score_strong_market_evidence",
        "high_score_weak_market_evidence",
        "low_score_strong_market_evidence",
    }
    assert any(row["combination"] == "old_publication_year;university_press" for row in combinations)


def test_candidate_review_identifies_relative_false_positives_and_negatives():
    rows = build_research_signal_effectiveness_rows(samples(), observations(), metadata())
    false_positives = [row for row in rows if row["section"] == "false_positive_candidate"]
    false_negatives = [row for row in rows if row["section"] == "false_negative_candidate"]

    assert {row["catalog_id"] for row in false_positives} == {"BK2", "BK3"}
    assert [row["catalog_id"] for row in false_negatives] == ["BK1"]
    assert false_positives[0]["reason_flagged"]
    assert false_negatives[0]["threshold_basis"].startswith("Sample-wide median")


def test_sparse_signal_and_missing_observation_are_reported_without_failure():
    rows = build_research_signal_effectiveness_rows(samples(), observations(), metadata())
    signals = {row["signal"]: row for row in rows if row["section"] == "signal_summary"}

    assert signals["missing_oclc"]["classification"] == "insufficient_sample"
    assert signals["old_publication_year"]["observation_coverage_rate"] == "50.0%"
    no_market = next(row for row in rows if row["section"] == "false_positive_candidate" and row["catalog_id"] == "BK3")
    assert no_market["observation_rows"] == "0"
    assert no_market["median_asking_price"] == ""


def test_calibration_notes_use_metadata_and_prior_artifact_context():
    rows = build_research_signal_effectiveness_rows(
        samples(),
        observations(),
        metadata(),
        [{"section": "summary"}],
        [{"section": "score_band_market_analysis", "score_band": "0-1", "books": "1", "median_asking_price": "100"}],
    )
    notes = {row["metric"]: row["notes"] for row in rows if row["section"] == "model_calibration_note"}

    assert "2-3" in notes["score_band_usage"]
    assert "Consumed 1 coverage rows and 1 PR8 analysis rows" in notes["artifact_traceability"]


def test_review_command_writes_csv_and_xlsx_outputs(tmp_path):
    output_dir = tmp_path / "output"
    write_rows(output_dir / "market_validation_sample.csv", sample_fields(), samples())
    write_rows(output_dir / "market_observations.csv", observation_fields(), observations())
    write_rows(output_dir / "market_validation_sample_metadata.csv", metadata_fields(), metadata())
    write_rows(output_dir / "market_observation_coverage_report.csv", ["section"], [{"section": "summary"}])
    write_rows(
        output_dir / "market_validation_analysis.csv",
        ["section", "score_band", "books", "median_asking_price"],
        [{"section": "score_band_market_analysis", "score_band": "0-1", "books": "1", "median_asking_price": "100"}],
    )

    count = review_research_signal_effectiveness(output_dir)

    output_path = output_dir / "research_signal_effectiveness_review.csv"
    assert count > 1
    assert output_path.exists()
    assert (output_dir / "research_signal_effectiveness_review.xlsx").exists()
    with output_path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        rows = list(reader)
    assert reader.fieldnames == RESEARCH_SIGNAL_EFFECTIVENESS_FIELDNAMES
    assert any(row["section"] == "signal_summary" for row in rows)


def test_review_command_wiring(capsys, monkeypatch, tmp_path):
    calls = []

    def fake_review(output_dir):
        calls.append(output_dir)
        return 17

    monkeypatch.setattr(library_pipeline, "review_research_signal_effectiveness", fake_review)

    result = main(["review-research-signal-effectiveness", "--output-dir", str(tmp_path)])

    assert result == 0
    assert calls == [tmp_path]
    assert "Wrote 17 research signal effectiveness rows" in capsys.readouterr().out


def samples():
    return [
        sample("BK1", "Low Strong", "Ada", "1", "0-1", "missing_oclc;university_press"),
        sample("BK2", "High Weak", "Bea", "9", "8-10", "old_publication_year;university_press"),
        sample("BK3", "High Missing", "Cy", "10", "8-10", "old_publication_year"),
        sample("BK4", "High Strong", "Dee", "8", "8-10", "scholarly_lc_subject;university_press"),
        sample("BK5", "Middle", "Eve", "5", "4-5", "specialist_publisher"),
        sample("BK6", "Middle Two", "Fox", "5", "4-5", "specialist_publisher"),
    ]


def observations():
    return [
        observation("BK1", "observed", "100"),
        observation("BK1", "observed", "120"),
        observation("BK2", "observed", "5"),
        observation("BK3", "no_results", ""),
        observation("BK4", "observed", "50"),
        observation("BK5", "observed", "10"),
        observation("BK6", "observed", "20"),
    ]


def metadata():
    return [
        meta("0-1", 20, 20, 1),
        meta("2-3", 20, 0, 0),
        meta("4-5", 20, 20, 2),
        meta("6-7", 20, 5, 0),
        meta("8-10", 20, 100, 3),
    ]


def sample(catalog_id, title, author, score, band, signals):
    return {
        "catalog_id": catalog_id,
        "title": title,
        "author": author,
        "research_score": score,
        "score_band": band,
        "triggered_signals": signals,
    }


def observation(catalog_id, status, price):
    return {"catalog_id": catalog_id, "lookup_status": status, "asking_price": price}


def meta(band, target, population, actual):
    return {
        "score_band": band,
        "target_sample_count": str(target),
        "available_population_count": str(population),
        "actual_sample_count": str(actual),
    }


def sample_fields():
    return ["catalog_id", "title", "author", "research_score", "score_band", "triggered_signals"]


def observation_fields():
    return ["catalog_id", "lookup_status", "asking_price"]


def metadata_fields():
    return ["score_band", "target_sample_count", "available_population_count", "actual_sample_count"]


def write_rows(path, fieldnames, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

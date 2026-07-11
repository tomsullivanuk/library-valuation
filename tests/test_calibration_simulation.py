import csv

import library_pipeline
from library_pipeline import main, simulate_research_assessment_calibration
from valuation.calibration_simulation import (
    BASELINE_SCENARIO,
    CALIBRATION_SIMULATION_FIELDNAMES,
    CALIBRATION_SIMULATION_MOVEMENT_FIELDNAMES,
    CALIBRATION_SIMULATION_SUMMARY_FIELDNAMES,
    CONSERVATIVE_SCENARIO,
    MARKET_LIKELIHOOD_SCENARIO,
    build_calibration_simulation,
)


def test_baseline_scenario_preserves_current_scores_and_bands():
    simulation, _, _ = simulation_result()
    baseline = [row for row in simulation if row["simulated_scenario"] == BASELINE_SCENARIO]

    assert all(row["simulated_score"] == row["current_score"] for row in baseline)
    assert all(row["simulated_band"] == row["current_band"] for row in baseline)
    assert all(row["score_delta"] == "+0" for row in baseline)
    assert all(row["band_delta"] == "+0" for row in baseline)


def test_scenario_scores_and_contributions_are_explainable():
    simulation, _, _ = simulation_result()
    conservative = find_row(simulation, "BK1", CONSERVATIVE_SCENARIO)
    market = find_row(simulation, "BK2", MARKET_LIKELIHOOD_SCENARIO)

    assert conservative["simulated_score"] == "15"
    assert conservative["score_delta"] == "+15"
    assert conservative["simulated_signal_contribution_summary"] == "university_press:+15"
    assert "university_press:+15->+15" not in conservative["movement_reason"]
    assert market["simulated_score"] == "1"
    assert market["score_delta"] == "-29"
    assert "low_metadata_confidence:+6->+0" in market["movement_reason"]
    assert "missing_oclc:+5->+1" in market["movement_reason"]


def test_score_distribution_summary_reports_movement_and_band_crossings():
    _, summary, _ = simulation_result()
    conservative = summary_metrics(summary, CONSERVATIVE_SCENARIO)

    assert conservative["book_count"] == "4"
    assert conservative["moving_up"] == "2"
    assert conservative["moving_down"] == "1"
    assert conservative["production_band_crossings"] == "2"
    distribution = {
        row["score_band"]: row["value"]
        for row in summary
        if row["section"] == "score_distribution" and row["scenario"] == CONSERVATIVE_SCENARIO
    }
    assert distribution == {"none": "0", "low": "2", "medium": "2", "high": "0"}


def test_candidate_movements_detect_top_n_and_reference_improvements():
    _, summary, movements = simulation_result()
    movement_types = {(row["catalog_id"], row["movement_type"]) for row in movements}

    assert ("BK1", "entered_top_n") in movement_types
    assert ("BK1", "false_negative_moved_up") in movement_types
    assert ("BK2", "left_top_n") in movement_types
    assert ("BK2", "false_positive_moved_down") in movement_types
    market = summary_metrics(summary, MARKET_LIKELIHOOD_SCENARIO)
    assert market["top_n_entering"] == "1"
    assert market["top_n_leaving"] == "1"
    assert market["false_positive_references_moving_down"] == "1"
    assert market["false_negative_references_moving_up"] == "1"


def test_simulation_handles_empty_validation_bands_and_is_deterministic():
    first = simulation_result()
    second = build_calibration_simulation(
        list(reversed(samples())),
        list(reversed(observations())),
        list(reversed(signal_review())),
        top_n=2,
    )

    assert first == second
    _, summary, _ = first
    issues = {
        row["metric"]: row["value"]
        for row in summary
        if row["section"] == "band_interpretation" and row["scenario"] == BASELINE_SCENARIO
    }
    assert issues["validation_2_3_band"] == "empty_in_expanded_sample"
    assert issues["validation_6_7_band"] == "sparse_in_expanded_sample"
    assert issues["validation_8_plus_band"] == "open_ended"


def test_simulation_writes_three_paired_artifacts(tmp_path):
    output_dir = tmp_path / "output"
    write_rows(output_dir / "expanded_market_validation_sample.csv", sample_fields(), samples())
    write_rows(output_dir / "expanded_market_observations.csv", observation_fields(), observations())
    write_rows(
        output_dir / "expanded_research_signal_effectiveness_review.csv",
        signal_review_fields(),
        signal_review(),
    )

    counts = simulate_research_assessment_calibration(output_dir, top_n=2)

    assert counts["simulation_rows"] == 12
    assert counts["summary_rows"] > 1
    assert counts["movement_rows"] > 1
    expected = [
        "calibration_simulation.csv",
        "calibration_simulation.xlsx",
        "calibration_simulation_summary.csv",
        "calibration_simulation_summary.xlsx",
        "calibration_simulation_candidate_movements.csv",
        "calibration_simulation_candidate_movements.xlsx",
    ]
    assert all((output_dir / name).exists() for name in expected)
    assert csv_fields(output_dir / expected[0]) == CALIBRATION_SIMULATION_FIELDNAMES
    assert csv_fields(output_dir / expected[2]) == CALIBRATION_SIMULATION_SUMMARY_FIELDNAMES
    assert csv_fields(output_dir / expected[4]) == CALIBRATION_SIMULATION_MOVEMENT_FIELDNAMES


def test_simulation_command_wiring(capsys, monkeypatch, tmp_path):
    calls = []

    def fake_simulate(output_dir, top_n):
        calls.append((output_dir, top_n))
        return {"simulation_rows": 12, "summary_rows": 60, "movement_rows": 8}

    monkeypatch.setattr(library_pipeline, "simulate_research_assessment_calibration", fake_simulate)

    result = main([
        "simulate-research-assessment-calibration",
        "--output-dir", str(tmp_path),
        "--top-n", "25",
    ])

    output = capsys.readouterr().out
    assert result == 0
    assert calls == [(tmp_path, 25)]
    assert "Wrote 12 calibration simulation rows" in output
    assert "Wrote 60 calibration summary rows" in output
    assert "Wrote 8 candidate movement rows" in output


def simulation_result():
    return build_calibration_simulation(samples(), observations(), signal_review(), top_n=2)


def find_row(rows, catalog_id, scenario):
    return next(
        row
        for row in rows
        if row["catalog_id"] == catalog_id and row["simulated_scenario"] == scenario
    )


def summary_metrics(rows, scenario):
    return {
        row["metric"]: row["value"]
        for row in rows
        if row["section"] == "scenario_summary" and row["scenario"] == scenario
    }


def samples():
    return [
        sample("BK1", 0, "university_press"),
        sample("BK2", 30, "low_metadata_confidence;missing_oclc"),
        sample("BK3", 15, "university_press"),
        sample("BK4", 6, "multiple_acquisitions"),
    ]


def observations():
    return [
        observation("BK1", "100"),
        observation("BK2", "5"),
        observation("BK3", "50"),
        observation("BK4", "60"),
    ]


def signal_review():
    return [
        {"section": "false_negative_candidate", "catalog_id": "BK1"},
        {"section": "false_positive_candidate", "catalog_id": "BK2"},
    ]


def sample(catalog_id, score, signals):
    return {
        "catalog_id": catalog_id,
        "title": f"Title {catalog_id}",
        "author": "Author",
        "research_score": str(score),
        "triggered_signals": signals,
    }


def observation(catalog_id, price):
    return {"catalog_id": catalog_id, "lookup_status": "observed", "asking_price": price}


def sample_fields():
    return ["catalog_id", "title", "author", "research_score", "triggered_signals"]


def observation_fields():
    return ["catalog_id", "lookup_status", "asking_price"]


def signal_review_fields():
    return ["section", "catalog_id"]


def write_rows(path, fieldnames, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def csv_fields(path):
    with path.open(newline="", encoding="utf-8") as handle:
        return csv.DictReader(handle).fieldnames

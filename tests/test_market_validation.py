import csv

import pytest

from library_pipeline import generate_market_validation_sample
from valuation.market_validation import (
    MARKET_VALIDATION_SAMPLE_METADATA_FIELDNAMES,
    MARKET_VALIDATION_SAMPLE_FIELDNAMES,
    build_market_validation_sample_metadata_rows,
    build_market_validation_sample_rows,
    score_band_for_score,
)


def test_score_band_for_score_uses_market_validation_bands():
    assert score_band_for_score("0") == "0-1"
    assert score_band_for_score("1") == "0-1"
    assert score_band_for_score("2") == "2-3"
    assert score_band_for_score("3") == "2-3"
    assert score_band_for_score("4") == "4-5"
    assert score_band_for_score("5") == "4-5"
    assert score_band_for_score("6") == "6-7"
    assert score_band_for_score("7") == "6-7"
    assert score_band_for_score("8") == "8-10"
    assert score_band_for_score("10") == "8-10"


def test_build_market_validation_sample_rows_is_deterministic_after_stable_sorting():
    catalog_rows = [catalog_row("BK000004"), catalog_row("BK000001"), catalog_row("BK000003"), catalog_row("BK000002")]
    assessments = [
        assessment("BK000004", "8", "university_press; old_publication_year"),
        assessment("BK000001", "8", "missing_lcc"),
        assessment("BK000003", "8", "specialist_publisher"),
        assessment("BK000002", "8", "pre_isbn"),
    ]

    first_rows = build_market_validation_sample_rows(
        catalog_rows,
        assessments,
        sample_size_per_band=2,
        seed=42,
        sampled_at="2026-07-09T00:00:00Z",
    )
    second_rows = build_market_validation_sample_rows(
        list(reversed(catalog_rows)),
        list(reversed(assessments)),
        sample_size_per_band=2,
        seed=42,
        sampled_at="2026-07-09T00:00:00Z",
    )

    assert first_rows == second_rows
    assert len(first_rows) == 2
    assert {row["score_band"] for row in first_rows} == {"8-10"}
    assert all(row["sample_seed"] == "42" for row in first_rows)


def test_build_market_validation_sample_rows_includes_undersized_score_bands():
    rows = build_market_validation_sample_rows(
        [catalog_row("BK000001"), catalog_row("BK000002")],
        [
            assessment("BK000001", "0", ""),
            assessment("BK000002", "7", "small_publisher"),
        ],
        sample_size_per_band=6,
        seed=42,
        sampled_at="2026-07-09T00:00:00Z",
    )

    assert [row["catalog_id"] for row in rows] == ["BK000001", "BK000002"]
    assert [row["score_band"] for row in rows] == ["0-1", "6-7"]


def test_build_market_validation_sample_rows_preserves_triggered_signals_without_score_inference():
    rows = build_market_validation_sample_rows(
        [catalog_row("BK000001")],
        [assessment("BK000001", "10", "pre_isbn; university_press; small_publisher")],
        sample_size_per_band=1,
        seed=42,
        sampled_at="2026-07-09T00:00:00Z",
    )

    assert rows[0]["triggered_signals"] == "pre_isbn;university_press;small_publisher"
    assert rows[0]["research_score"] == "10"


def test_build_market_validation_sample_rows_supports_100_book_stratified_sample():
    catalog_rows = []
    assessments = []
    scores_by_band = {
        "0-1": "1",
        "2-3": "3",
        "4-5": "5",
        "6-7": "7",
        "8-10": "10",
    }
    for band_index, score in enumerate(scores_by_band.values(), start=1):
        for item_index in range(25):
            catalog_id = f"BK{band_index:03d}{item_index:03d}"
            catalog_rows.append(catalog_row(catalog_id))
            assessments.append(assessment(catalog_id, score, "signal"))

    rows = build_market_validation_sample_rows(
        list(reversed(catalog_rows)),
        list(reversed(assessments)),
        sample_size_per_band=20,
        seed=42,
        sampled_at="2026-07-09T00:00:00Z",
    )

    assert len(rows) == 100
    assert {band: sum(1 for row in rows if row["score_band"] == band) for band in scores_by_band} == {
        "0-1": 20,
        "2-3": 20,
        "4-5": 20,
        "6-7": 20,
        "8-10": 20,
    }
    assert rows == build_market_validation_sample_rows(
        catalog_rows,
        assessments,
        sample_size_per_band=20,
        seed=42,
        sampled_at="2026-07-09T00:00:00Z",
    )


def test_build_market_validation_sample_metadata_rows_records_population_and_sample_counts():
    sample_rows = [
        {"catalog_id": "BK000001", "score_band": "0-1"},
        {"catalog_id": "BK000002", "score_band": "6-7"},
    ]
    assessments = [
        assessment("BK000001", "1", "old_publication_year") | {
            "research_model_version": "0.3.0",
            "research_config_hash": "hash-a",
        },
        assessment("BK000002", "7", "small_publisher") | {
            "research_model_version": "0.3.0",
            "research_config_hash": "hash-a",
        },
        assessment("BK000003", "10", "university_press") | {
            "research_model_version": "0.3.0",
            "research_config_hash": "hash-a",
        },
    ]

    rows = build_market_validation_sample_metadata_rows(
        sample_rows,
        assessments,
        sample_size_per_band=20,
        seed=42,
        sampled_at="2026-07-09T00:00:00Z",
    )

    assert [row["score_band"] for row in rows] == ["0-1", "2-3", "4-5", "6-7", "8-10"]
    assert rows[0]["available_population_count"] == "1"
    assert rows[0]["actual_sample_count"] == "1"
    assert rows[1]["available_population_count"] == "0"
    assert rows[1]["actual_sample_count"] == "0"
    assert rows[3]["available_population_count"] == "1"
    assert rows[3]["actual_sample_count"] == "1"
    assert rows[4]["available_population_count"] == "1"
    assert rows[4]["actual_sample_count"] == "0"
    assert {row["target_sample_count"] for row in rows} == {"20"}
    assert {row["total_available_population_count"] for row in rows} == {"3"}
    assert {row["total_sample_count"] for row in rows} == {"2"}
    assert {row["research_model_version"] for row in rows} == {"0.3.0"}
    assert {row["research_config_hash"] for row in rows} == {"hash-a"}


def test_generate_market_validation_sample_writes_required_columns_without_valuation_fields(tmp_path):
    output_dir = tmp_path / "output"
    data_dir = tmp_path / "data"
    write_rows(output_dir / "library_catalog.csv", ["catalog_item_id", "title", "authors", "isbn10", "isbn13"], [
        {
            "catalog_item_id": "BK000001",
            "title": "Sample Book",
            "authors": "Ada Author",
            "isbn10": "0123456789",
            "isbn13": "9780123456786",
        }
    ])
    write_rows(data_dir / "catalog_items.csv", ["catalog_item_id", "publisher", "publication_year"], [
        {
            "catalog_item_id": "BK000001",
            "publisher": "Example Press",
            "publication_year": "1984",
        }
    ])
    write_rows(data_dir / "acquisitions.csv", ["catalog_item_id", "source_asin"], [
        {
            "catalog_item_id": "BK000001",
            "source_asin": "0123456789",
        }
    ])
    write_rows(
        data_dir / "research_priority_assessments.csv",
        ["catalog_item_id", "isbn13", "research_priority_score", "research_signal_codes"],
        [assessment("BK000001", "8", "pre_isbn; university_press")],
    )

    count = generate_market_validation_sample(
        output_dir,
        data_dir=data_dir,
        sample_size_per_band=6,
        seed=42,
        sampled_at="2026-07-09T00:00:00Z",
    )

    sample_path = output_dir / "market_validation_sample.csv"
    assert count == 1
    assert sample_path.exists()
    assert (output_dir / "market_validation_sample.xlsx").exists()
    assert (output_dir / "market_validation_sample_metadata.csv").exists()
    assert (output_dir / "market_validation_sample_metadata.xlsx").exists()
    with sample_path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        assert reader.fieldnames == MARKET_VALIDATION_SAMPLE_FIELDNAMES
        rows = list(reader)
    assert rows[0] == {
        "catalog_id": "BK000001",
        "title": "Sample Book",
        "author": "Ada Author",
        "isbn10": "0123456789",
        "isbn13": "9780123456786",
        "asin": "0123456789",
        "publisher": "Example Press",
        "publication_year": "1984",
        "research_score": "8",
        "score_band": "8-10",
        "triggered_signals": "pre_isbn;university_press",
        "sample_seed": "42",
        "sampled_at": "2026-07-09T00:00:00Z",
    }
    forbidden_fields = {
        "estimated_value",
        "market_source",
        "confidence",
        "asking_price",
        "sold_price",
        "valuation_notes",
    }
    assert forbidden_fields.isdisjoint(reader.fieldnames or [])
    with (output_dir / "market_validation_sample_metadata.csv").open(newline="", encoding="utf-8") as handle:
        metadata_reader = csv.DictReader(handle)
        metadata_rows = list(metadata_reader)
    assert metadata_reader.fieldnames == MARKET_VALIDATION_SAMPLE_METADATA_FIELDNAMES
    assert len(metadata_rows) == 5
    assert metadata_rows[-1]["score_band"] == "8-10"
    assert metadata_rows[-1]["actual_sample_count"] == "1"


def test_generate_market_validation_sample_accepts_generated_assessment_input_without_data_files(tmp_path):
    output_dir = tmp_path / "output"
    write_rows(output_dir / "library_catalog.csv", ["catalog_item_id", "title", "authors"], [
        {
            "catalog_item_id": "BK000001",
            "title": "Generated Catalog Book",
            "authors": "Ada Author",
        }
    ])
    write_rows(
        output_dir / "research_assessments.csv",
        ["catalog_item_id", "isbn13", "research_priority_score", "research_signal_codes"],
        [assessment("BK000001", "3", "missing_oclc")],
    )

    count = generate_market_validation_sample(
        output_dir,
        data_dir=tmp_path / "missing-data",
        sample_size_per_band=6,
        seed=42,
        sampled_at="2026-07-09T00:00:00Z",
    )

    with (output_dir / "market_validation_sample.csv").open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    assert count == 1
    assert rows[0]["catalog_id"] == "BK000001"
    assert rows[0]["score_band"] == "2-3"
    assert rows[0]["triggered_signals"] == "missing_oclc"


def test_build_market_validation_sample_rows_rejects_nonpositive_sample_size():
    with pytest.raises(ValueError, match="sample_size_per_band"):
        build_market_validation_sample_rows([], [], sample_size_per_band=0)


def catalog_row(catalog_item_id):
    return {
        "catalog_item_id": catalog_item_id,
        "title": f"Title {catalog_item_id}",
        "authors": "Author",
        "isbn10": "",
        "isbn13": catalog_item_id.replace("BK", "978"),
    }


def assessment(catalog_item_id, score, signal_codes):
    return {
        "catalog_item_id": catalog_item_id,
        "isbn13": catalog_item_id.replace("BK", "978"),
        "research_priority_score": score,
        "research_signal_codes": signal_codes,
    }


def write_rows(path, fieldnames, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

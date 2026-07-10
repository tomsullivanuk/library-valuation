import csv

import library_pipeline
from library_pipeline import (
    collect_expanded_abebooks_observations,
    generate_expanded_market_validation_sample,
    main,
)
from valuation.market_validation import (
    EXPANDED_MARKET_VALIDATION_METADATA_FIELDNAMES,
    MARKET_VALIDATION_SAMPLE_FIELDNAMES,
    build_expanded_market_validation_metadata_rows,
    build_expanded_market_validation_sample_rows,
)


LISTING_HTML = """
<html><body><div class="cf result-item">
  <a class="title" href="/servlet/BookDetailsPL?bi=123">New Book</a>
  <p class="author">Author: New Author</p>
  <p class="item-price">$18.00</p>
  <p class="condition">Condition: Good</p>
  <p class="seller">Seller: Example Books</p>
</div></body></html>
"""


def test_expanded_sample_preserves_existing_rows_and_excludes_duplicate_candidates():
    existing = [sample("BK001", "1", "0-1", "missing_oclc", sampled_at="old")]
    catalog = [catalog_row("BK001"), catalog_row("BK002"), catalog_row("BK003")]
    assessments = [
        assessment("BK001", "1", "missing_oclc"),
        assessment("BK002", "5", "specialist_publisher"),
        assessment("BK003", "8", "university_press"),
    ]

    rows = build_expanded_market_validation_sample_rows(
        existing,
        catalog,
        assessments,
        additional_candidate_target=2,
        seed=42,
        sampled_at="new",
    )

    assert {row["catalog_id"] for row in rows} == {"BK001", "BK002", "BK003"}
    assert len(rows) == 3
    preserved = next(row for row in rows if row["catalog_id"] == "BK001")
    assert preserved["sampled_at"] == "old"
    assert preserved["sample_seed"] == "7"


def test_expanded_sample_respects_target_and_is_deterministic_after_input_reordering():
    existing = [sample("BK001", "1", "0-1", "missing_oclc")]
    catalog = [catalog_row(f"BK{index:03d}") for index in range(1, 10)]
    assessments = [
        assessment(f"BK{index:03d}", str((index % 3) * 4 + 1), "missing_oclc")
        for index in range(1, 10)
    ]

    first = build_expanded_market_validation_sample_rows(
        existing,
        catalog,
        assessments,
        additional_candidate_target=5,
        seed=42,
        sampled_at="new",
    )
    second = build_expanded_market_validation_sample_rows(
        list(reversed(existing)),
        list(reversed(catalog)),
        list(reversed(assessments)),
        additional_candidate_target=5,
        seed=42,
        sampled_at="new",
    )

    assert first == second
    assert len(first) == 6
    assert len({row["catalog_id"] for row in first}) == 6


def test_expanded_sample_prioritizes_sparse_calibration_evidence_within_band():
    rows = build_expanded_market_validation_sample_rows(
        [],
        [catalog_row("BK001"), catalog_row("BK002")],
        [
            assessment("BK001", "8", "university_press"),
            assessment("BK002", "8", "old_publication_year;specialist_publisher"),
        ],
        additional_candidate_target=1,
        seed=42,
        sampled_at="new",
    )

    assert [row["catalog_id"] for row in rows] == ["BK002"]


def test_expanded_sample_prefers_an_available_underrepresented_score_band():
    existing = [
        sample("BK001", "1", "0-1", "missing_oclc"),
        sample("BK002", "8", "8-10", "university_press"),
    ]
    rows = build_expanded_market_validation_sample_rows(
        existing,
        [catalog_row("BK001"), catalog_row("BK002"), catalog_row("BK003"), catalog_row("BK004")],
        [
            assessment("BK001", "1", "missing_oclc"),
            assessment("BK002", "8", "university_press"),
            assessment("BK003", "1", "missing_oclc"),
            assessment("BK004", "7", "multiple_acquisitions"),
        ],
        additional_candidate_target=1,
        seed=42,
        sampled_at="new",
    )

    assert {row["catalog_id"] for row in rows} == {"BK001", "BK002", "BK004"}


def test_expanded_metadata_reports_exhausted_bands_and_shortfall():
    existing = [sample("BK001", "1", "0-1", "missing_oclc")]
    expanded = existing + [sample("BK002", "5", "4-5", "specialist_publisher")]
    assessments = [
        assessment("BK001", "1", "missing_oclc", version="0.3.0", config_hash="hash-a"),
        assessment("BK002", "5", "specialist_publisher", version="0.3.0", config_hash="hash-a"),
    ]

    rows = build_expanded_market_validation_metadata_rows(
        expanded,
        existing,
        assessments,
        additional_candidate_target=4,
        seed=42,
        sampled_at="new",
    )
    by_band = {row["score_band"]: row for row in rows}

    assert by_band["0-1"]["existing_sample_count"] == "1"
    assert by_band["4-5"]["additional_selected_count"] == "1"
    assert by_band["2-3"]["population_exhausted"] == "yes"
    assert by_band["2-3"]["score_band_deficit_count"] == "1"
    assert {row["actual_additional_candidates"] for row in rows} == {"1"}
    assert {row["expanded_total_sample_count"] for row in rows} == {"2"}
    assert {row["research_model_version"] for row in rows} == {"0.3.0"}
    assert {row["research_config_hash"] for row in rows} == {"hash-a"}


def test_generate_expanded_sample_writes_required_artifacts(tmp_path):
    output_dir = tmp_path / "output"
    data_dir = tmp_path / "data"
    write_rows(output_dir / "library_catalog.csv", catalog_fields(), [catalog_row("BK001"), catalog_row("BK002")])
    write_rows(
        output_dir / "market_validation_sample.csv",
        MARKET_VALIDATION_SAMPLE_FIELDNAMES,
        [sample("BK001", "1", "0-1", "missing_oclc")],
    )
    write_rows(data_dir / "research_priority_assessments.csv", assessment_fields(), [
        assessment("BK001", "1", "missing_oclc"),
        assessment("BK002", "8", "university_press"),
    ])

    count = generate_expanded_market_validation_sample(
        output_dir,
        data_dir=data_dir,
        additional_candidate_target=1,
        seed=42,
        sampled_at="new",
    )

    assert count == 2
    assert (output_dir / "expanded_market_validation_sample.csv").exists()
    assert (output_dir / "expanded_market_validation_sample.xlsx").exists()
    assert (output_dir / "expanded_market_validation_sample_metadata.csv").exists()
    assert (output_dir / "expanded_market_validation_sample_metadata.xlsx").exists()
    with (output_dir / "expanded_market_validation_sample_metadata.csv").open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        list(reader)
    assert reader.fieldnames == EXPANDED_MARKET_VALIDATION_METADATA_FIELDNAMES


def test_expanded_collection_reuses_existing_observations_and_queries_only_new_books(tmp_path):
    output_dir = tmp_path / "output"
    existing = sample("BK001", "1", "0-1", "missing_oclc")
    new = sample("BK002", "8", "8-10", "university_press")
    write_rows(output_dir / "market_validation_sample.csv", MARKET_VALIDATION_SAMPLE_FIELDNAMES, [existing])
    write_rows(
        output_dir / "expanded_market_validation_sample.csv",
        MARKET_VALIDATION_SAMPLE_FIELDNAMES,
        [existing, new],
    )
    write_rows(output_dir / "market_observations.csv", observation_fields(), [existing_observation()])
    requested_urls = []

    count = collect_expanded_abebooks_observations(
        output_dir,
        limit=1,
        delay=0,
        fetch_html=lambda url: requested_urls.append(url) or LISTING_HTML,
        observation_date="new",
        sleep=lambda _seconds: None,
    )

    assert count == 2
    assert len(requested_urls) == 1
    assert "978002" in requested_urls[0]
    with (output_dir / "expanded_market_observations.csv").open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    assert {row["catalog_id"] for row in rows} == {"BK001", "BK002"}
    assert (output_dir / "expanded_market_observations.xlsx").exists()


def test_expanded_sample_command_wiring(capsys, monkeypatch, tmp_path):
    calls = []

    def fake_generate(output_dir, data_dir, additional_candidate_target, seed):
        calls.append((output_dir, data_dir, additional_candidate_target, seed))
        return 205

    monkeypatch.setattr(library_pipeline, "generate_expanded_market_validation_sample", fake_generate)

    result = main([
        "generate-expanded-market-validation-sample",
        "--output-dir", str(tmp_path / "output"),
        "--data-dir", str(tmp_path / "data"),
        "--additional-candidate-target", "140",
        "--seed", "7",
    ])

    assert result == 0
    assert calls == [(tmp_path / "output", tmp_path / "data", 140, 7)]
    assert "Wrote 205 expanded market validation sample rows" in capsys.readouterr().out


def test_expanded_collection_command_wiring(capsys, monkeypatch, tmp_path):
    calls = []

    def fake_collect(output_dir, limit, delay, max_results_per_book):
        calls.append((output_dir, limit, delay, max_results_per_book))
        return 300

    monkeypatch.setattr(library_pipeline, "collect_expanded_abebooks_observations", fake_collect)

    result = main([
        "collect-expanded-abebooks-observations",
        "--output-dir", str(tmp_path),
        "--limit", "140",
        "--delay", "0",
        "--max-results-per-book", "2",
    ])

    assert result == 0
    assert calls == [(tmp_path, 140, 0.0, 2)]
    assert "Wrote 300 expanded AbeBooks observation rows" in capsys.readouterr().out


def sample(catalog_id, score, band, signals, sampled_at="old"):
    return {
        "catalog_id": catalog_id,
        "title": f"Title {catalog_id}",
        "author": "Author",
        "isbn10": "",
        "isbn13": catalog_id.replace("BK", "978"),
        "asin": "",
        "publisher": "Press",
        "publication_year": "2000",
        "research_score": score,
        "score_band": band,
        "triggered_signals": signals,
        "sample_seed": "7",
        "sampled_at": sampled_at,
    }


def catalog_row(catalog_id):
    return {
        "catalog_item_id": catalog_id,
        "title": f"Title {catalog_id}",
        "authors": "Author",
        "isbn13": catalog_id.replace("BK", "978"),
    }


def assessment(catalog_id, score, signals, version="", config_hash=""):
    return {
        "catalog_item_id": catalog_id,
        "isbn13": catalog_id.replace("BK", "978"),
        "research_priority_score": score,
        "research_signal_codes": signals,
        "research_model_version": version,
        "research_config_hash": config_hash,
    }


def existing_observation():
    return {field: value for field, value in {
        "catalog_id": "BK001",
        "lookup_status": "observed",
        "asking_price": "10.00",
        "source": "abebooks",
    }.items()}


def catalog_fields():
    return ["catalog_item_id", "title", "authors", "isbn13"]


def assessment_fields():
    return [
        "catalog_item_id", "isbn13", "research_priority_score", "research_signal_codes",
        "research_model_version", "research_config_hash",
    ]


def observation_fields():
    from valuation.abebooks import MARKET_OBSERVATION_FIELDNAMES

    return MARKET_OBSERVATION_FIELDNAMES


def write_rows(path, fieldnames, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

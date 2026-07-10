"""Market validation sample generation."""

from __future__ import annotations

import hashlib
import random
from collections import Counter
from collections.abc import Iterable, Mapping

from valuation.research_candidates import stable_join


MARKET_VALIDATION_SAMPLE_FIELDNAMES = [
    "catalog_id",
    "title",
    "author",
    "isbn10",
    "isbn13",
    "asin",
    "publisher",
    "publication_year",
    "research_score",
    "score_band",
    "triggered_signals",
    "sample_seed",
    "sampled_at",
]

MARKET_VALIDATION_SAMPLE_METADATA_FIELDNAMES = [
    "score_band",
    "target_sample_count",
    "available_population_count",
    "actual_sample_count",
    "sample_seed",
    "sampled_at",
    "research_model_version",
    "research_config_hash",
    "total_available_population_count",
    "total_sample_count",
]

EXPANDED_MARKET_VALIDATION_METADATA_FIELDNAMES = [
    "score_band",
    "available_population_count",
    "existing_sample_count",
    "available_additional_population_count",
    "additional_selected_count",
    "expanded_sample_count",
    "balanced_target_floor_count",
    "score_band_deficit_count",
    "population_exhausted",
    "target_additional_candidates",
    "actual_additional_candidates",
    "existing_total_sample_count",
    "expanded_total_sample_count",
    "sample_seed",
    "sampled_at",
    "research_model_version",
    "research_config_hash",
]

SCORE_BANDS = ("0-1", "2-3", "4-5", "6-7", "8-10")
SCORE_BAND_ORDER = {band: index for index, band in enumerate(SCORE_BANDS)}

CALIBRATION_SIGNAL_PRIORITY = {
    "old_publication_year": 5,
    "specialist_publisher": 5,
    "low_metadata_confidence": 4,
    "multiple_acquisitions": 4,
    "scholarly_lc_subject": 3,
    "missing_oclc": 2,
    "missing_lcc": 2,
}

CALIBRATION_SIGNAL_COMBINATIONS = (
    frozenset({"university_press", "scholarly_lc_subject"}),
    frozenset({"old_publication_year", "specialist_publisher"}),
    frozenset({"old_publication_year", "low_metadata_confidence"}),
    frozenset({"multiple_acquisitions", "scholarly_lc_subject"}),
)


def score_band_for_score(score: str | int) -> str:
    score_value = integer_value(score)
    if score_value <= 1:
        return "0-1"
    if score_value <= 3:
        return "2-3"
    if score_value <= 5:
        return "4-5"
    if score_value <= 7:
        return "6-7"
    return "8-10"


def build_market_validation_sample_rows(
    catalog_rows: Iterable[Mapping[str, str]],
    assessment_rows: Iterable[Mapping[str, str]],
    *,
    catalog_item_rows: Iterable[Mapping[str, str]] | None = None,
    acquisition_rows: Iterable[Mapping[str, str]] | None = None,
    sample_size_per_band: int = 20,
    seed: int = 42,
    sampled_at: str = "",
) -> list[dict[str, str]]:
    if sample_size_per_band < 1:
        raise ValueError("sample_size_per_band must be at least 1")

    catalog_by_id = index_first_by_catalog_id(catalog_rows)
    catalog_items_by_id = index_first_by_catalog_id(catalog_item_rows or [])
    asins_by_id = source_asins_by_catalog_id(acquisition_rows or [])
    candidates_by_band = {band: [] for band in SCORE_BANDS}

    for assessment in assessment_rows:
        catalog_id = assessment.get("catalog_item_id", "")
        if not catalog_id:
            continue
        catalog = catalog_by_id.get(catalog_id, {})
        catalog_item = catalog_items_by_id.get(catalog_id, {})
        score = assessment.get("research_priority_score", "")
        band = score_band_for_score(score)
        candidates_by_band[band].append(
            {
                "catalog_id": catalog_id,
                "title": first_present(catalog, catalog_item, "title"),
                "author": first_present(catalog, catalog_item, "authors", "author"),
                "isbn10": first_present(catalog, catalog_item, assessment, "isbn10"),
                "isbn13": first_present(catalog, catalog_item, assessment, "isbn13"),
                "asin": asins_by_id.get(catalog_id, "") or first_present(catalog, catalog_item, "asin", "source_asins"),
                "publisher": first_present(catalog_item, catalog, "publisher", "publishers"),
                "publication_year": first_present(catalog_item, catalog, "publication_year"),
                "research_score": str(integer_value(score)),
                "score_band": band,
                "triggered_signals": triggered_signals(assessment),
                "sample_seed": str(seed),
                "sampled_at": sampled_at,
            }
        )

    rng = random.Random(seed)
    selected_rows = []
    for band in SCORE_BANDS:
        band_rows = sorted(candidates_by_band[band], key=stable_sample_sort_key)
        sample_size = min(sample_size_per_band, len(band_rows))
        if sample_size == len(band_rows):
            selected_rows.extend(band_rows)
        else:
            selected_rows.extend(sorted(rng.sample(band_rows, sample_size), key=stable_sample_sort_key))

    return sorted(selected_rows, key=sample_output_sort_key)


def build_market_validation_sample_metadata_rows(
    sample_rows: Iterable[Mapping[str, str]],
    assessment_rows: Iterable[Mapping[str, str]],
    *,
    sample_size_per_band: int = 20,
    seed: int = 42,
    sampled_at: str = "",
) -> list[dict[str, str]]:
    if sample_size_per_band < 1:
        raise ValueError("sample_size_per_band must be at least 1")

    sample_rows = list(sample_rows)
    assessment_rows = list(assessment_rows)
    population_counts = {band: 0 for band in SCORE_BANDS}
    sample_counts = {band: 0 for band in SCORE_BANDS}
    model_versions = set()
    config_hashes = set()

    for assessment in assessment_rows:
        population_counts[score_band_for_score(assessment.get("research_priority_score", ""))] += 1
        model_version = assessment.get("research_model_version", "").strip()
        config_hash = assessment.get("research_config_hash", "").strip()
        if model_version:
            model_versions.add(model_version)
        if config_hash:
            config_hashes.add(config_hash)

    for row in sample_rows:
        band = row.get("score_band", "")
        if band in sample_counts:
            sample_counts[band] += 1

    total_population = sum(population_counts.values())
    total_sample = sum(sample_counts.values())
    return [
        {
            "score_band": band,
            "target_sample_count": str(sample_size_per_band),
            "available_population_count": str(population_counts[band]),
            "actual_sample_count": str(sample_counts[band]),
            "sample_seed": str(seed),
            "sampled_at": sampled_at,
            "research_model_version": stable_join(model_versions),
            "research_config_hash": stable_join(config_hashes),
            "total_available_population_count": str(total_population),
            "total_sample_count": str(total_sample),
        }
        for band in SCORE_BANDS
    ]


def build_expanded_market_validation_sample_rows(
    existing_sample_rows: Iterable[Mapping[str, str]],
    catalog_rows: Iterable[Mapping[str, str]],
    assessment_rows: Iterable[Mapping[str, str]],
    *,
    catalog_item_rows: Iterable[Mapping[str, str]] | None = None,
    acquisition_rows: Iterable[Mapping[str, str]] | None = None,
    additional_candidate_target: int = 140,
    seed: int = 42,
    sampled_at: str = "",
) -> list[dict[str, str]]:
    if additional_candidate_target < 1:
        raise ValueError("additional_candidate_target must be at least 1")

    existing = deduplicate_sample_rows(existing_sample_rows)
    existing_ids = {row.get("catalog_id", "") for row in existing}
    assessments = list(assessment_rows)
    all_candidates = build_market_validation_sample_rows(
        catalog_rows,
        assessments,
        catalog_item_rows=catalog_item_rows,
        acquisition_rows=acquisition_rows,
        sample_size_per_band=max(1, len(assessments)),
        seed=seed,
        sampled_at=sampled_at,
    )
    candidates_by_band = {band: [] for band in SCORE_BANDS}
    for row in all_candidates:
        if row.get("catalog_id", "") not in existing_ids:
            candidates_by_band[row["score_band"]].append(row)
    for band in SCORE_BANDS:
        candidates_by_band[band].sort(key=lambda row: calibration_candidate_sort_key(row, seed))

    expanded_counts = Counter(row.get("score_band", "") for row in existing)
    selected = []
    while len(selected) < additional_candidate_target:
        available_bands = [band for band in SCORE_BANDS if candidates_by_band[band]]
        if not available_bands:
            break
        band = min(available_bands, key=lambda value: (expanded_counts[value], SCORE_BAND_ORDER[value]))
        selected.append(candidates_by_band[band].pop(0))
        expanded_counts[band] += 1

    return sorted(existing + selected, key=sample_output_sort_key)


def build_expanded_market_validation_metadata_rows(
    expanded_sample_rows: Iterable[Mapping[str, str]],
    existing_sample_rows: Iterable[Mapping[str, str]],
    assessment_rows: Iterable[Mapping[str, str]],
    *,
    additional_candidate_target: int = 140,
    seed: int = 42,
    sampled_at: str = "",
) -> list[dict[str, str]]:
    expanded = deduplicate_sample_rows(expanded_sample_rows)
    existing = deduplicate_sample_rows(existing_sample_rows)
    assessments = list(assessment_rows)
    population_counts = Counter(
        score_band_for_score(row.get("research_priority_score", ""))
        for row in assessments
        if row.get("catalog_item_id", "")
    )
    existing_counts = Counter(row.get("score_band", "") for row in existing)
    expanded_counts = Counter(row.get("score_band", "") for row in expanded)
    additional_counts = {
        band: max(0, expanded_counts[band] - existing_counts[band])
        for band in SCORE_BANDS
    }
    actual_additional = len(expanded) - len(existing)
    balanced_target_floor = (len(existing) + additional_candidate_target) // len(SCORE_BANDS)
    model_versions = {
        row.get("research_model_version", "").strip()
        for row in assessments
        if row.get("research_model_version", "").strip()
    }
    config_hashes = {
        row.get("research_config_hash", "").strip()
        for row in assessments
        if row.get("research_config_hash", "").strip()
    }
    return [
        {
            "score_band": band,
            "available_population_count": str(population_counts[band]),
            "existing_sample_count": str(existing_counts[band]),
            "available_additional_population_count": str(max(0, population_counts[band] - existing_counts[band])),
            "additional_selected_count": str(additional_counts[band]),
            "expanded_sample_count": str(expanded_counts[band]),
            "balanced_target_floor_count": str(balanced_target_floor),
            "score_band_deficit_count": str(max(0, balanced_target_floor - expanded_counts[band])),
            "population_exhausted": yes_no(expanded_counts[band] >= population_counts[band]),
            "target_additional_candidates": str(additional_candidate_target),
            "actual_additional_candidates": str(actual_additional),
            "existing_total_sample_count": str(len(existing)),
            "expanded_total_sample_count": str(len(expanded)),
            "sample_seed": str(seed),
            "sampled_at": sampled_at,
            "research_model_version": stable_join(model_versions),
            "research_config_hash": stable_join(config_hashes),
        }
        for band in SCORE_BANDS
    ]


def deduplicate_sample_rows(rows: Iterable[Mapping[str, str]]) -> list[dict[str, str]]:
    indexed = {}
    for row in rows:
        row_id = row.get("catalog_id", "") or row.get("catalog_item_id", "")
        if row_id and row_id not in indexed:
            indexed[row_id] = {field: row.get(field, "") for field in MARKET_VALIDATION_SAMPLE_FIELDNAMES}
    return list(indexed.values())


def calibration_candidate_sort_key(row: Mapping[str, str], seed: int) -> tuple[int, str, tuple[str, str, str]]:
    signals = frozenset(signal.strip() for signal in row.get("triggered_signals", "").split(";") if signal.strip())
    priority = sum(CALIBRATION_SIGNAL_PRIORITY.get(signal, 0) for signal in signals)
    priority += 6 * sum(1 for combination in CALIBRATION_SIGNAL_COMBINATIONS if combination <= signals)
    tie_breaker = hashlib.sha256(f"{seed}:{row.get('catalog_id', '')}".encode("utf-8")).hexdigest()
    return (-priority, tie_breaker, stable_sample_sort_key(row))


def triggered_signals(assessment: Mapping[str, str]) -> str:
    raw_codes = assessment.get("research_signal_codes", "")
    codes = [code.strip() for code in raw_codes.split(";") if code.strip()]
    return ";".join(codes)


def index_first_by_catalog_id(rows: Iterable[Mapping[str, str]]) -> dict[str, Mapping[str, str]]:
    indexed = {}
    for row in sorted(rows, key=stable_input_sort_key):
        catalog_id = row.get("catalog_item_id", "") or row.get("catalog_id", "")
        if catalog_id and catalog_id not in indexed:
            indexed[catalog_id] = row
    return indexed


def source_asins_by_catalog_id(rows: Iterable[Mapping[str, str]]) -> dict[str, str]:
    grouped: dict[str, list[str]] = {}
    for row in rows:
        catalog_id = row.get("catalog_item_id", "") or row.get("catalog_id", "")
        asin = row.get("source_asin", "") or row.get("asin", "")
        if catalog_id and asin:
            grouped.setdefault(catalog_id, []).append(asin)
    return {catalog_id: stable_join(asins) for catalog_id, asins in grouped.items()}


def stable_input_sort_key(row: Mapping[str, str]) -> tuple[str, str, str]:
    return (
        row.get("catalog_item_id", "") or row.get("catalog_id", ""),
        row.get("title", "") or row.get("product_name", ""),
        row.get("isbn13", ""),
    )


def stable_sample_sort_key(row: Mapping[str, str]) -> tuple[str, str, str]:
    return (
        row.get("catalog_id", ""),
        row.get("title", "").casefold(),
        row.get("isbn13", ""),
    )


def sample_output_sort_key(row: Mapping[str, str]) -> tuple[int, str, str, str]:
    return (
        SCORE_BAND_ORDER.get(row.get("score_band", ""), 99),
        row.get("catalog_id", ""),
        row.get("title", "").casefold(),
        row.get("isbn13", ""),
    )


def first_present(*sources: Mapping[str, str] | str) -> str:
    field_names = [source for source in sources if isinstance(source, str)]
    mappings = [source for source in sources if isinstance(source, Mapping)]
    for field_name in field_names:
        for mapping in mappings:
            value = mapping.get(field_name, "")
            if value:
                return value
    return ""


def integer_value(value: str | int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def yes_no(value: bool) -> str:
    return "yes" if value else "no"

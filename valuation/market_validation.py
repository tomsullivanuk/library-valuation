"""Market validation sample generation."""

from __future__ import annotations

import random
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

SCORE_BANDS = ("0-1", "2-3", "4-5", "6-7", "8-10")
SCORE_BAND_ORDER = {band: index for index, band in enumerate(SCORE_BANDS)}


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

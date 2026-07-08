"""Collector-facing Research Candidate output rows."""

from __future__ import annotations

from collections.abc import Iterable, Mapping


RESEARCH_CANDIDATE_FIELDNAMES = [
    "catalog_item_id",
    "isbn13",
    "title",
    "authors",
    "publisher",
    "publication_year",
    "research_priority_score",
    "research_priority_band",
    "research_signal_count",
    "research_signal_codes",
    "research_signal_summary",
    "research_signal_explanations",
    "acquisition_count",
    "first_acquired_date",
    "latest_acquired_date",
    "source_asins",
    "source_order_ids",
    "metadata_source",
    "metadata_confidence",
    "lcc",
    "oclc",
    "subjects",
    "openlibrary_work_key",
    "openlibrary_edition_key",
]

DEFAULT_INCLUDED_BANDS = ("high", "medium", "low")
BAND_SORT_ORDER = {"high": 0, "medium": 1, "low": 2, "none": 3}


def build_research_candidate_rows(
    catalog_items: Iterable[Mapping[str, str]],
    metadata_rows: Iterable[Mapping[str, str]],
    acquisitions: Iterable[Mapping[str, str]],
    research_assessments: Iterable[Mapping[str, str]],
    included_bands: Iterable[str] = DEFAULT_INCLUDED_BANDS,
) -> list[dict[str, str]]:
    """Build output-only Research Candidate rows from current durable state."""
    catalog_by_id = index_by_catalog_item_id(catalog_items)
    metadata_by_id = index_by_catalog_item_id(metadata_rows)
    acquisitions_by_id = group_by_catalog_item_id(acquisitions)
    included_band_set = set(included_bands)
    candidates = []
    for assessment in research_assessments:
        catalog_item_id = assessment.get("catalog_item_id", "")
        band = assessment.get("research_priority_band", "")
        if not catalog_item_id or band not in included_band_set:
            continue
        catalog_item = catalog_by_id.get(catalog_item_id, {})
        metadata = metadata_by_id.get(catalog_item_id, {})
        acquisition_rows = acquisitions_by_id.get(catalog_item_id, [])
        candidates.append(
            build_research_candidate_row(
                catalog_item,
                metadata,
                acquisition_rows,
                assessment,
            )
        )
    return sorted(candidates, key=research_candidate_sort_key)


def build_research_candidate_row(
    catalog_item: Mapping[str, str],
    metadata: Mapping[str, str],
    acquisitions: Iterable[Mapping[str, str]],
    assessment: Mapping[str, str],
) -> dict[str, str]:
    acquisition_summary = summarize_acquisitions(acquisitions)
    return {
        "catalog_item_id": first_present(assessment, metadata, catalog_item, "catalog_item_id"),
        "isbn13": first_present(assessment, metadata, catalog_item, "isbn13"),
        "title": first_present(metadata, catalog_item, "title"),
        "authors": metadata.get("authors") or catalog_item.get("author", ""),
        "publisher": metadata.get("publishers") or catalog_item.get("publisher", ""),
        "publication_year": publication_year(metadata, catalog_item),
        "research_priority_score": assessment.get("research_priority_score", ""),
        "research_priority_band": assessment.get("research_priority_band", ""),
        "research_signal_count": assessment.get("research_signal_count", ""),
        "research_signal_codes": assessment.get("research_signal_codes", ""),
        "research_signal_summary": assessment.get("research_signal_summary", ""),
        "research_signal_explanations": assessment.get("research_signal_explanations", ""),
        "acquisition_count": acquisition_summary["acquisition_count"],
        "first_acquired_date": acquisition_summary["first_acquired_date"],
        "latest_acquired_date": acquisition_summary["latest_acquired_date"],
        "source_asins": acquisition_summary["source_asins"],
        "source_order_ids": acquisition_summary["source_order_ids"],
        "metadata_source": metadata_source(metadata, catalog_item),
        "metadata_confidence": metadata_confidence(metadata, catalog_item),
        "lcc": metadata.get("lcc", ""),
        "oclc": metadata.get("oclc", ""),
        "subjects": metadata.get("subjects", ""),
        "openlibrary_work_key": metadata.get("openlibrary_work_key", ""),
        "openlibrary_edition_key": metadata.get("openlibrary_edition_key", ""),
    }


def summarize_acquisitions(acquisitions: Iterable[Mapping[str, str]]) -> dict[str, str]:
    rows = list(acquisitions)
    order_dates = sorted(value for row in rows if (value := row.get("order_date", "")))
    return {
        "acquisition_count": str(len(rows)),
        "first_acquired_date": order_dates[0] if order_dates else "",
        "latest_acquired_date": order_dates[-1] if order_dates else "",
        "source_asins": stable_join(row.get("source_asin", "") for row in rows),
        "source_order_ids": stable_join(row.get("source_order_id", "") for row in rows),
    }


def research_candidate_sort_key(row: Mapping[str, str]) -> tuple[int, int, int, int, str, str]:
    return (
        BAND_SORT_ORDER.get(row.get("research_priority_band", ""), 99),
        -integer_value(row.get("research_priority_score", "")),
        -integer_value(row.get("research_signal_count", "")),
        publication_year_sort_value(row.get("publication_year", "")),
        row.get("title", "").casefold(),
        row.get("catalog_item_id", ""),
    )


def index_by_catalog_item_id(rows: Iterable[Mapping[str, str]]) -> dict[str, Mapping[str, str]]:
    indexed = {}
    for row in rows:
        catalog_item_id = row.get("catalog_item_id", "")
        if catalog_item_id:
            indexed[catalog_item_id] = row
    return indexed


def group_by_catalog_item_id(rows: Iterable[Mapping[str, str]]) -> dict[str, list[Mapping[str, str]]]:
    grouped: dict[str, list[Mapping[str, str]]] = {}
    for row in rows:
        catalog_item_id = row.get("catalog_item_id", "")
        if catalog_item_id:
            grouped.setdefault(catalog_item_id, []).append(row)
    return grouped


def first_present(*sources: Mapping[str, str] | str) -> str:
    field = str(sources[-1])
    for source in sources[:-1]:
        if isinstance(source, Mapping) and source.get(field):
            return source[field]
    return ""


def publication_year(metadata: Mapping[str, str], catalog_item: Mapping[str, str]) -> str:
    return first_year(metadata.get("publish_date", "")) or catalog_item.get("publication_year", "")


def first_year(value: str) -> str:
    for part in value.replace(",", " ").split():
        digits = "".join(character for character in part if character.isdigit())
        if len(digits) == 4:
            return digits
    return ""


def metadata_source(metadata: Mapping[str, str], catalog_item: Mapping[str, str]) -> str:
    return (
        metadata.get("resolution_source")
        or metadata.get("openlibrary_status")
        or ("catalog" if catalog_item else "")
    )


def metadata_confidence(metadata: Mapping[str, str], catalog_item: Mapping[str, str]) -> str:
    return (
        metadata.get("resolution_confidence")
        or metadata.get("match_confidence")
        or catalog_item.get("match_confidence", "")
    )


def stable_join(values: Iterable[str]) -> str:
    return "; ".join(sorted({value for value in values if value}))


def integer_value(value: str) -> int:
    try:
        return int(value)
    except ValueError:
        return 0


def publication_year_sort_value(value: str) -> int:
    year = integer_value(value)
    return year if year else 9999

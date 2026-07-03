"""Workbook-facing helpers for future valuation exports."""

from __future__ import annotations

from collections.abc import Iterable, Mapping


VALUATION_FIELDNAMES = [
    "isbn13",
    "title",
    "authors",
    "publishers",
    "lcc",
    "subjects",
    "rps_score",
    "valuation_notes",
]


def valuation_fieldnames() -> list[str]:
    """Return the planned valuation workbook column order."""
    return list(VALUATION_FIELDNAMES)


def build_valuation_rows(catalog_rows: Iterable[Mapping[str, str]]) -> list[dict[str, str]]:
    """Create placeholder valuation rows from catalog rows.

    The row shape is intentionally stable, but score generation is deferred to a
    later sprint. Existing pipeline outputs do not call this helper yet.
    """
    rows = []
    for row in catalog_rows:
        rows.append(
            {
                "isbn13": row.get("isbn13", ""),
                "title": row.get("title", ""),
                "authors": row.get("authors", ""),
                "publishers": row.get("publishers", ""),
                "lcc": row.get("lcc", ""),
                "subjects": row.get("subjects", ""),
                "rps_score": "",
                "valuation_notes": "",
            }
        )
    return rows


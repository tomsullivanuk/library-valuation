"""Coverage reporting for generated market observations."""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable, Mapping


MARKET_OBSERVATION_COVERAGE_FIELDNAMES = [
    "section",
    "metric",
    "count",
    "percentage",
    "source",
    "lookup_status",
    "lookup_strategy",
    "match_confidence",
    "diagnostic_code",
    "match_notes",
    "raw_reference",
]


LOOKUP_STATUSES = ("observed", "no_results", "source_unavailable", "no_query")
LOOKUP_STRATEGIES = ("isbn13", "isbn10", "title_author")
MATCH_CONFIDENCES = ("high", "medium", "low", "unknown")


def build_market_observation_coverage_rows(
    sample_rows: Iterable[Mapping[str, str]],
    observation_rows: Iterable[Mapping[str, str]],
) -> list[dict[str, str]]:
    samples = list(sample_rows)
    observations = list(observation_rows)
    rows = summary_rows(samples, observations)
    rows.extend(diagnostic_detail_rows(observations))
    return rows


def summary_rows(
    sample_rows: list[Mapping[str, str]],
    observation_rows: list[Mapping[str, str]],
) -> list[dict[str, str]]:
    sampled_books = len({catalog_id(row) for row in sample_rows if catalog_id(row)})
    attempted_books = len({catalog_id(row) for row in observation_rows if catalog_id(row)})
    observed_books = len(
        {
            catalog_id(row)
            for row in observation_rows
            if catalog_id(row) and row.get("lookup_status", "") == "observed"
        }
    )
    observation_count = len(observation_rows)
    statuses = Counter(row.get("lookup_status", "") for row in observation_rows)
    strategies = Counter(row.get("lookup_strategy", "") for row in observation_rows)
    confidences = Counter(row.get("match_confidence", "") for row in observation_rows)
    sources = sorted({row.get("source", "") for row in observation_rows if row.get("source", "")})

    rows = [
        metric_row("sampled_books", sampled_books),
        metric_row("books_attempted", attempted_books, sampled_books),
        metric_row("observation_rows", observation_count),
        metric_row("books_with_observed_listings", observed_books, sampled_books),
    ]
    rows.extend(
        metric_row(f"{status}_count", statuses.get(status, 0), observation_count)
        for status in LOOKUP_STATUSES
    )
    rows.extend(
        metric_row(f"lookup_strategy_{strategy}_count", strategies.get(strategy, 0), observation_count)
        for strategy in LOOKUP_STRATEGIES
    )
    rows.extend(
        metric_row(
            f"match_confidence_{confidence}_count",
            confidences.get(confidence, 0),
            observation_count,
        )
        for confidence in MATCH_CONFIDENCES
    )
    rows.append(metric_row("unique_sources", len(sources), notes=", ".join(sources)))
    return rows


def diagnostic_detail_rows(observation_rows: list[Mapping[str, str]]) -> list[dict[str, str]]:
    observation_count = len(observation_rows)
    grouped = Counter(
        (
            row.get("source", ""),
            row.get("lookup_status", ""),
            row.get("lookup_strategy", ""),
            row.get("match_confidence", ""),
            row.get("diagnostic_code", ""),
            row.get("match_notes", ""),
            row.get("raw_reference", ""),
        )
        for row in observation_rows
        if row.get("lookup_status", "") != "observed"
    )
    rows = []
    for (
        source,
        lookup_status,
        lookup_strategy,
        match_confidence,
        diagnostic_code,
        match_notes,
        raw_reference,
    ), count in sorted(grouped.items()):
        rows.append(
            {
                "section": "diagnostic_detail",
                "metric": "lookup_failure",
                "count": str(count),
                "percentage": percentage(count, observation_count),
                "source": source,
                "lookup_status": lookup_status,
                "lookup_strategy": lookup_strategy,
                "match_confidence": match_confidence,
                "diagnostic_code": diagnostic_code,
                "match_notes": match_notes,
                "raw_reference": raw_reference,
            }
        )
    return rows


def metric_row(metric: str, count: int, denominator: int | None = None, notes: str = "") -> dict[str, str]:
    return {
        "section": "summary",
        "metric": metric,
        "count": str(count),
        "percentage": percentage(count, denominator) if denominator is not None else "",
        "source": notes if metric == "unique_sources" else "",
        "lookup_status": "",
        "lookup_strategy": "",
        "match_confidence": "",
        "diagnostic_code": "",
        "match_notes": "",
        "raw_reference": "",
    }


def percentage(count: int, denominator: int | None) -> str:
    if not denominator:
        return ""
    return f"{count / denominator:.1%}"


def catalog_id(row: Mapping[str, str]) -> str:
    return row.get("catalog_id", "") or row.get("catalog_item_id", "")

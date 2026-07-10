"""Market validation analysis for Research Assessment signals."""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable, Mapping
from statistics import median

from valuation.market_validation import SCORE_BANDS


MARKET_VALIDATION_ANALYSIS_FIELDNAMES = [
    "section",
    "metric",
    "value",
    "percentage",
    "score_band",
    "signal",
    "catalog_id",
    "title",
    "author",
    "research_score",
    "triggered_signals",
    "catalog_population_count",
    "catalog_population_percentage",
    "validation_sample_count",
    "validation_sample_percentage",
    "empty_band",
    "underrepresented_band",
    "books",
    "books_with_observations",
    "observation_rows",
    "observation_coverage_rate",
    "average_observations_per_book",
    "median_asking_price",
    "average_asking_price",
    "maximum_asking_price",
    "price_summary",
    "notes",
]


LOW_SCORE_BANDS = {"0-1"}
HIGH_SCORE_BANDS = {"8-10"}


def build_market_validation_analysis_rows(
    sample_rows: Iterable[Mapping[str, str]],
    observation_rows: Iterable[Mapping[str, str]],
    metadata_rows: Iterable[Mapping[str, str]],
) -> list[dict[str, str]]:
    samples = list(sample_rows)
    observations = list(observation_rows)
    metadata = list(metadata_rows)
    observations_by_catalog_id = group_observations_by_catalog_id(observations)
    book_summaries = {
        catalog_id(row): book_market_summary(row, observations_by_catalog_id.get(catalog_id(row), []))
        for row in samples
        if catalog_id(row)
    }
    sample_max_prices = [
        summary["maximum_asking_price_number"]
        for summary in book_summaries.values()
        if summary["maximum_asking_price_number"] is not None
    ]
    relative_price_cutoff = median(sample_max_prices) if sample_max_prices else None

    rows: list[dict[str, str]] = []
    rows.extend(score_distribution_rows(metadata))
    rows.extend(dataset_summary_rows(samples, observations, book_summaries))
    rows.extend(score_band_market_rows(samples, book_summaries))
    rows.extend(research_signal_rows(samples, book_summaries))
    rows.extend(false_positive_rows(samples, book_summaries, relative_price_cutoff))
    rows.extend(false_negative_rows(samples, book_summaries, relative_price_cutoff))
    return rows


def score_distribution_rows(metadata_rows: list[Mapping[str, str]]) -> list[dict[str, str]]:
    total_population = sum(integer_value(row.get("available_population_count", "")) for row in metadata_rows)
    total_sample = sum(integer_value(row.get("actual_sample_count", "")) for row in metadata_rows)
    rows = []
    for band in SCORE_BANDS:
        metadata = next((row for row in metadata_rows if row.get("score_band", "") == band), {})
        population_count = integer_value(metadata.get("available_population_count", ""))
        sample_count = integer_value(metadata.get("actual_sample_count", ""))
        target_count = integer_value(metadata.get("target_sample_count", ""))
        empty_band = population_count == 0
        underrepresented = sample_count < target_count
        notes = []
        if empty_band:
            notes.append("No catalog population in this Research Score band.")
        elif underrepresented:
            notes.append("Validation sample includes all available books below target count.")
        rows.append(
            base_row(
                section="score_distribution",
                score_band=band,
                catalog_population_count=str(population_count),
                catalog_population_percentage=percentage(population_count, total_population),
                validation_sample_count=str(sample_count),
                validation_sample_percentage=percentage(sample_count, total_sample),
                empty_band=yes_no(empty_band),
                underrepresented_band=yes_no(underrepresented),
                notes=" ".join(notes),
            )
        )
    return rows


def dataset_summary_rows(
    sample_rows: list[Mapping[str, str]],
    observation_rows: list[Mapping[str, str]],
    book_summaries: Mapping[str, Mapping[str, object]],
) -> list[dict[str, str]]:
    sampled_books = len({catalog_id(row) for row in sample_rows if catalog_id(row)})
    books_with_observations = sum(1 for summary in book_summaries.values() if summary["books_with_observations"])
    observed_rows = sum(1 for row in observation_rows if row.get("lookup_status", "") == "observed")
    signal_counts = Counter(
        signal
        for row in sample_rows
        for signal in triggered_signals(row)
    )
    return [
        metric_row("total_books_sampled", sampled_books),
        metric_row("score_bands_present", len({row.get("score_band", "") for row in sample_rows if row.get("score_band", "")})),
        metric_row("unique_triggered_signals", len(signal_counts)),
        metric_row("books_with_abebooks_observations", books_with_observations, sampled_books),
        metric_row("books_without_abebooks_observations", sampled_books - books_with_observations, sampled_books),
        metric_row("total_observation_rows", len(observation_rows)),
        metric_row("observed_listing_rows", observed_rows),
        metric_row(
            "average_observed_listings_per_book",
            format_decimal(observed_rows / sampled_books) if sampled_books else "0.00",
            notes="Uses observed listing rows only, not no-results or source-diagnostic rows.",
        ),
        metric_row("observation_coverage_rate", books_with_observations, sampled_books),
    ]


def score_band_market_rows(
    sample_rows: list[Mapping[str, str]],
    book_summaries: Mapping[str, Mapping[str, object]],
) -> list[dict[str, str]]:
    rows = []
    for band in SCORE_BANDS:
        band_samples = [row for row in sample_rows if row.get("score_band", "") == band]
        summaries = [book_summaries[catalog_id(row)] for row in band_samples if catalog_id(row) in book_summaries]
        rows.append(aggregate_row("score_band_market_analysis", summaries, score_band=band))
    return rows


def research_signal_rows(
    sample_rows: list[Mapping[str, str]],
    book_summaries: Mapping[str, Mapping[str, object]],
) -> list[dict[str, str]]:
    rows = []
    sample_count = len(sample_rows)
    signals = sorted({signal for row in sample_rows for signal in triggered_signals(row)})
    for signal in signals:
        signal_samples = [row for row in sample_rows if signal in triggered_signals(row)]
        summaries = [book_summaries[catalog_id(row)] for row in signal_samples if catalog_id(row) in book_summaries]
        row = aggregate_row("research_signal_analysis", summaries, signal=signal)
        row["percentage"] = percentage(len(signal_samples), sample_count)
        rows.append(row)
    return rows


def false_positive_rows(
    sample_rows: list[Mapping[str, str]],
    book_summaries: Mapping[str, Mapping[str, object]],
    relative_price_cutoff: float | None,
) -> list[dict[str, str]]:
    candidates = []
    for row in sample_rows:
        if row.get("score_band", "") not in HIGH_SCORE_BANDS:
            continue
        summary = book_summaries.get(catalog_id(row))
        if not summary:
            continue
        maximum_price = summary["maximum_asking_price_number"]
        if maximum_price is None or (relative_price_cutoff is not None and maximum_price <= relative_price_cutoff):
            candidates.append((row, summary))
    candidates.sort(
        key=lambda item: (
            item[1]["maximum_asking_price_number"] is not None,
            item[1]["maximum_asking_price_number"] or 0,
            item[0].get("research_score", ""),
            item[0].get("title", "").casefold(),
        )
    )
    return [
        book_detail_row("false_positive_candidate", row, summary, relative_price_cutoff)
        for row, summary in candidates[:10]
    ]


def false_negative_rows(
    sample_rows: list[Mapping[str, str]],
    book_summaries: Mapping[str, Mapping[str, object]],
    relative_price_cutoff: float | None,
) -> list[dict[str, str]]:
    if relative_price_cutoff is None:
        return []
    candidates = []
    for row in sample_rows:
        if row.get("score_band", "") not in LOW_SCORE_BANDS:
            continue
        summary = book_summaries.get(catalog_id(row))
        if not summary:
            continue
        maximum_price = summary["maximum_asking_price_number"]
        if maximum_price is not None and maximum_price > relative_price_cutoff:
            candidates.append((row, summary))
    candidates.sort(
        key=lambda item: (
            -(item[1]["maximum_asking_price_number"] or 0),
            item[0].get("research_score", ""),
            item[0].get("title", "").casefold(),
        )
    )
    return [
        book_detail_row("false_negative_candidate", row, summary, relative_price_cutoff)
        for row, summary in candidates[:10]
    ]


def aggregate_row(
    section: str,
    summaries: list[Mapping[str, object]],
    *,
    score_band: str = "",
    signal: str = "",
) -> dict[str, str]:
    book_count = len(summaries)
    books_with_observations = sum(1 for summary in summaries if summary["books_with_observations"])
    observed_rows = sum(int(summary["observation_rows"]) for summary in summaries)
    prices = [
        price
        for summary in summaries
        for price in summary["asking_prices"]
    ]
    return base_row(
        section=section,
        score_band=score_band,
        signal=signal,
        books=str(book_count),
        books_with_observations=str(books_with_observations),
        observation_rows=str(observed_rows),
        observation_coverage_rate=percentage(books_with_observations, book_count),
        average_observations_per_book=format_decimal(observed_rows / book_count) if book_count else "",
        median_asking_price=format_money(median(prices)) if prices else "",
        average_asking_price=format_money(sum(prices) / len(prices)) if prices else "",
        maximum_asking_price=format_money(max(prices)) if prices else "",
    )


def book_detail_row(
    section: str,
    sample_row: Mapping[str, str],
    summary: Mapping[str, object],
    relative_price_cutoff: float | None,
) -> dict[str, str]:
    note = "Compared to sample-wide median maximum asking price"
    if relative_price_cutoff is not None:
        note = f"{note} ({format_money(relative_price_cutoff)})."
    else:
        note = f"{note}; no observed asking prices available."
    return base_row(
        section=section,
        catalog_id=catalog_id(sample_row),
        title=sample_row.get("title", ""),
        author=sample_row.get("author", ""),
        research_score=sample_row.get("research_score", ""),
        score_band=sample_row.get("score_band", ""),
        triggered_signals=sample_row.get("triggered_signals", ""),
        observation_rows=str(summary["observation_rows"]),
        median_asking_price=format_money(summary["median_asking_price_number"]) if summary["median_asking_price_number"] is not None else "",
        average_asking_price=format_money(summary["average_asking_price_number"]) if summary["average_asking_price_number"] is not None else "",
        maximum_asking_price=format_money(summary["maximum_asking_price_number"]) if summary["maximum_asking_price_number"] is not None else "",
        price_summary=summary["price_summary"],
        notes=note,
    )


def book_market_summary(sample_row: Mapping[str, str], observation_rows: list[Mapping[str, str]]) -> dict[str, object]:
    observed_rows = [row for row in observation_rows if row.get("lookup_status", "") == "observed"]
    prices = [price for row in observed_rows if (price := asking_price(row)) is not None]
    return {
        "catalog_id": catalog_id(sample_row),
        "observation_rows": len(observed_rows),
        "books_with_observations": bool(observed_rows),
        "asking_prices": prices,
        "median_asking_price_number": median(prices) if prices else None,
        "average_asking_price_number": sum(prices) / len(prices) if prices else None,
        "maximum_asking_price_number": max(prices) if prices else None,
        "price_summary": price_summary(prices),
    }


def group_observations_by_catalog_id(rows: list[Mapping[str, str]]) -> dict[str, list[Mapping[str, str]]]:
    grouped: dict[str, list[Mapping[str, str]]] = {}
    for row in rows:
        grouped.setdefault(catalog_id(row), []).append(row)
    return grouped


def triggered_signals(row: Mapping[str, str]) -> list[str]:
    return [signal.strip() for signal in row.get("triggered_signals", "").split(";") if signal.strip()]


def asking_price(row: Mapping[str, str]) -> float | None:
    try:
        return float(row.get("asking_price", ""))
    except ValueError:
        return None


def price_summary(prices: list[float]) -> str:
    if not prices:
        return "No observed asking prices."
    return (
        f"n={len(prices)}; median={format_money(median(prices))}; "
        f"average={format_money(sum(prices) / len(prices))}; max={format_money(max(prices))}"
    )


def metric_row(metric: str, value: int | str, denominator: int | None = None, notes: str = "") -> dict[str, str]:
    count = integer_value(value) if isinstance(value, int) else None
    return base_row(
        section="dataset_summary",
        metric=metric,
        value=str(value),
        percentage=percentage(count, denominator) if count is not None and denominator is not None else "",
        notes=notes,
    )


def base_row(**values: str) -> dict[str, str]:
    return {field: values.get(field, "") for field in MARKET_VALIDATION_ANALYSIS_FIELDNAMES}


def catalog_id(row: Mapping[str, str]) -> str:
    return row.get("catalog_id", "") or row.get("catalog_item_id", "")


def integer_value(value: str | int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def percentage(count: int, denominator: int | None) -> str:
    if not denominator:
        return ""
    return f"{count / denominator:.1%}"


def yes_no(value: bool) -> str:
    return "yes" if value else "no"


def format_money(value: float | int) -> str:
    return f"{value:.2f}"


def format_decimal(value: float) -> str:
    return f"{value:.2f}"

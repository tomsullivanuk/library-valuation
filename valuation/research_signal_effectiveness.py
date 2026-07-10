"""Descriptive review of Research Signal effectiveness against market observations."""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable, Mapping
from statistics import median

from valuation.market_validation_analysis import (
    asking_price,
    book_market_summary,
    catalog_id,
    format_money,
    group_observations_by_catalog_id,
    percentage,
    triggered_signals,
)


RESEARCH_SIGNAL_EFFECTIVENESS_FIELDNAMES = [
    "section",
    "signal",
    "classification",
    "combination",
    "cohort",
    "metric",
    "value",
    "catalog_id",
    "title",
    "author",
    "research_score",
    "score_band",
    "triggered_signals",
    "sampled_books",
    "sample_percentage",
    "books_with_observations",
    "observation_coverage_rate",
    "observation_rows",
    "median_asking_price",
    "average_asking_price",
    "minimum_asking_price",
    "maximum_asking_price",
    "reason_flagged",
    "threshold_basis",
    "notes",
]

LOW_SCORE_BANDS = {"0-1"}
HIGH_SCORE_BANDS = {"8-10"}
MINIMUM_CLASSIFICATION_SAMPLE = 3


def build_research_signal_effectiveness_rows(
    sample_rows: Iterable[Mapping[str, str]],
    observation_rows: Iterable[Mapping[str, str]],
    metadata_rows: Iterable[Mapping[str, str]],
    coverage_rows: Iterable[Mapping[str, str]] = (),
    analysis_rows: Iterable[Mapping[str, str]] = (),
) -> list[dict[str, str]]:
    samples = list(sample_rows)
    observations = list(observation_rows)
    metadata = list(metadata_rows)
    coverage = list(coverage_rows)
    analysis = list(analysis_rows)
    grouped = group_observations_by_catalog_id(observations)
    summaries = {
        catalog_id(row): book_market_summary(row, grouped.get(catalog_id(row), []))
        for row in samples
        if catalog_id(row)
    }
    observed_prices = [
        price
        for row in observations
        if row.get("lookup_status", "") == "observed"
        if (price := asking_price(row)) is not None
    ]
    maximum_prices = [
        value
        for summary in summaries.values()
        if (value := summary["maximum_asking_price_number"]) is not None
    ]
    overall_price_median = median(observed_prices) if observed_prices else None
    maximum_price_cutoff = median(maximum_prices) if maximum_prices else None

    signal_rows = build_signal_summary_rows(samples, summaries, overall_price_median)
    rows = list(signal_rows)
    rows.extend(build_signal_combination_rows(samples, summaries, maximum_price_cutoff))
    rows.extend(build_candidate_rows(samples, summaries, maximum_price_cutoff, false_positive=True))
    rows.extend(build_candidate_rows(samples, summaries, maximum_price_cutoff, false_positive=False))
    rows.extend(build_calibration_rows(samples, metadata, coverage, analysis, signal_rows))
    return rows


def build_signal_summary_rows(
    sample_rows: list[Mapping[str, str]],
    summaries: Mapping[str, Mapping[str, object]],
    overall_price_median: float | None,
) -> list[dict[str, str]]:
    signals = sorted({signal for row in sample_rows for signal in triggered_signals(row)})
    rows = []
    for signal in signals:
        matching = [row for row in sample_rows if signal in triggered_signals(row)]
        matching_summaries = [summaries[catalog_id(row)] for row in matching if catalog_id(row) in summaries]
        prices = [price for summary in matching_summaries for price in summary["asking_prices"]]
        books_with_observations = sum(1 for summary in matching_summaries if summary["books_with_observations"])
        high_score_books = sum(1 for row in matching if row.get("score_band", "") in HIGH_SCORE_BANDS)
        classification, reason = classify_signal(
            book_count=len(matching),
            median_price=median(prices) if prices else None,
            overall_price_median=overall_price_median,
            high_score_share=high_score_books / len(matching) if matching else 0,
        )
        rows.append(
            base_row(
                section="signal_summary",
                signal=signal,
                classification=classification,
                sampled_books=str(len(matching)),
                sample_percentage=percentage(len(matching), len(sample_rows)),
                books_with_observations=str(books_with_observations),
                observation_coverage_rate=percentage(books_with_observations, len(matching)),
                observation_rows=str(sum(int(summary["observation_rows"]) for summary in matching_summaries)),
                median_asking_price=format_money(median(prices)) if prices else "",
                average_asking_price=format_money(sum(prices) / len(prices)) if prices else "",
                minimum_asking_price=format_money(min(prices)) if prices else "",
                maximum_asking_price=format_money(max(prices)) if prices else "",
                threshold_basis=(
                    f"Sample-wide median observed asking price: {format_money(overall_price_median)}."
                    if overall_price_median is not None
                    else "No sample-wide observed asking-price threshold was available."
                ),
                notes=reason,
            )
        )
    return rows


def classify_signal(
    *,
    book_count: int,
    median_price: float | None,
    overall_price_median: float | None,
    high_score_share: float,
) -> tuple[str, str]:
    if book_count < MINIMUM_CLASSIFICATION_SAMPLE or median_price is None or overall_price_median is None:
        return "insufficient_sample", "Fewer than three sampled books or no comparable observed asking prices."
    if high_score_share >= 0.5 and median_price < overall_price_median:
        return (
            "possible_false_positive_driver",
            "At least half of signal-bearing books are high-score, but the signal median is below the sample median.",
        )
    if median_price >= overall_price_median * 1.5:
        return "strong_market_signal", "Signal median is at least 1.5 times the sample median."
    if median_price >= overall_price_median:
        return "moderate_market_signal", "Signal median meets or exceeds the sample median."
    return "weak_or_inconclusive_signal", "Signal median is below the sample median."


def build_signal_combination_rows(
    sample_rows: list[Mapping[str, str]],
    summaries: Mapping[str, Mapping[str, object]],
    maximum_price_cutoff: float | None,
) -> list[dict[str, str]]:
    if maximum_price_cutoff is None:
        return []
    cohorts: dict[str, Counter[str]] = {
        "high_score_strong_market_evidence": Counter(),
        "high_score_weak_market_evidence": Counter(),
        "low_score_strong_market_evidence": Counter(),
    }
    for row in sample_rows:
        summary = summaries.get(catalog_id(row))
        if not summary:
            continue
        maximum_price = summary["maximum_asking_price_number"]
        band = row.get("score_band", "")
        cohort = ""
        if band in HIGH_SCORE_BANDS and maximum_price is not None and maximum_price > maximum_price_cutoff:
            cohort = "high_score_strong_market_evidence"
        elif band in HIGH_SCORE_BANDS and (maximum_price is None or maximum_price <= maximum_price_cutoff):
            cohort = "high_score_weak_market_evidence"
        elif band in LOW_SCORE_BANDS and maximum_price is not None and maximum_price > maximum_price_cutoff:
            cohort = "low_score_strong_market_evidence"
        if cohort:
            combination = ";".join(sorted(triggered_signals(row))) or "no_triggered_signals"
            cohorts[cohort][combination] += 1

    rows = []
    for cohort, combinations in cohorts.items():
        cohort_books = sum(combinations.values())
        for combination, count in sorted(combinations.items(), key=lambda item: (-item[1], item[0])):
            rows.append(
                base_row(
                    section="signal_combination_review",
                    combination=combination,
                    cohort=cohort,
                    sampled_books=str(count),
                    sample_percentage=percentage(count, cohort_books),
                    threshold_basis=(
                        "Sample-wide median per-book maximum asking price: "
                        f"{format_money(maximum_price_cutoff)}."
                    ),
                )
            )
    return rows


def build_candidate_rows(
    sample_rows: list[Mapping[str, str]],
    summaries: Mapping[str, Mapping[str, object]],
    maximum_price_cutoff: float | None,
    *,
    false_positive: bool,
) -> list[dict[str, str]]:
    if maximum_price_cutoff is None:
        return []
    candidates = []
    for row in sample_rows:
        band = row.get("score_band", "")
        if false_positive and band not in HIGH_SCORE_BANDS:
            continue
        if not false_positive and band not in LOW_SCORE_BANDS:
            continue
        summary = summaries.get(catalog_id(row))
        if not summary:
            continue
        maximum_price = summary["maximum_asking_price_number"]
        qualifies = (
            maximum_price is None or maximum_price <= maximum_price_cutoff
            if false_positive
            else maximum_price is not None and maximum_price > maximum_price_cutoff
        )
        if qualifies:
            candidates.append((row, summary))
    candidates.sort(
        key=lambda item: (
            item[1]["maximum_asking_price_number"] is not None,
            item[1]["maximum_asking_price_number"] or 0,
            item[0].get("title", "").casefold(),
        ),
        reverse=not false_positive,
    )
    section = "false_positive_candidate" if false_positive else "false_negative_candidate"
    reason = (
        "High Research Score with no observed asking price or a per-book maximum at or below the sample median."
        if false_positive
        else "Low Research Score with a per-book maximum asking price above the sample median."
    )
    return [
        base_row(
            section=section,
            catalog_id=catalog_id(row),
            title=row.get("title", ""),
            author=row.get("author", ""),
            research_score=row.get("research_score", ""),
            score_band=row.get("score_band", ""),
            triggered_signals=row.get("triggered_signals", ""),
            observation_rows=str(summary["observation_rows"]),
            median_asking_price=(
                format_money(summary["median_asking_price_number"])
                if summary["median_asking_price_number"] is not None
                else ""
            ),
            maximum_asking_price=(
                format_money(summary["maximum_asking_price_number"])
                if summary["maximum_asking_price_number"] is not None
                else ""
            ),
            reason_flagged=reason,
            threshold_basis=f"Sample-wide median per-book maximum asking price: {format_money(maximum_price_cutoff)}.",
        )
        for row, summary in candidates
    ]


def build_calibration_rows(
    sample_rows: list[Mapping[str, str]],
    metadata_rows: list[Mapping[str, str]],
    coverage_rows: list[Mapping[str, str]],
    analysis_rows: list[Mapping[str, str]],
    signal_rows: list[Mapping[str, str]],
) -> list[dict[str, str]]:
    unused = [row.get("score_band", "") for row in metadata_rows if row.get("available_population_count", "") == "0"]
    underused = [
        row.get("score_band", "")
        for row in metadata_rows
        if integer(row.get("actual_sample_count", "")) < integer(row.get("target_sample_count", ""))
    ]
    common = [row["signal"] for row in signal_rows if parse_percentage(row["sample_percentage"]) >= 0.5]
    strong = [row["signal"] for row in signal_rows if row["classification"] == "strong_market_signal"]
    possible_drivers = [
        row["signal"]
        for row in signal_rows
        if row["classification"] == "possible_false_positive_driver"
    ]
    high_score_samples = [row for row in sample_rows if row.get("score_band", "") in HIGH_SCORE_BANDS]
    high_signal_counts = Counter(signal for row in high_score_samples for signal in triggered_signals(row))
    concentrated = (
        [signal for signal, count in high_signal_counts.items() if count / len(high_score_samples) >= 0.5]
        if high_score_samples
        else []
    )
    band_analysis = [row for row in analysis_rows if row.get("section", "") == "score_band_market_analysis"]
    band_medians = [money(row.get("median_asking_price", "")) for row in band_analysis if row.get("books", "") != "0"]
    gradient = len(band_medians) >= 2 and all(left <= right for left, right in zip(band_medians, band_medians[1:]))

    findings = [
        (
            "score_band_usage",
            f"Unused catalog bands: {join_or_none(unused)}; "
            f"below-target sample bands: {join_or_none(underused)}.",
        ),
        (
            "score_gradient",
            "Observed band medians form a monotonic gradient."
            if gradient
            else "Observed band medians do not form a monotonic gradient.",
        ),
        (
            "high_score_signal_concentration",
            f"Signals present in at least half of high-score books: {join_or_none(concentrated)}.",
        ),
        ("signal_discrimination", f"Signals present in at least half of all sampled books: {join_or_none(common)}."),
        ("rare_or_strong_signals", f"Signals classified as strong in this sample: {join_or_none(strong)}."),
        (
            "future_model_review",
            f"Possible false-positive drivers for future review: {join_or_none(possible_drivers)}. "
            "No weights or definitions changed.",
        ),
        (
            "artifact_traceability",
            f"Consumed {len(coverage_rows)} coverage rows and {len(analysis_rows)} PR8 analysis rows.",
        ),
    ]
    return [base_row(section="model_calibration_note", metric=metric, notes=notes) for metric, notes in findings]


def base_row(**values: str) -> dict[str, str]:
    return {field: values.get(field, "") for field in RESEARCH_SIGNAL_EFFECTIVENESS_FIELDNAMES}


def integer(value: str) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def money(value: str) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def parse_percentage(value: str) -> float:
    try:
        return float(value.rstrip("%")) / 100
    except (AttributeError, ValueError):
        return 0.0


def join_or_none(values: list[str]) -> str:
    return ", ".join(sorted(value for value in values if value)) or "none"

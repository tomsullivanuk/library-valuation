"""Expanded market validation analysis with original-sample comparisons."""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable, Mapping

from valuation.market_validation_analysis import (
    MARKET_VALIDATION_ANALYSIS_FIELDNAMES,
    asking_price,
    build_market_validation_analysis_rows,
)
from valuation.research_signal_effectiveness import (
    RESEARCH_SIGNAL_EFFECTIVENESS_FIELDNAMES,
    build_research_signal_effectiveness_rows,
)


EXPANDED_MARKET_VALIDATION_ANALYSIS_FIELDNAMES = MARKET_VALIDATION_ANALYSIS_FIELDNAMES + [
    "minimum_asking_price",
    "original_sample_count",
    "original_observation_rows",
    "original_median_asking_price",
    "original_average_asking_price",
    "original_maximum_asking_price",
    "comparison_status",
    "interpretation",
]

EXPANDED_RESEARCH_SIGNAL_EFFECTIVENESS_FIELDNAMES = RESEARCH_SIGNAL_EFFECTIVENESS_FIELDNAMES + [
    "original_sampled_books",
    "original_classification",
    "original_median_asking_price",
    "original_maximum_asking_price",
    "comparison_status",
    "price_interpretation",
]


def build_expanded_market_validation_analysis_rows(
    expanded_sample_rows: Iterable[Mapping[str, str]],
    expanded_observation_rows: Iterable[Mapping[str, str]],
    expanded_metadata_rows: Iterable[Mapping[str, str]],
    original_sample_rows: Iterable[Mapping[str, str]],
    original_observation_rows: Iterable[Mapping[str, str]],
    original_metadata_rows: Iterable[Mapping[str, str]],
) -> list[dict[str, str]]:
    expanded_samples = list(expanded_sample_rows)
    expanded_observations = list(expanded_observation_rows)
    original_samples = list(original_sample_rows)
    original_observations = list(original_observation_rows)
    expanded_rows = build_market_validation_analysis_rows(
        expanded_samples,
        expanded_observations,
        normalize_expanded_metadata(expanded_metadata_rows),
    )
    original_rows = build_market_validation_analysis_rows(
        original_samples,
        original_observations,
        list(original_metadata_rows),
    )
    original_index = {analysis_key(row): row for row in original_rows}
    expanded_prices = prices_by_band(expanded_samples, expanded_observations)
    expanded_candidate_review = build_research_signal_effectiveness_rows(
        expanded_samples,
        expanded_observations,
        normalize_expanded_metadata(expanded_metadata_rows),
        analysis_rows=expanded_rows,
    )
    original_candidate_review = build_research_signal_effectiveness_rows(
        original_samples,
        original_observations,
        list(original_metadata_rows),
        analysis_rows=original_rows,
    )
    original_candidate_ids = candidate_ids_by_section(original_candidate_review)

    rows = []
    for source_row in expanded_rows:
        row = expanded_base_row(**source_row)
        original = original_index.get(analysis_key(source_row), {})
        if source_row.get("section") == "score_band_market_analysis":
            prices = expanded_prices.get(source_row.get("score_band", ""), [])
            row["minimum_asking_price"] = money(min(prices)) if prices else ""
            add_original_market_comparison(row, original)
        elif source_row.get("section") in {"false_positive_candidate", "false_negative_candidate"}:
            row["comparison_status"] = (
                "still_flagged"
                if source_row.get("catalog_id", "") in original_candidate_ids[source_row["section"]]
                else "new_candidate"
            )
        rows.append(row)

    rows.extend(
        coverage_comparison_rows(
            expanded_samples,
            expanded_observations,
            original_samples,
            original_observations,
        )
    )
    rows.extend(median_maximum_review_rows(rows))
    rows.extend(no_longer_flagged_rows(original_candidate_review, expanded_candidate_review))
    rows.extend(calibration_implication_rows(expanded_samples, expanded_observations))
    return rows


def build_expanded_research_signal_effectiveness_rows(
    expanded_sample_rows: Iterable[Mapping[str, str]],
    expanded_observation_rows: Iterable[Mapping[str, str]],
    expanded_metadata_rows: Iterable[Mapping[str, str]],
    original_sample_rows: Iterable[Mapping[str, str]],
    original_observation_rows: Iterable[Mapping[str, str]],
    original_metadata_rows: Iterable[Mapping[str, str]],
) -> list[dict[str, str]]:
    expanded_samples = list(expanded_sample_rows)
    expanded_observations = list(expanded_observation_rows)
    original_samples = list(original_sample_rows)
    original_observations = list(original_observation_rows)
    expanded_analysis = build_market_validation_analysis_rows(
        expanded_samples,
        expanded_observations,
        normalize_expanded_metadata(expanded_metadata_rows),
    )
    original_analysis = build_market_validation_analysis_rows(
        original_samples,
        original_observations,
        list(original_metadata_rows),
    )
    expanded_rows = build_research_signal_effectiveness_rows(
        expanded_samples,
        expanded_observations,
        normalize_expanded_metadata(expanded_metadata_rows),
        analysis_rows=expanded_analysis,
    )
    original_rows = build_research_signal_effectiveness_rows(
        original_samples,
        original_observations,
        list(original_metadata_rows),
        analysis_rows=original_analysis,
    )
    original_signals = {
        row.get("signal", ""): row
        for row in original_rows
        if row.get("section") == "signal_summary"
    }
    original_candidates = candidate_ids_by_section(original_rows)
    rows = []
    for source_row in expanded_rows:
        row = signal_base_row(**source_row)
        if source_row.get("section") == "signal_summary":
            original = original_signals.get(source_row.get("signal", ""), {})
            row["original_sampled_books"] = original.get("sampled_books", "0")
            row["original_classification"] = original.get("classification", "not_observed")
            row["original_median_asking_price"] = original.get("median_asking_price", "")
            row["original_maximum_asking_price"] = original.get("maximum_asking_price", "")
            row["comparison_status"] = classification_comparison(
                original.get("classification", ""),
                source_row.get("classification", ""),
            )
            row["price_interpretation"] = price_shape_interpretation(
                number(source_row.get("median_asking_price", "")),
                number(source_row.get("average_asking_price", "")),
                number(source_row.get("maximum_asking_price", "")),
            )
        elif source_row.get("section") in {"false_positive_candidate", "false_negative_candidate"}:
            row["comparison_status"] = (
                "still_flagged"
                if source_row.get("catalog_id", "") in original_candidates[source_row["section"]]
                else "new_candidate"
            )
        rows.append(row)
    rows.extend(no_longer_signal_candidate_rows(original_rows, expanded_rows))
    return rows


def normalize_expanded_metadata(rows: Iterable[Mapping[str, str]]) -> list[dict[str, str]]:
    return [
        {
            "score_band": row.get("score_band", ""),
            "target_sample_count": row.get("balanced_target_floor_count", ""),
            "available_population_count": row.get("available_population_count", ""),
            "actual_sample_count": row.get("expanded_sample_count", ""),
        }
        for row in rows
    ]


def coverage_comparison_rows(
    expanded_samples: list[Mapping[str, str]],
    expanded_observations: list[Mapping[str, str]],
    original_samples: list[Mapping[str, str]],
    original_observations: list[Mapping[str, str]],
) -> list[dict[str, str]]:
    expanded_ids = {row.get("catalog_id", "") for row in expanded_samples if row.get("catalog_id", "")}
    original_ids = {row.get("catalog_id", "") for row in original_samples if row.get("catalog_id", "")}
    expanded_observed_ids = observed_catalog_ids(expanded_observations)
    original_observed_ids = observed_catalog_ids(original_observations)
    metrics = [
        ("expanded_sample_count", len(expanded_ids), len(original_ids)),
        ("total_observation_rows", len(expanded_observations), len(original_observations)),
        ("books_with_observations", len(expanded_observed_ids), len(original_observed_ids)),
        (
            "books_without_observations",
            len(expanded_ids - expanded_observed_ids),
            len(original_ids - original_observed_ids),
        ),
    ]
    rows = [
        expanded_base_row(
            section="expanded_coverage_summary",
            metric=metric,
            value=str(value),
            original_sample_count=str(original_value),
            comparison_status=f"change={value - original_value:+d}",
        )
        for metric, value, original_value in metrics
    ]
    for strategy, count in sorted(Counter(row.get("lookup_strategy", "") for row in expanded_observations).items()):
        rows.append(
            expanded_base_row(
                section="expanded_coverage_summary",
                metric=f"lookup_strategy_{strategy}",
                value=str(count),
            )
        )
    for status, count in sorted(Counter(row.get("lookup_status", "") for row in expanded_observations).items()):
        rows.append(
            expanded_base_row(
                section="expanded_coverage_summary",
                metric=f"lookup_status_{status}",
                value=str(count),
            )
        )
    diagnostic_counts = Counter(
        row.get("diagnostic_code", "")
        for row in expanded_observations
        if row.get("diagnostic_code", "")
    )
    for code, count in sorted(diagnostic_counts.items()):
        rows.append(
            expanded_base_row(
                section="expanded_coverage_summary",
                metric=f"diagnostic_{code}",
                value=str(count),
            )
        )
    rows.append(
        expanded_base_row(
            section="expanded_coverage_summary",
            metric="source_failure_rows",
            value=str(sum(1 for row in expanded_observations if row.get("lookup_status", "") == "source_unavailable")),
        )
    )
    return rows


def median_maximum_review_rows(rows: list[Mapping[str, str]]) -> list[dict[str, str]]:
    review_rows = []
    for row in rows:
        if row.get("section") != "score_band_market_analysis":
            continue
        median_price = number(row.get("median_asking_price", ""))
        average_price = number(row.get("average_asking_price", ""))
        maximum_price = number(row.get("maximum_asking_price", ""))
        interpretation = price_shape_interpretation(median_price, average_price, maximum_price)
        review_rows.append(
            expanded_base_row(
                section="median_maximum_review",
                score_band=row.get("score_band", ""),
                median_asking_price=row.get("median_asking_price", ""),
                average_asking_price=row.get("average_asking_price", ""),
                minimum_asking_price=row.get("minimum_asking_price", ""),
                maximum_asking_price=row.get("maximum_asking_price", ""),
                interpretation=interpretation,
                notes="Asking-price shape only; maximum prices are not valuation evidence.",
            )
        )
    return review_rows


def price_shape_interpretation(median_price: float, average_price: float, maximum_price: float) -> str:
    if median_price <= 0:
        return "insufficient_price_evidence"
    if maximum_price >= median_price * 5 and average_price >= median_price * 1.5:
        return "maximum_and_average_outlier_sensitive"
    if maximum_price >= median_price * 5:
        return "maximum_outlier_sensitive"
    if median_price >= 10:
        return "stronger_typical_market_signal"
    return "typical_market_signal_near_sample_baseline"


def calibration_implication_rows(
    expanded_samples: list[Mapping[str, str]],
    expanded_observations: list[Mapping[str, str]],
) -> list[dict[str, str]]:
    implications = [
        (
            "signal_role_rebalancing",
            "supported_for_simulation",
            "The larger sample can distinguish typical-price behavior from upside outliers more credibly.",
        ),
        (
            "market_vs_research_effort",
            "still_relevant",
            "Metadata-gap signals should remain distinguishable from direct market-likelihood evidence.",
        ),
        (
            "score_band_structure",
            "structural_issue",
            "The 2-3 band remains empty, 6-7 remains sparse, and 8-10 contains every raw score of 8 or greater.",
        ),
        (
            "simulation_readiness",
            "sufficient_for_before_after_simulation",
            f"The expanded evidence includes {len(expanded_samples)} books "
            f"and {len(expanded_observations)} observation rows.",
        ),
        (
            "additional_market_data",
            "desirable_not_blocking",
            "Sold-price or second-source evidence would strengthen production decisions "
            "but is not required for a non-production simulation.",
        ),
    ]
    return [
        expanded_base_row(section="calibration_implication", metric=metric, value=value, notes=notes)
        for metric, value, notes in implications
    ]


def no_longer_flagged_rows(
    original_rows: list[Mapping[str, str]],
    expanded_rows: list[Mapping[str, str]],
) -> list[dict[str, str]]:
    expanded_candidates = candidate_ids_by_section(expanded_rows)
    rows = []
    for row in original_rows:
        section = row.get("section", "")
        if section not in {"false_positive_candidate", "false_negative_candidate"}:
            continue
        if row.get("catalog_id", "") in expanded_candidates[section]:
            continue
        values = dict(row)
        values.update(
            section=f"{section}_comparison",
            comparison_status="no_longer_flagged",
        )
        rows.append(
            expanded_base_row(**values)
        )
    return rows


def no_longer_signal_candidate_rows(
    original_rows: list[Mapping[str, str]],
    expanded_rows: list[Mapping[str, str]],
) -> list[dict[str, str]]:
    expanded_candidates = candidate_ids_by_section(expanded_rows)
    rows = []
    for row in original_rows:
        section = row.get("section", "")
        if section not in {"false_positive_candidate", "false_negative_candidate"}:
            continue
        if row.get("catalog_id", "") in expanded_candidates[section]:
            continue
        values = dict(row)
        values.update(
            section=f"{section}_comparison",
            comparison_status="no_longer_flagged",
        )
        rows.append(
            signal_base_row(**values)
        )
    return rows


def add_original_market_comparison(row: dict[str, str], original: Mapping[str, str]) -> None:
    row["original_sample_count"] = original.get("books", "0")
    row["original_observation_rows"] = original.get("observation_rows", "0")
    row["original_median_asking_price"] = original.get("median_asking_price", "")
    row["original_average_asking_price"] = original.get("average_asking_price", "")
    row["original_maximum_asking_price"] = original.get("maximum_asking_price", "")
    row["comparison_status"] = market_comparison_status(row, original)


def market_comparison_status(expanded: Mapping[str, str], original: Mapping[str, str]) -> str:
    if not original or original.get("books", "0") == "0":
        return "new_or_still_empty_band"
    expanded_median = number(expanded.get("median_asking_price", ""))
    original_median = number(original.get("median_asking_price", ""))
    if expanded_median > original_median:
        return "median_increased"
    if expanded_median < original_median:
        return "median_decreased"
    return "median_unchanged"


def classification_comparison(original: str, expanded: str) -> str:
    if not original:
        return "new_signal_evidence"
    if original == expanded:
        return "classification_holds"
    if original == "insufficient_sample" and expanded != "insufficient_sample":
        return "evidence_strengthened"
    if expanded == "insufficient_sample":
        return "evidence_weakened"
    strength = {
        "possible_false_positive_driver": 1,
        "weak_or_inconclusive_signal": 1,
        "moderate_market_signal": 2,
        "strong_market_signal": 3,
    }
    if strength.get(expanded, 0) > strength.get(original, 0):
        return "evidence_strengthened"
    if strength.get(expanded, 0) < strength.get(original, 0):
        return "evidence_weakened"
    return "classification_changed"


def analysis_key(row: Mapping[str, str]) -> tuple[str, str, str, str, str]:
    return (
        row.get("section", ""),
        row.get("metric", ""),
        row.get("score_band", ""),
        row.get("signal", ""),
        row.get("catalog_id", ""),
    )


def candidate_ids_by_section(rows: Iterable[Mapping[str, str]]) -> dict[str, set[str]]:
    sections = {"false_positive_candidate": set(), "false_negative_candidate": set()}
    for row in rows:
        section = row.get("section", "")
        if section in sections and row.get("catalog_id", ""):
            sections[section].add(row["catalog_id"])
    return sections


def prices_by_band(
    sample_rows: list[Mapping[str, str]],
    observation_rows: list[Mapping[str, str]],
) -> dict[str, list[float]]:
    band_by_id = {row.get("catalog_id", ""): row.get("score_band", "") for row in sample_rows}
    grouped = {}
    for row in observation_rows:
        if row.get("lookup_status", "") != "observed":
            continue
        price = asking_price(row)
        band = band_by_id.get(row.get("catalog_id", ""), "")
        if price is not None and band:
            grouped.setdefault(band, []).append(price)
    return grouped


def observed_catalog_ids(rows: Iterable[Mapping[str, str]]) -> set[str]:
    return {
        row.get("catalog_id", "")
        for row in rows
        if row.get("lookup_status", "") == "observed" and row.get("catalog_id", "")
    }


def expanded_base_row(**values: str) -> dict[str, str]:
    return {field: values.get(field, "") for field in EXPANDED_MARKET_VALIDATION_ANALYSIS_FIELDNAMES}


def signal_base_row(**values: str) -> dict[str, str]:
    return {field: values.get(field, "") for field in EXPANDED_RESEARCH_SIGNAL_EFFECTIVENESS_FIELDNAMES}


def number(value: str) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def money(value: float) -> str:
    return f"{value:.2f}"

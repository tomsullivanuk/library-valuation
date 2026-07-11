"""Non-production Research Assessment calibration simulation."""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable, Mapping
from statistics import median

from valuation.market_validation_analysis import asking_price
from valuation.research_assessments import research_priority_band
from valuation.research_signals import DEFAULT_RESEARCH_SIGNAL_WEIGHTS, default_research_signal_config


BASELINE_SCENARIO = "current_baseline"
CONSERVATIVE_SCENARIO = "conservative_rebalancing"
MARKET_LIKELIHOOD_SCENARIO = "market_likelihood_emphasis"
SCENARIO_ORDER = (BASELINE_SCENARIO, CONSERVATIVE_SCENARIO, MARKET_LIKELIHOOD_SCENARIO)

# These mappings are simulation inputs only. Production configuration remains authoritative.
SIMULATION_SCENARIO_WEIGHTS = {
    CONSERVATIVE_SCENARIO: {
        "old_publication_year": 12,
        "university_press": 15,
        "specialist_publisher": 10,
        "missing_lcc": 6,
        "missing_oclc": 3,
        "scholarly_lc_subject": 9,
        "multiple_acquisitions": 8,
        "low_metadata_confidence": 2,
    },
    MARKET_LIKELIHOOD_SCENARIO: {
        "old_publication_year": 14,
        "university_press": 18,
        "specialist_publisher": 8,
        "missing_lcc": 3,
        "missing_oclc": 1,
        "scholarly_lc_subject": 12,
        "multiple_acquisitions": 10,
        "low_metadata_confidence": 0,
    },
}

CALIBRATION_SIMULATION_FIELDNAMES = [
    "catalog_id",
    "title",
    "author",
    "current_score",
    "current_band",
    "simulated_scenario",
    "simulated_score",
    "simulated_band",
    "score_delta",
    "band_delta",
    "triggered_signals",
    "current_signal_contribution_summary",
    "simulated_signal_contribution_summary",
    "movement_reason",
    "baseline_rank",
    "simulated_rank",
    "rank_delta",
    "baseline_top_n",
    "simulated_top_n",
    "market_observation_count",
    "median_asking_price",
    "average_asking_price",
    "maximum_asking_price",
    "false_positive_reference",
    "false_negative_reference",
]

CALIBRATION_SIMULATION_SUMMARY_FIELDNAMES = [
    "section",
    "scenario",
    "metric",
    "score_band",
    "value",
    "percentage",
    "baseline_value",
    "delta",
    "notes",
]

CALIBRATION_SIMULATION_MOVEMENT_FIELDNAMES = [
    "scenario",
    "movement_type",
    "catalog_id",
    "title",
    "author",
    "current_score",
    "simulated_score",
    "score_delta",
    "baseline_rank",
    "simulated_rank",
    "rank_delta",
    "current_band",
    "simulated_band",
    "triggered_signals",
    "median_asking_price",
    "maximum_asking_price",
    "reference_candidate_type",
    "movement_reason",
]

BAND_ORDER = {"none": 0, "low": 1, "medium": 2, "high": 3}


def build_calibration_simulation(
    sample_rows: Iterable[Mapping[str, str]],
    observation_rows: Iterable[Mapping[str, str]],
    signal_review_rows: Iterable[Mapping[str, str]],
    *,
    top_n: int = 50,
) -> tuple[list[dict[str, str]], list[dict[str, str]], list[dict[str, str]]]:
    if top_n < 1:
        raise ValueError("top_n must be at least 1")
    samples = sorted(list(sample_rows), key=lambda row: row.get("catalog_id", ""))
    observations = list(observation_rows)
    review_rows = list(signal_review_rows)
    market_by_id = market_summaries(observations)
    false_positive_ids = candidate_ids(review_rows, "false_positive_candidate")
    false_negative_ids = candidate_ids(review_rows, "false_negative_candidate")
    scenario_scores = {
        scenario: scores_for_scenario(samples, scenario)
        for scenario in SCENARIO_ORDER
    }
    ranks = {
        scenario: rank_scores(scores)
        for scenario, scores in scenario_scores.items()
    }

    simulation_rows = []
    for scenario in SCENARIO_ORDER:
        for sample in samples:
            sample_id = sample.get("catalog_id", "")
            current_score = integer(sample.get("research_score", ""))
            simulated_score = scenario_scores[scenario][sample_id]
            current_band = production_band(current_score)
            simulated_band = production_band(simulated_score)
            signals = signal_codes(sample)
            market = market_by_id.get(sample_id, empty_market_summary())
            baseline_rank = ranks[BASELINE_SCENARIO][sample_id]
            simulated_rank = ranks[scenario][sample_id]
            simulation_rows.append(
                {
                    "catalog_id": sample_id,
                    "title": sample.get("title", ""),
                    "author": sample.get("author", ""),
                    "current_score": str(current_score),
                    "current_band": current_band,
                    "simulated_scenario": scenario,
                    "simulated_score": str(simulated_score),
                    "simulated_band": simulated_band,
                    "score_delta": signed(simulated_score - current_score),
                    "band_delta": signed(BAND_ORDER[simulated_band] - BAND_ORDER[current_band]),
                    "triggered_signals": ";".join(signals),
                    "current_signal_contribution_summary": contribution_summary(
                        signals,
                        DEFAULT_RESEARCH_SIGNAL_WEIGHTS,
                    ),
                    "simulated_signal_contribution_summary": contribution_summary(
                        signals,
                        scenario_weights(scenario),
                    ),
                    "movement_reason": movement_reason(signals, current_score, simulated_score, scenario),
                    "baseline_rank": str(baseline_rank),
                    "simulated_rank": str(simulated_rank),
                    "rank_delta": signed(baseline_rank - simulated_rank),
                    "baseline_top_n": yes_no(baseline_rank <= top_n),
                    "simulated_top_n": yes_no(simulated_rank <= top_n),
                    "market_observation_count": str(market["count"]),
                    "median_asking_price": money_or_blank(market["median"]),
                    "average_asking_price": money_or_blank(market["average"]),
                    "maximum_asking_price": money_or_blank(market["maximum"]),
                    "false_positive_reference": yes_no(sample_id in false_positive_ids),
                    "false_negative_reference": yes_no(sample_id in false_negative_ids),
                }
            )

    summary_rows = build_summary_rows(
        simulation_rows,
        top_n=top_n,
        false_positive_ids=false_positive_ids,
        false_negative_ids=false_negative_ids,
    )
    movement_rows = build_movement_rows(simulation_rows)
    return simulation_rows, summary_rows, movement_rows


def scores_for_scenario(samples: list[Mapping[str, str]], scenario: str) -> dict[str, int]:
    weights = scenario_weights(scenario)
    scores = {}
    for row in samples:
        sample_id = row.get("catalog_id", "")
        if scenario == BASELINE_SCENARIO:
            scores[sample_id] = integer(row.get("research_score", ""))
        else:
            scores[sample_id] = sum(weights.get(signal, 0) for signal in signal_codes(row))
    return scores


def scenario_weights(scenario: str) -> Mapping[str, int]:
    if scenario == BASELINE_SCENARIO:
        return DEFAULT_RESEARCH_SIGNAL_WEIGHTS
    return SIMULATION_SCENARIO_WEIGHTS[scenario]


def rank_scores(scores: Mapping[str, int]) -> dict[str, int]:
    ordered = sorted(scores, key=lambda sample_id: (-scores[sample_id], sample_id))
    return {sample_id: rank for rank, sample_id in enumerate(ordered, start=1)}


def build_summary_rows(
    simulation_rows: list[Mapping[str, str]],
    *,
    top_n: int,
    false_positive_ids: set[str],
    false_negative_ids: set[str],
) -> list[dict[str, str]]:
    rows_by_scenario = {
        scenario: [row for row in simulation_rows if row.get("simulated_scenario", "") == scenario]
        for scenario in SCENARIO_ORDER
    }
    baseline = rows_by_scenario[BASELINE_SCENARIO]
    baseline_metrics = scenario_metrics(baseline, top_n, false_positive_ids, false_negative_ids)
    summary_rows = []
    for scenario in SCENARIO_ORDER:
        scenario_rows = rows_by_scenario[scenario]
        metrics = scenario_metrics(scenario_rows, top_n, false_positive_ids, false_negative_ids)
        band_counts = Counter(row.get("simulated_band", "") for row in scenario_rows)
        for band in BAND_ORDER:
            summary_rows.append(
                summary_row(
                    section="score_distribution",
                    scenario=scenario,
                    metric="book_count",
                    score_band=band,
                    value=band_counts[band],
                    percentage_value=ratio(band_counts[band], len(scenario_rows)),
                    baseline_value=Counter(row.get("simulated_band", "") for row in baseline)[band],
                )
            )
        for metric, value in metrics.items():
            baseline_value = baseline_metrics.get(metric, "")
            summary_rows.append(
                summary_row(
                    section="scenario_summary",
                    scenario=scenario,
                    metric=metric,
                    value=value,
                    baseline_value=baseline_value,
                    delta=numeric_delta(value, baseline_value),
                )
            )
        summary_rows.extend(score_band_issue_rows(scenario))
    return summary_rows


def scenario_metrics(
    rows: list[Mapping[str, str]],
    top_n: int,
    false_positive_ids: set[str],
    false_negative_ids: set[str],
) -> dict[str, int | str]:
    scores = [integer(row.get("simulated_score", "")) for row in rows]
    top_rows = [row for row in rows if row.get("simulated_top_n", "") == "yes"]
    top_prices = [number(row.get("median_asking_price", "")) for row in top_rows if row.get("median_asking_price", "")]
    top_average_prices = [
        number(row.get("average_asking_price", ""))
        for row in top_rows
        if row.get("average_asking_price", "")
    ]
    return {
        "book_count": len(rows),
        "average_score": decimal(sum(scores) / len(scores)) if scores else "",
        "median_score": decimal(median(scores)) if scores else "",
        "minimum_score": min(scores) if scores else "",
        "maximum_score": max(scores) if scores else "",
        "moving_up": sum(1 for row in rows if integer(row.get("score_delta", "")) > 0),
        "moving_down": sum(1 for row in rows if integer(row.get("score_delta", "")) < 0),
        "unchanged": sum(1 for row in rows if integer(row.get("score_delta", "")) == 0),
        "production_band_crossings": sum(
            1
            for row in rows
            if row.get("current_band", "") != row.get("simulated_band", "")
        ),
        "top_n": min(top_n, len(rows)),
        "top_n_entering": sum(
            1
            for row in rows
            if row.get("baseline_top_n", "") == "no" and row.get("simulated_top_n", "") == "yes"
        ),
        "top_n_leaving": sum(
            1
            for row in rows
            if row.get("baseline_top_n", "") == "yes" and row.get("simulated_top_n", "") == "no"
        ),
        "top_n_median_book_asking_price": money_or_blank(median(top_prices) if top_prices else None),
        "top_n_average_book_asking_price": money_or_blank(
            sum(top_average_prices) / len(top_average_prices) if top_average_prices else None
        ),
        "top_n_false_positive_references": sum(
            1
            for row in top_rows
            if row.get("catalog_id", "") in false_positive_ids
        ),
        "false_positive_references_moving_down": sum(
            1
            for row in rows
            if row.get("catalog_id", "") in false_positive_ids and integer(row.get("rank_delta", "")) < 0
        ),
        "false_negative_references_moving_up": sum(
            1
            for row in rows
            if row.get("catalog_id", "") in false_negative_ids and integer(row.get("rank_delta", "")) > 0
        ),
        "top_n_outlier_sensitive_books": sum(1 for row in top_rows if outlier_sensitive(row)),
    }


def build_movement_rows(simulation_rows: list[Mapping[str, str]]) -> list[dict[str, str]]:
    rows = []
    for row in simulation_rows:
        scenario = row.get("simulated_scenario", "")
        if scenario == BASELINE_SCENARIO:
            continue
        movement_types = []
        if row.get("baseline_top_n", "") == "no" and row.get("simulated_top_n", "") == "yes":
            movement_types.append("entered_top_n")
        if row.get("baseline_top_n", "") == "yes" and row.get("simulated_top_n", "") == "no":
            movement_types.append("left_top_n")
        if abs(integer(row.get("rank_delta", ""))) >= 10:
            movement_types.append("material_rank_movement")
        if row.get("false_positive_reference", "") == "yes" and integer(row.get("rank_delta", "")) < 0:
            movement_types.append("false_positive_moved_down")
        if row.get("false_negative_reference", "") == "yes" and integer(row.get("rank_delta", "")) > 0:
            movement_types.append("false_negative_moved_up")
        for movement_type in movement_types:
            rows.append(movement_row(row, movement_type))
    return sorted(
        rows,
        key=lambda row: (
            SCENARIO_ORDER.index(row["scenario"]),
            row["movement_type"],
            -abs(integer(row["rank_delta"])),
            row["catalog_id"],
        ),
    )


def movement_row(row: Mapping[str, str], movement_type: str) -> dict[str, str]:
    reference_types = []
    if row.get("false_positive_reference", "") == "yes":
        reference_types.append("false_positive")
    if row.get("false_negative_reference", "") == "yes":
        reference_types.append("false_negative")
    return {
        "scenario": row.get("simulated_scenario", ""),
        "movement_type": movement_type,
        "catalog_id": row.get("catalog_id", ""),
        "title": row.get("title", ""),
        "author": row.get("author", ""),
        "current_score": row.get("current_score", ""),
        "simulated_score": row.get("simulated_score", ""),
        "score_delta": row.get("score_delta", ""),
        "baseline_rank": row.get("baseline_rank", ""),
        "simulated_rank": row.get("simulated_rank", ""),
        "rank_delta": row.get("rank_delta", ""),
        "current_band": row.get("current_band", ""),
        "simulated_band": row.get("simulated_band", ""),
        "triggered_signals": row.get("triggered_signals", ""),
        "median_asking_price": row.get("median_asking_price", ""),
        "maximum_asking_price": row.get("maximum_asking_price", ""),
        "reference_candidate_type": ";".join(reference_types),
        "movement_reason": row.get("movement_reason", ""),
    }


def market_summaries(observation_rows: list[Mapping[str, str]]) -> dict[str, dict[str, float | int | None]]:
    prices_by_id = {}
    for row in observation_rows:
        if row.get("lookup_status", "") != "observed":
            continue
        price = asking_price(row)
        sample_id = row.get("catalog_id", "")
        if price is not None and sample_id:
            prices_by_id.setdefault(sample_id, []).append(price)
    return {
        sample_id: {
            "count": len(prices),
            "median": median(prices),
            "average": sum(prices) / len(prices),
            "maximum": max(prices),
        }
        for sample_id, prices in prices_by_id.items()
    }


def empty_market_summary() -> dict[str, float | int | None]:
    return {"count": 0, "median": None, "average": None, "maximum": None}


def candidate_ids(rows: list[Mapping[str, str]], section: str) -> set[str]:
    return {
        row.get("catalog_id", "")
        for row in rows
        if row.get("section", "") == section and row.get("catalog_id", "")
    }


def contribution_summary(signals: list[str], weights: Mapping[str, int]) -> str:
    return ";".join(f"{signal}:{weights.get(signal, 0):+d}" for signal in signals)


def movement_reason(signals: list[str], current_score: int, simulated_score: int, scenario: str) -> str:
    if scenario == BASELINE_SCENARIO:
        return "Control scenario preserves the persisted Research Score."
    changed = [
        f"{signal}:{DEFAULT_RESEARCH_SIGNAL_WEIGHTS.get(signal, 0):+d}->{scenario_weights(scenario).get(signal, 0):+d}"
        for signal in signals
        if DEFAULT_RESEARCH_SIGNAL_WEIGHTS.get(signal, 0) != scenario_weights(scenario).get(signal, 0)
    ]
    direction = "unchanged"
    if simulated_score > current_score:
        direction = "increased"
    elif simulated_score < current_score:
        direction = "decreased"
    detail = "; ".join(changed) if changed else "no triggered contribution changed"
    return f"Score {direction}: {detail}."


def signal_codes(row: Mapping[str, str]) -> list[str]:
    return [signal.strip() for signal in row.get("triggered_signals", "").split(";") if signal.strip()]


def production_band(score: int) -> str:
    return research_priority_band(score, default_research_signal_config())


def outlier_sensitive(row: Mapping[str, str]) -> bool:
    median_price = number(row.get("median_asking_price", ""))
    maximum_price = number(row.get("maximum_asking_price", ""))
    return median_price > 0 and maximum_price >= median_price * 5


def score_band_issue_rows(scenario: str) -> list[dict[str, str]]:
    return [
        summary_row(
            section="band_interpretation",
            scenario=scenario,
            metric="validation_2_3_band",
            value="empty_in_expanded_sample",
            notes="The validation sampling band remains empty because the catalog has no population there.",
        ),
        summary_row(
            section="band_interpretation",
            scenario=scenario,
            metric="validation_6_7_band",
            value="sparse_in_expanded_sample",
            notes="Only five expanded-sample books occupy the validation 6-7 band.",
        ),
        summary_row(
            section="band_interpretation",
            scenario=scenario,
            metric="validation_8_plus_band",
            value="open_ended",
            notes=(
                "The validation label 8-10 contains every raw score of 8 or greater; "
                "production bands are reported separately."
            ),
        ),
    ]


def summary_row(
    *,
    section: str,
    scenario: str,
    metric: str,
    value: int | str,
    score_band: str = "",
    percentage_value: str = "",
    baseline_value: int | str = "",
    delta: str = "",
    notes: str = "",
) -> dict[str, str]:
    return {
        "section": section,
        "scenario": scenario,
        "metric": metric,
        "score_band": score_band,
        "value": str(value),
        "percentage": percentage_value,
        "baseline_value": str(baseline_value),
        "delta": delta,
        "notes": notes,
    }


def numeric_delta(value: int | str, baseline: int | str) -> str:
    try:
        return signed(float(value) - float(baseline))
    except (TypeError, ValueError):
        return ""


def ratio(count: int, total: int) -> str:
    return f"{count / total:.1%}" if total else ""


def signed(value: int | float) -> str:
    if isinstance(value, float):
        return f"{value:+.2f}"
    return f"{value:+d}"


def integer(value: str | int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def number(value: str | float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def decimal(value: float) -> str:
    return f"{value:.2f}"


def money_or_blank(value: float | int | None) -> str:
    return f"{value:.2f}" if value is not None else ""


def yes_no(value: bool) -> str:
    return "yes" if value else "no"

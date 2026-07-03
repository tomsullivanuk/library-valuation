"""Relative pricing score (RPS) primitives for future valuation work."""

from __future__ import annotations

from collections.abc import Mapping


DEFAULT_RPS_WEIGHTS = {
    "publisher_tier": 0.35,
    "subject_signal": 0.30,
    "scarcity": 0.25,
    "condition": 0.10,
}


def calculate_rps(
    signals: Mapping[str, float] | None = None,
    weights: Mapping[str, float] | None = None,
) -> float:
    """Return a weighted relative pricing score for normalized valuation signals.

    Signal values are expected to be normalized from 0.0 to 1.0. Missing signals
    contribute zero. This intentionally small implementation establishes the
    public API without changing the existing catalog pipeline behavior.
    """
    signals = signals or {}
    active_weights = weights or DEFAULT_RPS_WEIGHTS
    return round(sum(float(signals.get(name, 0.0)) * weight for name, weight in active_weights.items()), 4)


def empty_rps_breakdown() -> dict[str, float | dict[str, float]]:
    """Return the default empty RPS result shape used by future valuation rows."""
    return {"score": 0.0, "signals": {}}


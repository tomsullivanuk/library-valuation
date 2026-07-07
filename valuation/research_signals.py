"""Deterministic research signals for collector attention."""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path

import yaml


DEFAULT_RESEARCH_SIGNAL_WEIGHTS = {
    "old_publication_year": 12,
    "university_press": 15,
    "specialist_publisher": 10,
    "missing_lcc": 8,
    "missing_oclc": 5,
    "scholarly_lc_subject": 10,
    "multiple_acquisitions": 6,
    "low_metadata_confidence": 6,
}

DEFAULT_OLD_PUBLICATION_YEAR_THRESHOLD = 1950


@dataclass(frozen=True)
class ResearchSignal:
    signal_code: str
    signal_label: str
    points: int
    evidence_field: str
    evidence_value: str
    explanation: str

    def as_dict(self) -> dict[str, str]:
        return {
            "signal_code": self.signal_code,
            "signal_label": self.signal_label,
            "points": str(self.points),
            "evidence_field": self.evidence_field,
            "evidence_value": self.evidence_value,
            "explanation": self.explanation,
        }


@dataclass(frozen=True)
class ResearchSignalConfig:
    weights: Mapping[str, int]
    old_publication_year_threshold: int = DEFAULT_OLD_PUBLICATION_YEAR_THRESHOLD
    publisher_tiers: Mapping[str, list[str]] | None = None
    scholarly_lc_classes: Mapping[str, str] | None = None

    def points(self, signal_code: str) -> int:
        return int(self.weights.get(signal_code, 0))


def default_research_signal_config() -> ResearchSignalConfig:
    return ResearchSignalConfig(weights=dict(DEFAULT_RESEARCH_SIGNAL_WEIGHTS))


def load_research_signal_config(config_dir: Path) -> ResearchSignalConfig:
    signal_config = _read_yaml_mapping(config_dir / "research_signals.yml")
    publisher_config = _read_yaml_mapping(config_dir / "publisher_tiers.yml")
    subject_config = _read_yaml_mapping(config_dir / "lc_subjects.yml")

    weights = dict(DEFAULT_RESEARCH_SIGNAL_WEIGHTS)
    weights.update({key: int(value) for key, value in signal_config.get("weights", {}).items()})
    threshold = int(signal_config.get("old_publication_year_threshold", DEFAULT_OLD_PUBLICATION_YEAR_THRESHOLD))

    return ResearchSignalConfig(
        weights=weights,
        old_publication_year_threshold=threshold,
        publisher_tiers=_publisher_tier_patterns(publisher_config),
        scholarly_lc_classes=_lc_subject_labels(subject_config),
    )


def generate_research_signals(
    catalog_item: Mapping[str, str],
    metadata: Mapping[str, str] | None = None,
    acquisitions: Iterable[Mapping[str, str]] | None = None,
    config: ResearchSignalConfig | None = None,
) -> list[ResearchSignal]:
    """Return deterministic reasons a catalog item may deserve attention."""
    config = config or default_research_signal_config()
    metadata = metadata or {}
    acquisition_rows = list(acquisitions or [])
    item = _merged_item(catalog_item, metadata)

    signals = [
        signal
        for signal in [
            _old_publication_year_signal(item, config),
            _publisher_signal(item, config),
            _missing_lcc_signal(item, config),
            _missing_oclc_signal(item, config),
            _scholarly_lc_subject_signal(item, config),
            _multiple_acquisitions_signal(item, acquisition_rows, config),
            _low_metadata_confidence_signal(item, config),
        ]
        if signal is not None
    ]
    return sorted(signals, key=lambda signal: signal.signal_code)


def _old_publication_year_signal(item: Mapping[str, str], config: ResearchSignalConfig) -> ResearchSignal | None:
    year = _publication_year(item.get("publication_year", "") or item.get("publish_date", ""))
    if not year or year >= config.old_publication_year_threshold:
        return None
    return ResearchSignal(
        signal_code="old_publication_year",
        signal_label="Older publication",
        points=config.points("old_publication_year"),
        evidence_field="publication_year",
        evidence_value=str(year),
        explanation=f"Published before {config.old_publication_year_threshold}.",
    )


def _publisher_signal(item: Mapping[str, str], config: ResearchSignalConfig) -> ResearchSignal | None:
    publisher = item.get("publisher", "") or item.get("publishers", "")
    normalized = _normalize_text(publisher)
    if not normalized:
        return None

    tier = _matching_publisher_tier(normalized, config.publisher_tiers or {})
    if tier == "university_press" or "university press" in normalized:
        return ResearchSignal(
            signal_code="university_press",
            signal_label="University press",
            points=config.points("university_press"),
            evidence_field="publisher",
            evidence_value=publisher,
            explanation="Published by a university press.",
        )
    if tier and tier != "general_trade":
        return ResearchSignal(
            signal_code="specialist_publisher",
            signal_label="Specialist publisher",
            points=config.points("specialist_publisher"),
            evidence_field="publisher",
            evidence_value=publisher,
            explanation="Published by a specialist or scholarly publisher.",
        )
    return None


def _missing_lcc_signal(item: Mapping[str, str], config: ResearchSignalConfig) -> ResearchSignal | None:
    if item.get("lcc"):
        return None
    return ResearchSignal(
        signal_code="missing_lcc",
        signal_label="Missing LC classification",
        points=config.points("missing_lcc"),
        evidence_field="lcc",
        evidence_value="",
        explanation="LC classification is missing, so bibliographic review may be useful.",
    )


def _missing_oclc_signal(item: Mapping[str, str], config: ResearchSignalConfig) -> ResearchSignal | None:
    if item.get("oclc"):
        return None
    return ResearchSignal(
        signal_code="missing_oclc",
        signal_label="Missing OCLC identifier",
        points=config.points("missing_oclc"),
        evidence_field="oclc",
        evidence_value="",
        explanation="OCLC identifier is missing, which may make edition matching harder.",
    )


def _scholarly_lc_subject_signal(item: Mapping[str, str], config: ResearchSignalConfig) -> ResearchSignal | None:
    lcc = item.get("lcc", "")
    lc_class = _first_lc_class(lcc)
    subject_label = (config.scholarly_lc_classes or {}).get(lc_class)
    if not subject_label:
        return None
    return ResearchSignal(
        signal_code="scholarly_lc_subject",
        signal_label="Scholarly LC subject",
        points=config.points("scholarly_lc_subject"),
        evidence_field="lcc",
        evidence_value=lcc,
        explanation=f"LC class {lc_class} suggests research interest: {subject_label}.",
    )


def _multiple_acquisitions_signal(
    item: Mapping[str, str], acquisitions: list[Mapping[str, str]], config: ResearchSignalConfig
) -> ResearchSignal | None:
    catalog_item_id = item.get("catalog_item_id", "")
    acquisition_count = sum(1 for row in acquisitions if row.get("catalog_item_id") == catalog_item_id)
    if acquisition_count <= 1:
        acquisition_count = _safe_int(item.get("purchase_count", ""))
    if acquisition_count <= 1:
        return None
    return ResearchSignal(
        signal_code="multiple_acquisitions",
        signal_label="Multiple acquisitions",
        points=config.points("multiple_acquisitions"),
        evidence_field="acquisition_count",
        evidence_value=str(acquisition_count),
        explanation="Multiple acquisitions may indicate duplicate copies, replacement copies, or a collected work.",
    )


def _low_metadata_confidence_signal(item: Mapping[str, str], config: ResearchSignalConfig) -> ResearchSignal | None:
    source = item.get("resolution_source", "")
    confidence = item.get("resolution_confidence", "")
    status = item.get("openlibrary_status", "")
    if source == "manual_review" or confidence in {"low", "medium"} or (status and status != "matched"):
        evidence = confidence or source or status
        return ResearchSignal(
            signal_code="low_metadata_confidence",
            signal_label="Low metadata confidence",
            points=config.points("low_metadata_confidence"),
            evidence_field="resolution_confidence",
            evidence_value=evidence,
            explanation="Metadata resolution is incomplete or uncertain.",
        )
    return None


def _merged_item(catalog_item: Mapping[str, str], metadata: Mapping[str, str]) -> dict[str, str]:
    item = dict(catalog_item)
    for key, value in metadata.items():
        if value or key not in item:
            item[key] = value
    return item


def _publisher_tier_patterns(config: Mapping[str, object]) -> dict[str, list[str]]:
    tiers = config.get("tiers", {})
    if not isinstance(tiers, Mapping):
        return {}
    examples_by_tier: dict[str, list[str]] = {}
    for tier_name, tier_config in tiers.items():
        if isinstance(tier_config, Mapping):
            examples = tier_config.get("examples", [])
            if isinstance(examples, list):
                examples_by_tier[str(tier_name)] = [str(example) for example in examples]
    return examples_by_tier


def _lc_subject_labels(config: Mapping[str, object]) -> dict[str, str]:
    subjects = config.get("subjects", {})
    if not isinstance(subjects, Mapping):
        return {}
    labels = {}
    for lc_class, subject_config in subjects.items():
        if isinstance(subject_config, Mapping):
            labels[str(lc_class)] = str(subject_config.get("label", lc_class))
    return labels


def _matching_publisher_tier(normalized_publisher: str, tiers: Mapping[str, list[str]]) -> str:
    for tier_name, examples in tiers.items():
        for example in examples:
            normalized_example = _normalize_text(example)
            if normalized_example and normalized_example in normalized_publisher:
                return tier_name
    return ""


def _publication_year(value: str) -> int | None:
    match = re.search(r"\b(\d{4})\b", value or "")
    return int(match.group(1)) if match else None


def _first_lc_class(lcc: str) -> str:
    match = re.search(r"\b([A-Z]{1,3})\d", lcc or "")
    return match.group(1)[0] if match else ""


def _safe_int(value: str) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _normalize_text(value: str) -> str:
    return " ".join(re.findall(r"[a-z0-9]+", (value or "").lower()))


def _read_yaml_mapping(path: Path) -> dict[str, object]:
    if not path.exists():
        return {}
    with path.open(encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}
    return data if isinstance(data, dict) else {}

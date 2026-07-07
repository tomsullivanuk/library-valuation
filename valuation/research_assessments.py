"""Research assessments derived from deterministic research signals."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import datetime, timezone

from valuation.research_signals import (
    ResearchSignal,
    ResearchSignalConfig,
    default_research_signal_config,
    generate_research_signals,
)


RESEARCH_MODEL_VERSION = "0.3.0"
NO_RESEARCH_SIGNALS_EXPLANATION = "No research signals generated."


@dataclass(frozen=True)
class ResearchAssessment:
    catalog_item_id: str
    isbn13: str
    research_priority_score: int
    research_priority_band: str
    research_signal_count: int
    research_signal_codes: str
    research_signal_summary: str
    research_signal_explanations: str
    research_model_version: str
    research_config_hash: str
    assessed_at: str
    assessment_status: str
    acquisition_snapshot_hash: str
    metadata_snapshot_hash: str

    def as_dict(self) -> dict[str, str]:
        return {
            "catalog_item_id": self.catalog_item_id,
            "isbn13": self.isbn13,
            "research_priority_score": str(self.research_priority_score),
            "research_priority_band": self.research_priority_band,
            "research_signal_count": str(self.research_signal_count),
            "research_signal_codes": self.research_signal_codes,
            "research_signal_summary": self.research_signal_summary,
            "research_signal_explanations": self.research_signal_explanations,
            "research_model_version": self.research_model_version,
            "research_config_hash": self.research_config_hash,
            "assessed_at": self.assessed_at,
            "assessment_status": self.assessment_status,
            "acquisition_snapshot_hash": self.acquisition_snapshot_hash,
            "metadata_snapshot_hash": self.metadata_snapshot_hash,
        }


def build_research_assessment(
    metadata: Mapping[str, str],
    acquisitions: Iterable[Mapping[str, str]] | None = None,
    config: ResearchSignalConfig | None = None,
    assessed_at: str | None = None,
) -> dict[str, str]:
    config = config or default_research_signal_config()
    acquisition_rows = list(acquisitions or [])
    signals = generate_research_signals(metadata, acquisitions=acquisition_rows, config=config)
    score = research_priority_score(signals)
    assessment = ResearchAssessment(
        catalog_item_id=metadata.get("catalog_item_id", ""),
        isbn13=metadata.get("isbn13", ""),
        research_priority_score=score,
        research_priority_band=research_priority_band(score, config),
        research_signal_count=len(signals),
        research_signal_codes=research_signal_codes(signals),
        research_signal_summary=research_signal_summary(signals),
        research_signal_explanations=research_signal_explanations(signals),
        research_model_version=RESEARCH_MODEL_VERSION,
        research_config_hash=research_config_hash(config),
        assessed_at=assessed_at or utc_timestamp(),
        assessment_status="current",
        acquisition_snapshot_hash=acquisition_snapshot_hash(acquisition_rows),
        metadata_snapshot_hash=metadata_snapshot_hash(metadata),
    )
    return assessment.as_dict()


def research_priority_score(signals: Iterable[ResearchSignal]) -> int:
    return sum(signal.points for signal in signals)


def research_priority_band(score: int, config: ResearchSignalConfig) -> str:
    if score >= config.band_threshold("high"):
        return "high"
    if score >= config.band_threshold("medium"):
        return "medium"
    if score >= config.band_threshold("low"):
        return "low"
    return "none"


def research_signal_codes(signals: Iterable[ResearchSignal]) -> str:
    return "; ".join(signal.signal_code for signal in signals)


def research_signal_summary(signals: Iterable[ResearchSignal]) -> str:
    return "; ".join(f"{signal.signal_code}:+{signal.points}" for signal in signals)


def research_signal_explanations(signals: Iterable[ResearchSignal]) -> str:
    explanations = [signal.explanation for signal in signals]
    return " | ".join(explanations) if explanations else NO_RESEARCH_SIGNALS_EXPLANATION


def research_config_hash(config: ResearchSignalConfig) -> str:
    return stable_json_hash(
        {
            "weights": dict(sorted(config.weights.items())),
            "old_publication_year_threshold": config.old_publication_year_threshold,
            "bands": dict(sorted(config.effective_band_thresholds().items())),
            "publisher_tiers": {
                key: sorted(values)
                for key, values in sorted((config.publisher_tiers or {}).items())
            },
            "scholarly_lc_classes": dict(sorted((config.scholarly_lc_classes or {}).items())),
        }
    )


def metadata_snapshot_hash(metadata: Mapping[str, str]) -> str:
    scoring_metadata = {
        "catalog_item_id": metadata.get("catalog_item_id", ""),
        "isbn13": metadata.get("isbn13", ""),
        "isbn10": metadata.get("isbn10", ""),
        "title": metadata.get("title", ""),
        "authors": metadata.get("authors", ""),
        "publishers": metadata.get("publishers", ""),
        "publish_date": metadata.get("publish_date", ""),
        "publication_year": metadata.get("publication_year", ""),
        "lcc": metadata.get("lcc", ""),
        "oclc": metadata.get("oclc", ""),
        "subjects": metadata.get("subjects", ""),
        "resolution_source": metadata.get("resolution_source", ""),
        "resolution_confidence": metadata.get("resolution_confidence", ""),
        "openlibrary_status": metadata.get("openlibrary_status", ""),
        "purchase_count": metadata.get("purchase_count", ""),
    }
    return stable_json_hash(scoring_metadata)


def acquisition_snapshot_hash(acquisitions: Iterable[Mapping[str, str]]) -> str:
    relevant_rows = []
    for acquisition in acquisitions:
        relevant_rows.append(
            {
                "acquisition_id": acquisition.get("acquisition_id", ""),
                "catalog_item_id": acquisition.get("catalog_item_id", ""),
                "source": acquisition.get("source", ""),
                "source_order_id": acquisition.get("source_order_id", ""),
                "source_item_id": acquisition.get("source_item_id", ""),
                "order_date": acquisition.get("order_date", ""),
                "quantity": acquisition.get("quantity", ""),
                "item_price": acquisition.get("item_price", ""),
                "item_subtotal": acquisition.get("item_subtotal", ""),
                "currency": acquisition.get("currency", ""),
                "source_title": acquisition.get("source_title", ""),
                "source_asin": acquisition.get("source_asin", ""),
                "isbn13": acquisition.get("isbn13", ""),
                "isbn10": acquisition.get("isbn10", ""),
            }
        )
    return stable_json_hash(sorted(relevant_rows, key=lambda row: (row["acquisition_id"], row["source_item_id"])))


def stable_json_hash(value: object) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")

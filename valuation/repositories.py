"""CSV repositories for durable library pipeline state."""

from __future__ import annotations

import csv
from pathlib import Path


CATALOG_ITEMS_FIELDNAMES = [
    "catalog_item_id",
    "isbn13",
    "isbn10",
    "title",
    "author",
    "publisher",
    "publication_year",
    "source_fingerprint",
    "match_confidence",
]

ACQUISITION_FIELDNAMES = [
    "acquisition_id",
    "catalog_item_id",
    "source",
    "source_order_id",
    "source_item_id",
    "order_date",
    "quantity",
    "item_price",
    "item_subtotal",
    "currency",
    "source_title",
    "source_asin",
    "isbn13",
    "isbn10",
]

IMPORT_MANIFEST_FIELDNAMES = [
    "import_id",
    "filename",
    "file_hash",
    "imported_at",
    "pipeline_version",
    "schema_version",
    "amazon_row_count",
    "book_candidates",
    "catalog_matches",
    "new_catalog_items",
    "acquisition_rows",
    "status",
    "notes",
]

RESEARCH_ASSESSMENT_FIELDNAMES = [
    "catalog_item_id",
    "isbn13",
    "research_priority_score",
    "research_priority_band",
    "research_signal_count",
    "research_signal_codes",
    "research_signal_summary",
    "research_signal_explanations",
    "research_model_version",
    "research_config_hash",
    "assessed_at",
    "assessment_status",
    "acquisition_snapshot_hash",
    "metadata_snapshot_hash",
]

COLLECTOR_REVIEW_FIELDNAMES = [
    "catalog_item_id",
    "workflow_state",
    "disposition",
    "priority_override",
    "reviewed_at",
    "reviewed_by",
    "review_notes",
    "created_at",
    "updated_at",
]


class CsvRepository:
    fieldnames: list[str] = []

    def __init__(self, path: Path):
        self.path = path

    def load(self) -> list[dict[str, str]]:
        if not self.path.exists():
            return []
        with self.path.open(newline="", encoding="utf-8") as handle:
            return [{field: row.get(field, "") for field in self.fieldnames} for row in csv.DictReader(handle)]

    def save(self, rows: list[dict[str, str]]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=self.fieldnames)
            writer.writeheader()
            writer.writerows({field: row.get(field, "") for field in self.fieldnames} for row in rows)

    def ensure_exists(self) -> None:
        if not self.path.exists():
            self.save([])


class CatalogRepository(CsvRepository):
    fieldnames = CATALOG_ITEMS_FIELDNAMES


class AcquisitionRepository(CsvRepository):
    fieldnames = ACQUISITION_FIELDNAMES


class ImportManifestRepository(CsvRepository):
    fieldnames = IMPORT_MANIFEST_FIELDNAMES

    def append(self, row: dict[str, str]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        should_write_header = not self.path.exists() or self.path.stat().st_size == 0
        with self.path.open("a", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=self.fieldnames)
            if should_write_header:
                writer.writeheader()
            writer.writerow({field: row.get(field, "") for field in self.fieldnames})


class ResearchAssessmentRepository(CsvRepository):
    fieldnames = RESEARCH_ASSESSMENT_FIELDNAMES


class CollectorReviewRepository(CsvRepository):
    fieldnames = COLLECTOR_REVIEW_FIELDNAMES

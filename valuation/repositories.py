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


class CatalogRepository(CsvRepository):
    fieldnames = CATALOG_ITEMS_FIELDNAMES


class AcquisitionRepository(CsvRepository):
    fieldnames = ACQUISITION_FIELDNAMES

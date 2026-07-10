#!/usr/bin/env python3
"""Extract and enrich Amazon book purchases with library metadata."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import platform
import re
import shutil
import ssl
import subprocess
import sys
import tempfile
import time
import urllib.parse
import urllib.request
import zipfile
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from xml.sax.saxutils import escape

from valuation.abebooks import (
    MARKET_OBSERVATION_FIELDNAMES,
    collect_abebooks_observation_rows,
    fetch_url,
)
from valuation.collector_workbook import write_collector_workbook
from valuation.market_validation import (
    MARKET_VALIDATION_SAMPLE_METADATA_FIELDNAMES,
    MARKET_VALIDATION_SAMPLE_FIELDNAMES,
    build_market_validation_sample_metadata_rows,
    build_market_validation_sample_rows,
)
from valuation.market_validation_analysis import (
    MARKET_VALIDATION_ANALYSIS_FIELDNAMES,
    build_market_validation_analysis_rows,
)
from valuation.market_observation_coverage import (
    MARKET_OBSERVATION_COVERAGE_FIELDNAMES,
    build_market_observation_coverage_rows,
)
from valuation.research_assessments import (
    RESEARCH_MODEL_VERSION,
    acquisition_snapshot_hash,
    build_research_assessment,
    metadata_snapshot_hash,
    research_config_hash,
)
from valuation.research_candidates import (
    RESEARCH_CANDIDATE_FIELDNAMES,
    build_research_candidate_rows,
)
from valuation.research_signal_effectiveness import (
    RESEARCH_SIGNAL_EFFECTIVENESS_FIELDNAMES,
    build_research_signal_effectiveness_rows,
)
from valuation.research_signals import (
    ResearchSignalConfig,
    default_research_signal_config,
    load_research_signal_config,
)
from valuation.repositories import (
    ACQUISITION_FIELDNAMES,
    CATALOG_ITEMS_FIELDNAMES,
    AcquisitionRepository,
    CatalogRepository,
    CollectorReviewRepository,
    ImportManifestRepository,
    ResearchAssessmentRepository,
)


class UserFacingError(ValueError):
    """Expected CLI error that should be shown without a traceback."""


BOOK_FIELDNAMES = [
    "asin",
    "isbn10",
    "isbn13",
    "order_date",
    "order_id",
    "product_name",
    "product_condition",
    "quantity",
    "unit_price",
    "currency",
    "website",
]

AMAZON_ORDER_HISTORY_REQUIRED_COLUMNS = [
    "ASIN",
    "Order Date",
    "Order ID",
    "Product Name",
    "Product Condition",
    "Original Quantity",
    "Unit Price",
    "Currency",
    "Website",
]

ENRICHED_FIELDNAMES = BOOK_FIELDNAMES + [
    "openlibrary_status",
    "openlibrary_url",
    "title",
    "authors",
    "publishers",
    "publish_date",
    "lcc",
    "dewey",
    "lccn",
    "oclc",
    "subjects",
]

RESOLVED_FIELDNAMES = ENRICHED_FIELDNAMES + [
    "resolution_source",
    "resolution_confidence",
    "resolution_notes",
    "resolved_query",
]

BOOK_METADATA_FIELDNAMES = [
    "catalog_item_id",
    "isbn13",
    "isbn10",
    "asin",
    "purchase_count",
    "total_quantity",
    "first_order_date",
    "latest_order_date",
    "representative_product_name",
    "product_names",
    "openlibrary_status",
    "openlibrary_url",
    "title",
    "authors",
    "publishers",
    "publish_date",
    "lcc",
    "dewey",
    "lccn",
    "oclc",
    "subjects",
    "resolution_source",
    "resolution_confidence",
    "resolution_notes",
    "resolved_query",
]

LIBRARY_CATALOG_FIELDNAMES = [
    "catalog_item_id",
    "lcc",
    "title",
    "authors",
    "purchase_date",
    "isbn13",
    "isbn10",
    "product_name",
    "quantity",
    "unit_price",
    "currency",
    "order_id",
    "openlibrary_url",
    "resolution_source",
    "resolution_confidence",
    "subjects",
]

VALUATION_EXTENSION_STAGE = "post_catalog_rows"
PIPELINE_VERSION = "0.2.0"
SCHEMA_VERSION = "1"


@dataclass(frozen=True)
class LibraryPaths:
    """Central project paths for the library pipeline."""

    input_dir: Path = Path("input")
    amazon_input_dir: Path = Path("input/amazon")
    data_dir: Path = Path("data")
    cache_dir: Path = Path("cache")
    openlibrary_cache_dir: Path = Path("cache/openlibrary")
    config_dir: Path = Path("config")
    output_dir: Path = Path("output")

    @property
    def openlibrary_isbn_cache_path(self) -> Path:
        return self.openlibrary_cache_dir / "isbn.json"

    @property
    def openlibrary_search_cache_path(self) -> Path:
        return self.openlibrary_cache_dir / "search.json"

    @property
    def catalog_items_path(self) -> Path:
        return self.data_dir / "catalog_items.csv"

    @property
    def acquisitions_path(self) -> Path:
        return self.data_dir / "acquisitions.csv"

    @property
    def import_manifest_path(self) -> Path:
        return self.data_dir / "import_manifest.csv"

    @property
    def research_priority_assessments_path(self) -> Path:
        return self.data_dir / "research_priority_assessments.csv"

    @property
    def collector_reviews_path(self) -> Path:
        return self.data_dir / "collector_reviews.csv"

    def ensure_directories(self) -> None:
        for path in (
            self.input_dir,
            self.amazon_input_dir,
            self.data_dir,
            self.cache_dir,
            self.openlibrary_cache_dir,
            self.config_dir,
            self.output_dir,
        ):
            path.mkdir(parents=True, exist_ok=True)


def valuation_extension_context(
    purchases: list[dict[str, str]],
    metadata_rows: list[dict[str, str]],
    catalog_rows: list[dict[str, str]],
) -> dict[str, list[dict[str, str]] | str]:
    """Return the stable handoff shape for future valuation generation.

    The existing pipeline does not generate valuation outputs yet; this context
    simply names the post-catalog extension point for a later sprint.
    """
    return {
        "stage": VALUATION_EXTENSION_STAGE,
        "purchases": purchases,
        "metadata_rows": metadata_rows,
        "catalog_rows": catalog_rows,
    }


def paired_output_paths(output_path: Path) -> tuple[Path, Path]:
    if output_path.suffix.lower() == ".xlsx":
        return output_path.with_suffix(".csv"), output_path
    if output_path.suffix.lower() == ".csv":
        return output_path, output_path.with_suffix(".xlsx")
    return output_path.with_suffix(".csv"), output_path.with_suffix(".xlsx")


def write_table_outputs(output_path: Path, fieldnames: list[str], rows: list[dict[str, str]], sheet_name: str) -> tuple[Path, Path]:
    csv_path, xlsx_path = paired_output_paths(output_path)
    write_csv(csv_path, fieldnames, rows)
    write_xlsx(xlsx_path, fieldnames, rows, sheet_name)
    return csv_path, xlsx_path


def write_csv(output_path: Path, fieldnames: list[str], rows: list[dict[str, str]]) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def read_csv_rows(input_path: Path) -> list[dict[str, str]]:
    if not input_path.exists():
        raise UserFacingError(f"Required input file not found: {input_path}")
    with input_path.open(newline="", encoding="utf-8-sig") as handle:
        return [dict(row) for row in csv.DictReader(handle)]


def read_optional_csv_rows(input_path: Path) -> list[dict[str, str]]:
    if not input_path.exists():
        return []
    return read_csv_rows(input_path)


def write_xlsx(output_path: Path, fieldnames: list[str], rows: list[dict[str, str]], sheet_name: str) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    sheet_xml = build_sheet_xml(fieldnames, rows)
    workbook_xml = build_workbook_xml(sheet_name)
    with zipfile.ZipFile(output_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", CONTENT_TYPES_XML)
        archive.writestr("_rels/.rels", ROOT_RELS_XML)
        archive.writestr("docProps/app.xml", APP_XML)
        archive.writestr("docProps/core.xml", CORE_XML)
        archive.writestr("xl/workbook.xml", workbook_xml)
        archive.writestr("xl/_rels/workbook.xml.rels", WORKBOOK_RELS_XML)
        archive.writestr("xl/styles.xml", STYLES_XML)
        archive.writestr("xl/worksheets/sheet1.xml", sheet_xml)


def build_sheet_xml(fieldnames: list[str], rows: list[dict[str, str]]) -> str:
    row_count = len(rows) + 1
    col_count = len(fieldnames)
    dimension = f"A1:{excel_col(col_count)}{row_count}"
    widths = column_widths(fieldnames, rows)
    cols = "".join(
        f'<col min="{index}" max="{index}" width="{width}" customWidth="1"/>'
        for index, width in enumerate(widths, start=1)
    )
    body = [build_row_xml(1, fieldnames, style="1")]
    for index, row in enumerate(rows, start=2):
        body.append(build_row_xml(index, [row.get(field, "") for field in fieldnames]))
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        f'<dimension ref="{dimension}"/>'
        '<sheetViews><sheetView tabSelected="1" workbookViewId="0">'
        '<pane ySplit="1" topLeftCell="A2" activePane="bottomLeft" state="frozen"/>'
        '<selection pane="bottomLeft" activeCell="A2" sqref="A2"/>'
        '</sheetView></sheetViews>'
        '<sheetFormatPr defaultRowHeight="15"/>'
        f"<cols>{cols}</cols>"
        f"<sheetData>{''.join(body)}</sheetData>"
        f'<autoFilter ref="{dimension}"/>'
        "</worksheet>"
    )


def build_row_xml(row_index: int, values: list[str], style: str | None = None) -> str:
    cells = []
    style_attr = f' s="{style}"' if style else ""
    for col_index, value in enumerate(values, start=1):
        cell_ref = f"{excel_col(col_index)}{row_index}"
        text = escape(xml_safe_text(value))
        cells.append(f'<c r="{cell_ref}" t="inlineStr"{style_attr}><is><t>{text}</t></is></c>')
    return f'<row r="{row_index}">{"".join(cells)}</row>'


def xml_safe_text(value: str) -> str:
    text = str(value or "")
    safe_chars = []
    for char in text[:32767]:
        codepoint = ord(char)
        if char in "\t\n\r" or codepoint >= 32 and not (0xD800 <= codepoint <= 0xDFFF) and codepoint not in (0xFFFE, 0xFFFF):
            safe_chars.append(char)
        else:
            safe_chars.append(" ")
    return "".join(safe_chars)


def column_widths(fieldnames: list[str], rows: list[dict[str, str]]) -> list[int]:
    widths = []
    for field in fieldnames:
        max_len = len(field)
        for row in rows[:1000]:
            max_len = max(max_len, len(str(row.get(field, ""))))
        widths.append(min(max(max_len + 2, 10), 60))
    return widths


def excel_col(index: int) -> str:
    letters = ""
    while index:
        index, remainder = divmod(index - 1, 26)
        letters = chr(65 + remainder) + letters
    return letters


def build_workbook_xml(sheet_name: str) -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        "<sheets>"
        f'<sheet name="{escape(sheet_name)}" sheetId="1" r:id="rId1"/>'
        "</sheets>"
        "</workbook>"
    )


CONTENT_TYPES_XML = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/docProps/app.xml" ContentType="application/vnd.openxmlformats-officedocument.extended-properties+xml"/>
  <Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/>
  <Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>
  <Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>
  <Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>
</Types>"""

ROOT_RELS_XML = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>
  <Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/>
  <Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/extended-properties" Target="docProps/app.xml"/>
</Relationships>"""

WORKBOOK_RELS_XML = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>
  <Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>
</Relationships>"""

APP_XML = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/extended-properties" xmlns:vt="http://schemas.openxmlformats.org/officeDocument/2006/docPropsVTypes">
  <Application>Amazon Library Pipeline</Application>
</Properties>"""

CORE_XML = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:dcterms="http://purl.org/dc/terms/" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
  <dc:creator>Amazon Library Pipeline</dc:creator>
  <dc:title>Amazon Library Export</dc:title>
</cp:coreProperties>"""

STYLES_XML = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
  <fonts count="2"><font><sz val="11"/><name val="Calibri"/></font><font><b/><sz val="11"/><name val="Calibri"/></font></fonts>
  <fills count="2"><fill><patternFill patternType="none"/></fill><fill><patternFill patternType="gray125"/></fill></fills>
  <borders count="1"><border><left/><right/><top/><bottom/><diagonal/></border></borders>
  <cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>
  <cellXfs count="2"><xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/><xf numFmtId="0" fontId="1" fillId="0" borderId="0" xfId="0" applyFont="1"/></cellXfs>
  <cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles>
</styleSheet>"""


def normalize_isbn(value: str) -> str:
    return re.sub(r"[^0-9Xx]", "", value or "").upper()


def is_valid_isbn10(isbn: str) -> bool:
    isbn = normalize_isbn(isbn)
    if not re.fullmatch(r"[0-9]{9}[0-9X]", isbn):
        return False
    total = 0
    for index, char in enumerate(isbn):
        value = 10 if char == "X" else int(char)
        total += (10 - index) * value
    return total % 11 == 0


def is_valid_isbn13(isbn: str) -> bool:
    isbn = normalize_isbn(isbn)
    if not re.fullmatch(r"[0-9]{13}", isbn):
        return False
    total = 0
    for index, char in enumerate(isbn[:12]):
        total += int(char) * (1 if index % 2 == 0 else 3)
    check = (10 - (total % 10)) % 10
    return check == int(isbn[-1])


def isbn10_to_isbn13(isbn10: str) -> str:
    isbn10 = normalize_isbn(isbn10)
    if not is_valid_isbn10(isbn10):
        raise ValueError(f"Invalid ISBN-10: {isbn10}")
    stem = "978" + isbn10[:9]
    total = 0
    for index, char in enumerate(stem):
        total += int(char) * (1 if index % 2 == 0 else 3)
    check = (10 - (total % 10)) % 10
    return stem + str(check)


def classify_asin(asin: str) -> str:
    raw = (asin or "").strip().upper()
    if not raw:
        return "blank"
    if raw.startswith("B"):
        return "amazon_asin"
    value = normalize_isbn(raw)
    if len(value) == 10 and is_valid_isbn10(value):
        return "isbn10"
    if len(value) == 13 and is_valid_isbn13(value):
        return "isbn13"
    return "unknown_non_b"


def iter_amazon_rows(input_path: Path):
    with input_path.open(newline="", encoding="utf-8-sig") as handle:
        yield from csv.DictReader(handle)


@contextmanager
def resolve_amazon_order_history_input(input_path: Path):
    if input_path.is_file() and input_path.suffix.lower() == ".csv":
        yield input_path
        return
    if input_path.is_dir():
        yield find_order_history_csv(iter_order_history_candidates(input_path))
        return
    if input_path.is_file() and input_path.suffix.lower() == ".zip":
        with tempfile.TemporaryDirectory() as temp_dir:
            try:
                with zipfile.ZipFile(input_path) as archive:
                    safe_extract_zip(archive, Path(temp_dir))
            except zipfile.BadZipFile as error:
                raise UserFacingError(f"Unsupported Amazon input: {input_path} is not a readable ZIP file.") from error
            yield find_order_history_csv(iter_order_history_candidates(Path(temp_dir)))
        return
    raise UserFacingError(f"Unsupported Amazon input: {input_path}. Expected a CSV file, ZIP file, or directory.")


def iter_order_history_candidates(root: Path):
    yield from root.rglob("Order History.csv")
    yield from root.rglob("Retail.OrderHistory.1.csv")


def find_order_history_csv(candidates_iterable) -> Path:
    candidates = sorted(Path(candidate) for candidate in candidates_iterable)
    if not candidates:
        raise UserFacingError(
            "No Amazon order history CSV found. Expected 'Your Amazon Orders/Order History.csv' "
            "or 'Retail.OrderHistory.1/Retail.OrderHistory.1.csv'."
        )
    preferred = [candidate for candidate in candidates if is_preferred_order_history_path(candidate)]
    if len(preferred) == 1:
        return preferred[0]
    retail = [candidate for candidate in candidates if is_retail_order_history_1_path(candidate)]
    if len(retail) == 1:
        validate_order_history_schema(retail[0])
        return retail[0]
    order_history = [candidate for candidate in candidates if candidate.name == "Order History.csv"]
    if len(order_history) == 1:
        return order_history[0]
    candidate_list = "\n".join(str(candidate) for candidate in candidates)
    raise UserFacingError(f"Multiple ambiguous Amazon order history CSV files found:\n{candidate_list}")


def is_preferred_order_history_path(path: Path) -> bool:
    parts = path.parts
    return len(parts) >= 2 and parts[-2:] == ("Your Amazon Orders", "Order History.csv")


def is_retail_order_history_1_path(path: Path) -> bool:
    parts = path.parts
    return len(parts) >= 2 and parts[-2:] == ("Retail.OrderHistory.1", "Retail.OrderHistory.1.csv")


def validate_order_history_schema(path: Path) -> None:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        fieldnames = set(reader.fieldnames or [])
    missing = [field for field in AMAZON_ORDER_HISTORY_REQUIRED_COLUMNS if field not in fieldnames]
    if missing:
        raise UserFacingError(f"Unsupported Amazon order history CSV schema in {path}. Missing columns: {', '.join(missing)}")


def safe_extract_zip(archive: zipfile.ZipFile, destination: Path) -> None:
    destination = destination.resolve()
    for member in archive.infolist():
        member_path = destination / member.filename
        resolved_member_path = member_path.resolve()
        if destination != resolved_member_path and destination not in resolved_member_path.parents:
            raise UserFacingError(f"Unsafe path in Amazon ZIP export: {member.filename}")
    archive.extractall(destination)


def book_candidate_from_row(row: dict[str, str]) -> dict[str, str] | None:
    asin = normalize_isbn(row.get("ASIN", ""))
    kind = classify_asin(asin)
    if kind == "isbn10":
        isbn10 = asin
        isbn13 = isbn10_to_isbn13(asin)
    elif kind == "isbn13":
        isbn10 = ""
        isbn13 = asin
    else:
        return None

    return {
        "asin": asin,
        "isbn10": isbn10,
        "isbn13": isbn13,
        "order_date": row.get("Order Date", ""),
        "order_id": row.get("Order ID", ""),
        "product_name": row.get("Product Name", ""),
        "product_condition": row.get("Product Condition", ""),
        "quantity": row.get("Original Quantity", ""),
        "unit_price": row.get("Unit Price", ""),
        "currency": row.get("Currency", ""),
        "website": row.get("Website", ""),
    }


def extract_candidates(input_path: Path, output_path: Path) -> int:
    candidates = extract_candidate_rows(input_path)
    write_table_outputs(output_path, BOOK_FIELDNAMES, candidates, "Book Candidates")
    return len(candidates)


def extract_candidate_rows(input_path: Path) -> list[dict[str, str]]:
    candidates, _row_count = extract_candidate_rows_with_count(input_path)
    return candidates


def extract_candidate_rows_with_count(input_path: Path) -> tuple[list[dict[str, str]], int]:
    candidates = []
    row_count = 0
    for row in iter_amazon_rows(input_path):
        row_count += 1
        candidate = book_candidate_from_row(row)
        if candidate:
            candidates.append(candidate)
    return candidates, row_count


def summarize(input_path: Path) -> dict[str, int]:
    counts = {
        "rows": 0,
        "amazon_asin": 0,
        "isbn10": 0,
        "isbn13": 0,
        "unknown_non_b": 0,
        "blank": 0,
    }
    for row in iter_amazon_rows(input_path):
        counts["rows"] += 1
        counts[classify_asin(row.get("ASIN", ""))] += 1
    return counts


def load_cache(cache_path: Path) -> dict[str, dict]:
    if not cache_path.exists():
        return {}
    with cache_path.open(encoding="utf-8") as handle:
        return json.load(handle)


def save_cache(cache_path: Path, cache: dict[str, dict]) -> None:
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = cache_path.with_suffix(cache_path.suffix + ".tmp")
    with tmp_path.open("w", encoding="utf-8") as handle:
        json.dump(cache, handle, indent=2, sort_keys=True)
    tmp_path.replace(cache_path)


def openlibrary_lookup(isbn: str) -> dict:
    return openlibrary_lookup_many([isbn]).get(isbn, {})


def openlibrary_lookup_many(isbns: list[str]) -> dict[str, dict]:
    if not isbns:
        return {}
    params = urllib.parse.urlencode(
        {
            "bibkeys": ",".join(f"ISBN:{isbn}" for isbn in isbns),
            "jscmd": "data",
            "format": "json",
        }
    )
    url = f"https://openlibrary.org/api/books?{params}"
    request = urllib.request.Request(url, headers={"User-Agent": "amazon-library-lcc/0.1"})
    context = ssl.create_default_context(cafile=ca_bundle_path())
    with urllib.request.urlopen(request, timeout=30, context=context) as response:
        data = json.load(response)
    return {isbn: data.get(f"ISBN:{isbn}", {}) for isbn in isbns}


def openlibrary_search_title(title: str, limit: int = 5) -> dict:
    params = urllib.parse.urlencode(
        {
            "title": title,
            "limit": str(limit),
            "fields": ",".join(
                [
                    "key",
                    "title",
                    "author_name",
                    "first_publish_year",
                    "isbn",
                    "lcc",
                    "ddc",
                    "lccn",
                    "oclc",
                    "subject",
                ]
            ),
        }
    )
    url = f"https://openlibrary.org/search.json?{params}"
    request = urllib.request.Request(url, headers={"User-Agent": "amazon-library-lcc/0.1"})
    context = ssl.create_default_context(cafile=ca_bundle_path())
    with urllib.request.urlopen(request, timeout=30, context=context) as response:
        return json.load(response)


def ca_bundle_path() -> str | None:
    for candidate in (
        "/etc/ssl/cert.pem",
        "/etc/ssl/certs/ca-certificates.crt",
        "/opt/homebrew/etc/ca-certificates/cert.pem",
        "/usr/local/etc/openssl@3/cert.pem",
    ):
        if Path(candidate).exists():
            return candidate
    return None


def names(items: list[dict], limit: int | None = None) -> str:
    values = [item.get("name", "") for item in items if item.get("name")]
    if limit is not None:
        values = values[:limit]
    return "; ".join(values)


def values(mapping: dict, key: str) -> str:
    raw = mapping.get(key, [])
    if isinstance(raw, list):
        return "; ".join(str(value) for value in raw)
    return str(raw) if raw else ""


def enrich_row(row: dict[str, str], payload: dict) -> dict[str, str]:
    identifiers = payload.get("identifiers", {}) if payload else {}
    classifications = payload.get("classifications", {}) if payload else {}
    subjects = payload.get("subjects", []) if payload else []
    enriched = dict(row)
    enriched.update(
        {
            "openlibrary_status": "matched" if payload else "not_found",
            "openlibrary_url": payload.get("url", "") if payload else "",
            "title": payload.get("title", "") if payload else "",
            "authors": names(payload.get("authors", [])) if payload else "",
            "publishers": names(payload.get("publishers", [])) if payload else "",
            "publish_date": payload.get("publish_date", "") if payload else "",
            "lcc": values(classifications, "lc_classifications"),
            "dewey": values(classifications, "dewey_decimal_class"),
            "lccn": values(identifiers, "lccn"),
            "oclc": values(identifiers, "oclc"),
            "subjects": names(subjects, limit=12),
        }
    )
    return enriched


def enrich_row_from_search_doc(row: dict[str, str], doc: dict) -> dict[str, str]:
    enriched = dict(row)
    enriched.update(
        {
            "openlibrary_status": "matched",
            "openlibrary_url": f"https://openlibrary.org{doc.get('key', '')}" if doc.get("key") else "",
            "title": doc.get("title", ""),
            "authors": "; ".join(doc.get("author_name", [])[:8]),
            "publishers": row.get("publishers", ""),
            "publish_date": str(doc.get("first_publish_year", "")),
            "lcc": join_doc_values(doc, "lcc"),
            "dewey": join_doc_values(doc, "ddc"),
            "lccn": join_doc_values(doc, "lccn"),
            "oclc": join_doc_values(doc, "oclc"),
            "subjects": join_doc_values(doc, "subject", limit=12),
        }
    )
    return enriched


def join_doc_values(doc: dict, key: str, limit: int = 8) -> str:
    raw = doc.get(key, [])
    if not isinstance(raw, list):
        raw = [raw]
    return "; ".join(str(value) for value in raw[:limit] if value)


def title_query(row: dict[str, str]) -> str:
    title = row.get("product_name") or row.get("title") or ""
    return re.sub(r"\s*\([^)]*\)\s*$", "", title).strip()


def text_similarity(left: str, right: str) -> float:
    left_tokens = set(re.findall(r"[a-z0-9]+", left.lower()))
    right_tokens = set(re.findall(r"[a-z0-9]+", right.lower()))
    if not left_tokens or not right_tokens:
        return 0.0
    return len(left_tokens & right_tokens) / len(left_tokens | right_tokens)


def best_title_match(query: str, docs: list[dict]) -> tuple[dict | None, float]:
    scored = [(doc, text_similarity(query, doc.get("title", ""))) for doc in docs]
    scored.sort(key=lambda item: item[1], reverse=True)
    return scored[0] if scored else (None, 0.0)


def resolve_row(row: dict[str, str], isbn_cache: dict[str, dict], search_cache: dict[str, dict], delay: float) -> dict[str, str]:
    resolved = {field: row.get(field, "") for field in RESOLVED_FIELDNAMES}
    resolved.update(
        {
            "resolution_source": "already_matched" if row.get("openlibrary_status") == "matched" else "manual_review",
            "resolution_confidence": "high" if row.get("openlibrary_status") == "matched" else "none",
            "resolution_notes": "",
            "resolved_query": "",
        }
    )
    if row.get("openlibrary_status") == "matched":
        return resolved

    isbn10 = row.get("isbn10", "")
    if isbn10:
        if isbn10 not in isbn_cache:
            isbn_cache[isbn10] = openlibrary_lookup(isbn10)
            time.sleep(delay)
        if isbn_cache[isbn10]:
            enriched = enrich_row(row, isbn_cache[isbn10])
            resolved.update(enriched)
            resolved.update(
                {
                    "resolution_source": "openlibrary_isbn10_exact",
                    "resolution_confidence": "high",
                    "resolution_notes": "Resolved by retrying the original ISBN-10.",
                    "resolved_query": isbn10,
                }
            )
            return resolved

    query = title_query(row)
    if query:
        if query not in search_cache:
            print(f"Open Library title fallback: {query}", file=sys.stderr)
            search_cache[query] = openlibrary_search_title(query)
            time.sleep(delay)
        docs = search_cache[query].get("docs", [])
        match, score = best_title_match(query, docs)
        if match and score >= 0.65:
            enriched = enrich_row_from_search_doc(row, match)
            resolved.update(enriched)
            resolved.update(
                {
                    "resolution_source": "openlibrary_title_search",
                    "resolution_confidence": "medium" if score < 0.9 else "high",
                    "resolution_notes": f"Best title-search match, similarity {score:.2f}.",
                    "resolved_query": query,
                }
            )
            return resolved

    resolved.update(
        {
            "resolution_notes": "No ISBN-10 or title-search match met the confidence threshold.",
            "resolved_query": query,
        }
    )
    return resolved


def enrich_openlibrary(input_path: Path, output_path: Path, cache_path: Path, delay: float, limit: int | None) -> int:
    cache = load_cache(cache_path)
    rows = []
    with input_path.open(newline="", encoding="utf-8-sig") as source:
        reader = csv.DictReader(source)
        for row in reader:
            if limit is not None and len(rows) >= limit:
                break
            isbn = row.get("isbn13") or row.get("isbn10") or row.get("asin")
            if isbn not in cache:
                cache[isbn] = openlibrary_lookup(isbn)
                save_cache(cache_path, cache)
                time.sleep(delay)
            rows.append(enrich_row(row, cache[isbn]))
    save_cache(cache_path, cache)
    write_table_outputs(output_path, ENRICHED_FIELDNAMES, rows, "Open Library Enrichment")
    return len(rows)


def resolve_missing(input_path: Path, output_path: Path, isbn_cache_path: Path, search_cache_path: Path, delay: float) -> dict[str, int]:
    isbn_cache = load_cache(isbn_cache_path)
    search_cache = load_cache(search_cache_path)
    rows = []
    counts = {
        "rows": 0,
        "already_matched": 0,
        "openlibrary_isbn10_exact": 0,
        "openlibrary_title_search": 0,
        "manual_review": 0,
    }
    with input_path.open(newline="", encoding="utf-8-sig") as source:
        for row in csv.DictReader(source):
            resolved = resolve_row(row, isbn_cache, search_cache, delay)
            rows.append(resolved)
            counts["rows"] += 1
            source_name = resolved.get("resolution_source", "manual_review")
            counts[source_name] = counts.get(source_name, 0) + 1
            save_cache(isbn_cache_path, isbn_cache)
            save_cache(search_cache_path, search_cache)

    write_table_outputs(output_path, RESOLVED_FIELDNAMES, rows, "Resolved Missing")
    save_cache(isbn_cache_path, isbn_cache)
    save_cache(search_cache_path, search_cache)
    return counts


def update_library(
    amazon_input: Path,
    output_dir: Path,
    isbn_cache_path: Path,
    search_cache_path: Path,
    delay: float,
    paths: LibraryPaths | None = None,
) -> dict[str, int | str]:
    if paths is None:
        paths = LibraryPaths(output_dir=output_dir)
    paths.ensure_directories()
    output_dir.mkdir(parents=True, exist_ok=True)
    with resolve_amazon_order_history_input(amazon_input) as order_history_input:
        purchases, amazon_row_count = extract_candidate_rows_with_count(order_history_input)
        manifest_source_filename = order_history_input.name
        manifest_source_hash = file_sha256(order_history_input)
    write_table_outputs(output_dir / "book_purchases.csv", BOOK_FIELDNAMES, purchases, "Book Purchases")

    isbn_cache = load_cache(isbn_cache_path)
    search_cache = load_cache(search_cache_path)
    metadata_rows = build_book_metadata_rows(
        purchases,
        isbn_cache,
        search_cache,
        delay,
        isbn_cache_path=isbn_cache_path,
        search_cache_path=search_cache_path,
    )
    catalog_repository = CatalogRepository(paths.catalog_items_path)
    acquisition_repository = AcquisitionRepository(paths.acquisitions_path)
    research_assessment_repository = ResearchAssessmentRepository(paths.research_priority_assessments_path)
    collector_review_repository = CollectorReviewRepository(paths.collector_reviews_path)
    catalog_items = catalog_repository.load()
    existing_acquisitions = acquisition_repository.load()
    existing_catalog_item_ids = {row.get("catalog_item_id", "") for row in catalog_items if row.get("catalog_item_id")}
    existing_assessments = research_assessment_repository.load()
    collector_review_repository.ensure_exists()
    collector_reviews = collector_review_repository.load()
    metadata_rows, catalog_items = reconcile_catalog_items(metadata_rows, catalog_items)
    catalog_repository.save(catalog_items)
    catalog_rows = build_library_catalog_rows(purchases, metadata_rows)
    acquisitions = build_acquisitions(purchases, metadata_rows)
    acquisition_repository.save(acquisitions)
    existing_acquisition_ids = {row.get("acquisition_id", "") for row in existing_acquisitions if row.get("acquisition_id")}
    current_acquisition_ids = {row.get("acquisition_id", "") for row in acquisitions if row.get("acquisition_id")}
    new_acquisition_count = len(current_acquisition_ids - existing_acquisition_ids)
    assessment_metadata_rows = assessment_metadata_for_catalog_items(catalog_items, metadata_rows)
    research_signal_config = load_research_signal_config(paths.config_dir)
    research_assessments = reconcile_research_assessments(
        existing_assessments,
        assessment_metadata_rows,
        acquisitions=acquisitions,
        config=research_signal_config,
    )
    research_assessment_repository.save(research_assessments)
    research_candidates = build_research_candidate_rows(
        catalog_items,
        metadata_rows,
        acquisitions,
        research_assessments,
        collector_reviews,
    )
    final_catalog_item_ids = {row.get("catalog_item_id", "") for row in catalog_items if row.get("catalog_item_id")}
    assessed_catalog_item_ids = {
        row.get("catalog_item_id", "")
        for row in existing_assessments
        if row.get("catalog_item_id")
    }
    current_metadata_catalog_item_ids = {
        row.get("catalog_item_id", "")
        for row in metadata_rows
        if row.get("catalog_item_id")
    }
    final_assessed_catalog_item_ids = {
        row.get("catalog_item_id", "")
        for row in research_assessments
        if row.get("catalog_item_id")
    }
    created_assessment_catalog_item_ids = final_assessed_catalog_item_ids - assessed_catalog_item_ids
    manifest_row = build_import_manifest_row(
        filename=manifest_source_filename,
        file_hash=manifest_source_hash,
        amazon_row_count=amazon_row_count,
        purchases=purchases,
        metadata_rows=metadata_rows,
        existing_catalog_item_ids=existing_catalog_item_ids,
        catalog_items=catalog_items,
        acquisitions=acquisitions,
    )
    run_summary = {
        "imported_at": manifest_row.get("imported_at", ""),
        "amazon_row_count": amazon_row_count,
        "purchase_rows": len(purchases),
        "catalog_new": len(current_metadata_catalog_item_ids - existing_catalog_item_ids),
        "acquisition_new": new_acquisition_count,
        "research_durable_total": len(final_assessed_catalog_item_ids),
        "research_reused": len(current_metadata_catalog_item_ids & assessed_catalog_item_ids),
        "research_created": len(current_metadata_catalog_item_ids & created_assessment_catalog_item_ids),
    }

    write_table_outputs(output_dir / "book_metadata.csv", BOOK_METADATA_FIELDNAMES, metadata_rows, "Book Metadata")
    write_table_outputs(output_dir / "library_catalog.csv", LIBRARY_CATALOG_FIELDNAMES, catalog_rows, "Library Catalog")
    write_table_outputs(
        output_dir / "research_candidates.csv",
        RESEARCH_CANDIDATE_FIELDNAMES,
        research_candidates,
        "Research Candidates",
    )
    write_collector_workbook(
        output_dir / "collector_workbook.xlsx",
        catalog_items=catalog_items,
        acquisitions=acquisitions,
        research_candidates=research_candidates,
        collector_reviews=collector_reviews,
        metadata_rows=metadata_rows,
        latest_import=str(amazon_input),
        run_summary=run_summary,
    )
    save_cache(isbn_cache_path, isbn_cache)
    save_cache(search_cache_path, search_cache)
    manifest_repository = ImportManifestRepository(paths.import_manifest_path)
    manifest_repository.append(manifest_row)

    return {
        "amazon_export": str(amazon_input),
        "amazon_row_count": amazon_row_count,
        "purchase_rows": len(purchases),
        "unique_books": len(metadata_rows),
        "metadata_matched": sum(1 for row in metadata_rows if row.get("openlibrary_status") == "matched"),
        "metadata_with_lcc": sum(1 for row in metadata_rows if row.get("lcc")),
        "metadata_manual_review": sum(1 for row in metadata_rows if row.get("resolution_source") == "manual_review"),
        "catalog_durable_total": len(final_catalog_item_ids),
        "catalog_current_export": len(current_metadata_catalog_item_ids),
        "catalog_existing": len(current_metadata_catalog_item_ids & existing_catalog_item_ids),
        "catalog_new": len(current_metadata_catalog_item_ids - existing_catalog_item_ids),
        "acquisition_rows": len(acquisitions),
        "acquisition_new": new_acquisition_count,
        "research_durable_total": len(final_assessed_catalog_item_ids),
        "research_reused": len(current_metadata_catalog_item_ids & assessed_catalog_item_ids),
        "research_created": len(current_metadata_catalog_item_ids & created_assessment_catalog_item_ids),
        "research_candidates": len(research_candidates),
        "manifest_entries": len(manifest_repository.load()),
    }


def format_catalog_item_id(sequence_number: int) -> str:
    if sequence_number < 1:
        raise ValueError("Catalog item sequence number must be positive.")
    return f"BK{sequence_number:06d}"


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")


def generate_market_validation_sample(
    output_dir: Path,
    data_dir: Path = Path("data"),
    sample_size_per_band: int = 20,
    seed: int = 42,
    sampled_at: str | None = None,
) -> int:
    if sample_size_per_band < 1:
        raise UserFacingError("sample-size-per-band must be at least 1")
    catalog_rows = read_csv_rows(output_dir / "library_catalog.csv")
    catalog_item_rows = read_optional_csv_rows(data_dir / "catalog_items.csv")
    acquisition_rows = read_optional_csv_rows(data_dir / "acquisitions.csv")
    generated_assessments_path = output_dir / "research_assessments.csv"
    durable_assessments_path = data_dir / "research_priority_assessments.csv"
    assessment_rows = read_csv_rows(
        generated_assessments_path
        if generated_assessments_path.exists()
        else durable_assessments_path
    )
    sample_timestamp = sampled_at or utc_timestamp()
    sample_rows = build_market_validation_sample_rows(
        catalog_rows,
        assessment_rows,
        catalog_item_rows=catalog_item_rows,
        acquisition_rows=acquisition_rows,
        sample_size_per_band=sample_size_per_band,
        seed=seed,
        sampled_at=sample_timestamp,
    )
    metadata_rows = build_market_validation_sample_metadata_rows(
        sample_rows,
        assessment_rows,
        sample_size_per_band=sample_size_per_band,
        seed=seed,
        sampled_at=sample_timestamp,
    )
    write_table_outputs(
        output_dir / "market_validation_sample.csv",
        MARKET_VALIDATION_SAMPLE_FIELDNAMES,
        sample_rows,
        "Market Validation Sample",
    )
    write_table_outputs(
        output_dir / "market_validation_sample_metadata.csv",
        MARKET_VALIDATION_SAMPLE_METADATA_FIELDNAMES,
        metadata_rows,
        "Market Validation Metadata",
    )
    return len(sample_rows)


def collect_abebooks_observations(
    output_dir: Path,
    limit: int = 30,
    delay: float = 1.0,
    max_results_per_book: int = 3,
    fetch_html=fetch_url,
    observation_date: str | None = None,
    sleep=time.sleep,
) -> int:
    if limit < 1:
        raise UserFacingError("limit must be at least 1")
    if delay < 0:
        raise UserFacingError("delay must be zero or greater")
    if max_results_per_book < 1:
        raise UserFacingError("max-results-per-book must be at least 1")
    sample_rows = read_csv_rows(output_dir / "market_validation_sample.csv")
    observation_rows = collect_abebooks_observation_rows(
        sample_rows,
        fetch_html=fetch_html,
        observation_date=observation_date or utc_timestamp(),
        limit=limit,
        max_results_per_book=max_results_per_book,
        delay_seconds=delay,
        sleep=sleep,
    )
    write_table_outputs(
        output_dir / "market_observations.csv",
        MARKET_OBSERVATION_FIELDNAMES,
        observation_rows,
        "Market Observations",
    )
    return len(observation_rows)


def report_market_observation_coverage(output_dir: Path) -> int:
    sample_rows = read_csv_rows(output_dir / "market_validation_sample.csv")
    observation_rows = read_csv_rows(output_dir / "market_observations.csv")
    report_rows = build_market_observation_coverage_rows(sample_rows, observation_rows)
    write_table_outputs(
        output_dir / "market_observation_coverage_report.csv",
        MARKET_OBSERVATION_COVERAGE_FIELDNAMES,
        report_rows,
        "Market Observation Coverage",
    )
    return len(report_rows)


def analyze_market_validation(output_dir: Path) -> int:
    sample_rows = read_csv_rows(output_dir / "market_validation_sample.csv")
    observation_rows = read_csv_rows(output_dir / "market_observations.csv")
    metadata_rows = read_csv_rows(output_dir / "market_validation_sample_metadata.csv")
    analysis_rows = build_market_validation_analysis_rows(sample_rows, observation_rows, metadata_rows)
    write_table_outputs(
        output_dir / "market_validation_analysis.csv",
        MARKET_VALIDATION_ANALYSIS_FIELDNAMES,
        analysis_rows,
        "Market Validation Analysis",
    )
    return len(analysis_rows)


def review_research_signal_effectiveness(output_dir: Path) -> int:
    review_rows = build_research_signal_effectiveness_rows(
        read_csv_rows(output_dir / "market_validation_sample.csv"),
        read_csv_rows(output_dir / "market_observations.csv"),
        read_csv_rows(output_dir / "market_validation_sample_metadata.csv"),
        read_csv_rows(output_dir / "market_observation_coverage_report.csv"),
        read_csv_rows(output_dir / "market_validation_analysis.csv"),
    )
    write_table_outputs(
        output_dir / "research_signal_effectiveness_review.csv",
        RESEARCH_SIGNAL_EFFECTIVENESS_FIELDNAMES,
        review_rows,
        "Research Signal Effectiveness",
    )
    return len(review_rows)


def build_import_manifest_row(
    filename: str,
    file_hash: str,
    amazon_row_count: int,
    purchases: list[dict[str, str]],
    metadata_rows: list[dict[str, str]],
    existing_catalog_item_ids: set[str],
    catalog_items: list[dict[str, str]],
    acquisitions: list[dict[str, str]],
) -> dict[str, str]:
    imported_at = utc_timestamp()
    catalog_item_ids = {row.get("catalog_item_id", "") for row in catalog_items if row.get("catalog_item_id")}
    new_catalog_item_ids = catalog_item_ids - existing_catalog_item_ids
    catalog_matches = sum(1 for row in metadata_rows if row.get("catalog_item_id") in existing_catalog_item_ids)
    return {
        # import_id is unique per run, not deterministic for the same source file.
        # Duplicate source detection should use file_hash, not import_id.
        "import_id": stable_hash_id("IMP", [file_hash, imported_at]),
        "filename": filename,
        "file_hash": file_hash,
        "imported_at": imported_at,
        "pipeline_version": PIPELINE_VERSION,
        "schema_version": SCHEMA_VERSION,
        "amazon_row_count": str(amazon_row_count),
        "book_candidates": str(len(purchases)),
        "catalog_matches": str(catalog_matches),
        "new_catalog_items": str(len(new_catalog_item_ids)),
        "acquisition_rows": str(len(acquisitions)),
        "status": "success",
        "notes": "",
    }


def load_research_assessments(path: Path) -> list[dict[str, str]]:
    return ResearchAssessmentRepository(path).load()


def write_research_assessments(path: Path, rows: list[dict[str, str]]) -> None:
    ResearchAssessmentRepository(path).save(rows)


def load_collector_reviews(path: Path) -> list[dict[str, str]]:
    return CollectorReviewRepository(path).load()


def write_collector_reviews(path: Path, rows: list[dict[str, str]]) -> None:
    CollectorReviewRepository(path).save(rows)


def reconcile_research_assessments(
    existing_assessments: list[dict[str, str]],
    metadata_rows: list[dict[str, str]],
    acquisitions: list[dict[str, str]] | None = None,
    config: ResearchSignalConfig | None = None,
) -> list[dict[str, str]]:
    config = config or default_research_signal_config()
    assessments_by_id = {
        row.get("catalog_item_id", ""): dict(row)
        for row in existing_assessments
        if row.get("catalog_item_id")
    }
    acquisitions_by_catalog_item_id = group_acquisitions_by_catalog_item_id(acquisitions or [])
    config_hash = research_config_hash(config)
    for metadata in metadata_rows:
        catalog_item_id = metadata.get("catalog_item_id", "")
        if not catalog_item_id:
            continue
        existing = assessments_by_id.get(catalog_item_id)
        acquisition_rows = acquisitions_by_catalog_item_id.get(catalog_item_id, [])
        if existing and is_current_research_assessment(existing, metadata, acquisition_rows, config_hash):
            continue
        assessments_by_id[catalog_item_id] = build_research_assessment(
            metadata,
            acquisitions=acquisition_rows,
            config=config,
        )
    return sorted(assessments_by_id.values(), key=lambda row: row.get("catalog_item_id", ""))


def is_current_research_assessment(
    assessment: dict[str, str],
    metadata: dict[str, str],
    acquisitions: list[dict[str, str]],
    config_hash: str,
) -> bool:
    return (
        assessment.get("research_model_version") == RESEARCH_MODEL_VERSION
        and assessment.get("research_config_hash") == config_hash
        and assessment.get("acquisition_snapshot_hash") == acquisition_snapshot_hash(acquisitions)
        and assessment.get("metadata_snapshot_hash") == metadata_snapshot_hash(metadata)
    )


def group_acquisitions_by_catalog_item_id(acquisitions: list[dict[str, str]]) -> dict[str, list[dict[str, str]]]:
    grouped: dict[str, list[dict[str, str]]] = {}
    for acquisition in acquisitions:
        catalog_item_id = acquisition.get("catalog_item_id", "")
        if catalog_item_id:
            grouped.setdefault(catalog_item_id, []).append(acquisition)
    return grouped


def assessment_metadata_for_catalog_items(
    catalog_items: list[dict[str, str]], metadata_rows: list[dict[str, str]]
) -> list[dict[str, str]]:
    metadata_by_id = {}
    for item in catalog_items:
        catalog_item_id = item.get("catalog_item_id", "")
        if catalog_item_id:
            metadata_by_id[catalog_item_id] = catalog_item_assessment_metadata(item)
    for metadata in metadata_rows:
        catalog_item_id = metadata.get("catalog_item_id", "")
        if catalog_item_id:
            metadata_by_id[catalog_item_id] = metadata
    return sorted(metadata_by_id.values(), key=lambda row: row.get("catalog_item_id", ""))


def catalog_item_assessment_metadata(item: dict[str, str]) -> dict[str, str]:
    return {
        "catalog_item_id": item.get("catalog_item_id", ""),
        "isbn13": item.get("isbn13", ""),
        "isbn10": item.get("isbn10", ""),
        "title": item.get("title", ""),
        "authors": item.get("author", ""),
        "publishers": item.get("publisher", ""),
        "publish_date": item.get("publication_year", ""),
    }


def load_catalog_items(path: Path) -> list[dict[str, str]]:
    return CatalogRepository(path).load()


def write_catalog_items(path: Path, rows: list[dict[str, str]]) -> None:
    CatalogRepository(path).save(rows)


def load_acquisitions(path: Path) -> list[dict[str, str]]:
    return AcquisitionRepository(path).load()


def write_acquisitions(path: Path, rows: list[dict[str, str]]) -> None:
    AcquisitionRepository(path).save(rows)


def build_acquisitions(purchases: list[dict[str, str]], metadata_rows: list[dict[str, str]]) -> list[dict[str, str]]:
    metadata_index = metadata_lookup_for_acquisitions(metadata_rows)
    acquisitions = []
    for purchase in purchases:
        metadata = find_metadata_for_purchase(purchase, metadata_index)
        source = "amazon"
        source_order_id = purchase.get("order_id", "")
        source_asin = purchase.get("asin", "")
        order_date = purchase.get("order_date", "")
        source_title = purchase.get("product_name", "")
        item_price = purchase.get("unit_price", "")
        quantity = purchase.get("quantity", "")
        source_item_id = source_item_identifier(
            source,
            source_order_id,
            source_asin,
            order_date,
            source_title,
            item_price,
        )
        acquisitions.append(
            {
                "acquisition_id": acquisition_id(
                    source,
                    source_order_id,
                    source_asin,
                    order_date,
                    source_title,
                    item_price,
                    quantity,
                ),
                "catalog_item_id": metadata.get("catalog_item_id", ""),
                "source": source,
                "source_order_id": source_order_id,
                "source_item_id": source_item_id,
                "order_date": order_date,
                "quantity": quantity,
                "item_price": item_price,
                "item_subtotal": item_subtotal(item_price, quantity),
                "currency": purchase.get("currency", ""),
                "source_title": source_title,
                "source_asin": source_asin,
                "isbn13": purchase.get("isbn13", ""),
                "isbn10": purchase.get("isbn10", ""),
            }
        )
    return acquisitions


def metadata_lookup_for_acquisitions(metadata_rows: list[dict[str, str]]) -> dict[str, dict[str, dict[str, str]]]:
    index: dict[str, dict[str, dict[str, str]]] = {
        "isbn13": {},
        "isbn10": {},
        "title": {},
    }
    for row in metadata_rows:
        if row.get("isbn13"):
            index["isbn13"].setdefault(row["isbn13"], row)
        if row.get("isbn10"):
            index["isbn10"].setdefault(row["isbn10"], row)
        title_key = normalized_acquisition_title_key(row)
        if title_key:
            index["title"].setdefault(title_key, row)
    return index


def find_metadata_for_purchase(
    purchase: dict[str, str], metadata_index: dict[str, dict[str, dict[str, str]]]
) -> dict[str, str]:
    isbn13 = purchase.get("isbn13", "")
    if isbn13 and isbn13 in metadata_index["isbn13"]:
        return metadata_index["isbn13"][isbn13]
    isbn10 = purchase.get("isbn10", "")
    if isbn10 and isbn10 in metadata_index["isbn10"]:
        return metadata_index["isbn10"][isbn10]
    if has_isbn_evidence(purchase):
        return {}
    title_key = normalized_acquisition_title_key(purchase)
    if title_key and title_key in metadata_index["title"]:
        return metadata_index["title"][title_key]
    return {}


def normalized_acquisition_title_key(row: dict[str, str]) -> str:
    return normalize_match_text(row.get("source_title") or row.get("product_name") or row.get("title") or row.get("representative_product_name", ""))


def source_item_identifier(
    source: str,
    source_order_id: str,
    source_asin: str,
    order_date: str,
    source_title: str,
    item_price: str,
) -> str:
    return stable_hash_id("SRC", [source, source_order_id, source_asin, order_date, source_title, item_price])


def acquisition_id(
    source: str,
    source_order_id: str,
    source_asin: str,
    order_date: str,
    source_title: str,
    item_price: str,
    quantity: str,
) -> str:
    return stable_hash_id("AMZ", [source, source_order_id, source_asin, order_date, source_title, item_price, quantity])


def stable_hash_id(prefix: str, values: list[str]) -> str:
    payload = "\x1f".join(value or "" for value in values)
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16].upper()
    return f"{prefix}-{digest}"


def item_subtotal(item_price: str, quantity: str) -> str:
    try:
        price = float(item_price)
        count = int(quantity)
    except (TypeError, ValueError):
        return ""
    return f"{price * count:.2f}"


def reconcile_catalog_items(
    metadata_rows: list[dict[str, str]], existing_items: list[dict[str, str]]
) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    matcher = CatalogMatcher(existing_items)
    reconciled_metadata = []
    current_items_by_id = {row.get("catalog_item_id", ""): dict(row) for row in existing_items if row.get("catalog_item_id")}

    for metadata in metadata_rows:
        match, confidence = matcher.match(metadata)
        if match:
            catalog_item_id = match["catalog_item_id"]
        else:
            catalog_item_id = matcher.next_catalog_item_id()
            confidence = initial_match_confidence(metadata)

        metadata_with_id = dict(metadata)
        metadata_with_id["catalog_item_id"] = catalog_item_id
        reconciled_metadata.append(metadata_with_id)

        catalog_item = merge_catalog_item(match, metadata_with_id, confidence)
        current_items_by_id[catalog_item_id] = catalog_item
        matcher.add(catalog_item)

    catalog_items = sorted(current_items_by_id.values(), key=lambda row: row.get("catalog_item_id", ""))
    return reconciled_metadata, catalog_items


class CatalogMatcher:
    def __init__(self, catalog_items: list[dict[str, str]]):
        self.catalog_items_by_id = {row.get("catalog_item_id", ""): row for row in catalog_items if row.get("catalog_item_id")}
        self.by_isbn13: dict[str, dict[str, str]] = {}
        self.by_isbn10: dict[str, dict[str, str]] = {}
        self.by_source_fingerprint: dict[str, dict[str, str]] = {}
        self.by_title_author: dict[str, dict[str, str]] = {}
        for item in catalog_items:
            self.add(item)

    def add(self, item: dict[str, str]) -> None:
        catalog_item_id = item.get("catalog_item_id", "")
        if catalog_item_id:
            self.catalog_items_by_id[catalog_item_id] = item
        if item.get("isbn13"):
            self.by_isbn13.setdefault(item["isbn13"], item)
        if item.get("isbn10"):
            self.by_isbn10.setdefault(item["isbn10"], item)
        if item.get("source_fingerprint"):
            self.by_source_fingerprint.setdefault(item["source_fingerprint"], item)
        title_author_key = normalized_title_author_key(item)
        if title_author_key:
            self.by_title_author.setdefault(title_author_key, item)

    def match(self, row: dict[str, str]) -> tuple[dict[str, str] | None, str]:
        if row.get("isbn13"):
            if row["isbn13"] in self.by_isbn13:
                return self.by_isbn13[row["isbn13"]], "high"
            return None, "needs_review"
        if row.get("isbn10"):
            if row["isbn10"] in self.by_isbn10:
                return self.by_isbn10[row["isbn10"]], "high"
            return None, "needs_review"
        # TODO: Populate source_fingerprint from source evidence once the
        # durable acquisitions/source-item layer exists.
        if row.get("source_fingerprint") and row["source_fingerprint"] in self.by_source_fingerprint:
            return self.by_source_fingerprint[row["source_fingerprint"]], "high"
        title_author_key = normalized_title_author_key(row)
        if title_author_key and title_author_key in self.by_title_author:
            return self.by_title_author[title_author_key], "medium"
        return None, "needs_review"

    def next_catalog_item_id(self) -> str:
        max_sequence = 0
        for catalog_item_id in self.catalog_items_by_id:
            match = re.fullmatch(r"BK(\d{6})", catalog_item_id)
            if match:
                max_sequence = max(max_sequence, int(match.group(1)))
        return format_catalog_item_id(max_sequence + 1)


def normalized_title_author_key(row: dict[str, str]) -> str:
    title = normalize_match_text(row.get("title") or row.get("representative_product_name", ""))
    author = normalize_match_text(row.get("author") or row.get("authors", ""))
    if not title or not author:
        return ""
    return f"{title}|{author}"


def has_isbn_evidence(row: dict[str, str]) -> bool:
    return bool(row.get("isbn13") or row.get("isbn10"))


def normalize_match_text(value: str) -> str:
    return " ".join(re.findall(r"[a-z0-9]+", (value or "").lower()))


def initial_match_confidence(metadata: dict[str, str]) -> str:
    if metadata.get("isbn13") or metadata.get("isbn10"):
        return "high"
    if normalized_title_author_key(metadata):
        return "medium"
    return "needs_review"


def catalog_item_from_metadata(metadata: dict[str, str], match_confidence: str) -> dict[str, str]:
    return {
        "catalog_item_id": metadata.get("catalog_item_id", ""),
        "isbn13": metadata.get("isbn13", ""),
        "isbn10": metadata.get("isbn10", ""),
        "title": metadata.get("title") or metadata.get("representative_product_name", ""),
        "author": metadata.get("authors", ""),
        "publisher": metadata.get("publishers", ""),
        "publication_year": publication_year(metadata.get("publish_date", "")),
        "source_fingerprint": metadata.get("source_fingerprint", ""),
        "match_confidence": match_confidence,
    }


def merge_catalog_item(existing: dict[str, str] | None, metadata: dict[str, str], match_confidence: str) -> dict[str, str]:
    incoming = catalog_item_from_metadata(metadata, match_confidence)
    if not existing:
        return incoming
    merged = {field: existing.get(field, "") for field in CATALOG_ITEMS_FIELDNAMES}
    for field, value in incoming.items():
        if field == "catalog_item_id":
            merged[field] = value
        elif not merged.get(field) and value:
            merged[field] = value
    return merged


def publication_year(value: str) -> str:
    match = re.search(r"\b(\d{4})\b", value or "")
    return match.group(1) if match else ""


def build_book_metadata_rows(
    purchases: list[dict[str, str]],
    isbn_cache: dict[str, dict],
    search_cache: dict[str, dict],
    delay: float,
    isbn_cache_path: Path | None = None,
    search_cache_path: Path | None = None,
) -> list[dict[str, str]]:
    rows = []
    groups = grouped_purchases(purchases)
    fetch_missing_isbn_cache(list(groups), isbn_cache, isbn_cache_path=isbn_cache_path, delay=delay)
    prepared_rows = []
    isbn10_fallbacks = []
    for isbn13, group in groups.items():
        summary = purchase_summary(group)
        enriched = enrich_row(summary, isbn_cache[isbn13])
        prepared_rows.append((summary, enriched))
        if enriched.get("openlibrary_status") != "matched" and summary.get("isbn10"):
            isbn10_fallbacks.append(summary["isbn10"])

    fetch_missing_isbn_cache(
        isbn10_fallbacks,
        isbn_cache,
        isbn_cache_path=isbn_cache_path,
        delay=delay,
        report_cached=False,
    )

    for summary, enriched in prepared_rows:
        search_cache_count = len(search_cache)
        isbn_cache_count = len(isbn_cache)
        resolved = resolve_row(enriched, isbn_cache, search_cache, delay)
        if isbn_cache_path and len(isbn_cache) != isbn_cache_count:
            save_cache(isbn_cache_path, isbn_cache)
        if search_cache_path and len(search_cache) != search_cache_count:
            save_cache(search_cache_path, search_cache)
        rows.append(metadata_row(summary, resolved))
    return sorted(rows, key=lambda row: (row.get("lcc") or "ZZZ", row.get("title") or row.get("representative_product_name", "")))


def fetch_missing_isbn_cache(
    isbns: list[str],
    isbn_cache: dict[str, dict],
    isbn_cache_path: Path | None = None,
    delay: float = 0.25,
    batch_size: int = 50,
    report_cached: bool = True,
) -> None:
    missing = [isbn for isbn in isbns if isbn and isbn not in isbn_cache]
    if not missing:
        if report_cached:
            print("ISBN cache already has all required Open Library lookups.", file=sys.stderr)
        return
    print(f"Fetching {len(missing)} missing Open Library ISBN lookups in batches of {batch_size}.", file=sys.stderr)
    for start in range(0, len(missing), batch_size):
        batch = missing[start : start + batch_size]
        batch_number = start // batch_size + 1
        batch_count = (len(missing) + batch_size - 1) // batch_size
        print(f"Open Library batch {batch_number}/{batch_count}: {len(batch)} ISBNs", file=sys.stderr)
        isbn_cache.update(openlibrary_lookup_many(batch))
        if isbn_cache_path:
            save_cache(isbn_cache_path, isbn_cache)
        time.sleep(delay)


def grouped_purchases(purchases: list[dict[str, str]]) -> dict[str, list[dict[str, str]]]:
    groups: dict[str, list[dict[str, str]]] = {}
    for row in purchases:
        groups.setdefault(row.get("isbn13", ""), []).append(row)
    return {isbn: rows for isbn, rows in groups.items() if isbn}


def purchase_summary(group: list[dict[str, str]]) -> dict[str, str]:
    sorted_group = sorted(group, key=lambda row: row.get("order_date", ""))
    first = sorted_group[0]
    product_names = unique_join(row.get("product_name", "") for row in sorted_group)
    return {
        **first,
        "order_date": first.get("order_date", ""),
        "product_name": first.get("product_name", ""),
        "quantity": str(sum(sum_int(row.get("quantity", "")) for row in sorted_group)),
        "purchase_count": str(len(group)),
        "total_quantity": str(sum(sum_int(row.get("quantity", "")) for row in group)),
        "first_order_date": sorted_group[0].get("order_date", ""),
        "latest_order_date": sorted_group[-1].get("order_date", ""),
        "representative_product_name": first.get("product_name", ""),
        "product_names": product_names,
    }


def metadata_row(summary: dict[str, str], resolved: dict[str, str]) -> dict[str, str]:
    return {
        "isbn13": summary.get("isbn13", ""),
        "isbn10": summary.get("isbn10", ""),
        "asin": summary.get("asin", ""),
        "purchase_count": summary.get("purchase_count", ""),
        "total_quantity": summary.get("total_quantity", ""),
        "first_order_date": summary.get("first_order_date", ""),
        "latest_order_date": summary.get("latest_order_date", ""),
        "representative_product_name": summary.get("representative_product_name", ""),
        "product_names": summary.get("product_names", ""),
        "openlibrary_status": resolved.get("openlibrary_status", ""),
        "openlibrary_url": resolved.get("openlibrary_url", ""),
        "title": resolved.get("title", ""),
        "authors": resolved.get("authors", ""),
        "publishers": resolved.get("publishers", ""),
        "publish_date": resolved.get("publish_date", ""),
        "lcc": resolved.get("lcc", ""),
        "dewey": resolved.get("dewey", ""),
        "lccn": resolved.get("lccn", ""),
        "oclc": resolved.get("oclc", ""),
        "subjects": resolved.get("subjects", ""),
        "resolution_source": resolved.get("resolution_source", ""),
        "resolution_confidence": resolved.get("resolution_confidence", ""),
        "resolution_notes": resolved.get("resolution_notes", ""),
        "resolved_query": resolved.get("resolved_query", ""),
    }


def build_library_catalog_rows(
    purchases: list[dict[str, str]], metadata_rows: list[dict[str, str]]
) -> list[dict[str, str]]:
    metadata_by_isbn = {row.get("isbn13", ""): row for row in metadata_rows}
    catalog = []
    for purchase in sorted(purchases, key=lambda row: row.get("order_date", "")):
        metadata = metadata_by_isbn.get(purchase.get("isbn13", ""), {})
        catalog.append(
            {
                "catalog_item_id": metadata.get("catalog_item_id", ""),
                "lcc": metadata.get("lcc", ""),
                "title": metadata.get("title") or purchase.get("product_name", ""),
                "authors": metadata.get("authors", ""),
                "purchase_date": purchase.get("order_date", ""),
                "isbn13": purchase.get("isbn13", ""),
                "isbn10": purchase.get("isbn10", ""),
                "product_name": purchase.get("product_name", ""),
                "quantity": purchase.get("quantity", ""),
                "unit_price": purchase.get("unit_price", ""),
                "currency": purchase.get("currency", ""),
                "order_id": purchase.get("order_id", ""),
                "openlibrary_url": metadata.get("openlibrary_url", ""),
                "resolution_source": metadata.get("resolution_source", ""),
                "resolution_confidence": metadata.get("resolution_confidence", ""),
                "subjects": metadata.get("subjects", ""),
            }
        )
    return catalog


def sum_int(value: str) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def unique_join(values) -> str:
    seen = []
    for value in values:
        if value and value not in seen:
            seen.append(value)
    return "; ".join(seen)


def pct(part: int, whole: int) -> str:
    if whole == 0:
        return "0.0%"
    return f"{part / whole:.1%}"


def analyze_enrichment(input_path: Path) -> dict[str, str | int]:
    counts = {
        "rows": 0,
        "matched": 0,
        "not_found": 0,
        "with_lcc": 0,
        "with_dewey": 0,
        "with_lccn": 0,
        "with_oclc": 0,
        "with_subjects": 0,
    }
    with input_path.open(newline="", encoding="utf-8-sig") as handle:
        for row in csv.DictReader(handle):
            counts["rows"] += 1
            if row.get("openlibrary_status") == "matched":
                counts["matched"] += 1
            else:
                counts["not_found"] += 1
            if row.get("lcc"):
                counts["with_lcc"] += 1
            if row.get("dewey"):
                counts["with_dewey"] += 1
            if row.get("lccn"):
                counts["with_lccn"] += 1
            if row.get("oclc"):
                counts["with_oclc"] += 1
            if row.get("subjects"):
                counts["with_subjects"] += 1

    rows = counts["rows"]
    return {
        **counts,
        "matched_rate": pct(counts["matched"], rows),
        "lcc_rate": pct(counts["with_lcc"], rows),
        "dewey_rate": pct(counts["with_dewey"], rows),
        "lccn_rate": pct(counts["with_lccn"], rows),
        "oclc_rate": pct(counts["with_oclc"], rows),
        "subjects_rate": pct(counts["with_subjects"], rows),
    }


def discover_amazon_export(amazon_input_dir: Path) -> Path:
    if not amazon_input_dir.exists():
        raise UserFacingError(
            f"No Amazon exports found in {amazon_input_dir}. Add a .zip or .csv export, or pass --amazon-input."
        )
    candidates = sorted(
        path
        for path in amazon_input_dir.iterdir()
        if path.is_file() and path.suffix.lower() in {".csv", ".zip"}
    )
    if not candidates:
        raise UserFacingError(
            f"No Amazon exports found in {amazon_input_dir}. Add a .zip or .csv export, or pass --amazon-input."
        )
    if len(candidates) == 1:
        return candidates[0]
    return max(candidates, key=lambda path: (path.stat().st_mtime, str(path)))


def send_macos_notification(message: str, title: str = "Library Valuation") -> None:
    try:
        if os.environ.get("LIBRARY_PIPELINE_DISABLE_NOTIFICATIONS"):
            return
        if platform.system() != "Darwin" or not sys.stdout.isatty():
            return
        osascript = shutil.which("osascript")
        if not osascript:
            return
        subprocess.run(
            [osascript, "-e", f"display notification {applescript_string(message)} with title {applescript_string(title)}"],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except OSError:
        pass


def applescript_string(value: str) -> str:
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def format_update_summary(summary: dict[str, int | str], output_dir: Path) -> str:
    return "\n".join(
        [
            "Amazon export:",
            f"  {summary.get('amazon_export', '')}",
            f"Amazon rows processed:      {summary.get('amazon_row_count', 0)}",
            f"Book candidates:            {summary.get('purchase_rows', 0)}",
            "Catalog",
            f"  Durable total:            {summary.get('catalog_durable_total', 0)}",
            f"  Current export:           {summary.get('catalog_current_export', 0)}",
            f"  Existing in export:       {summary.get('catalog_existing', 0)}",
            f"  New this run:             {summary.get('catalog_new', 0)}",
            "Acquisitions",
            f"  Rebuilt:                  {summary.get('acquisition_rows', 0)}",
            f"  New this run:             {summary.get('acquisition_new', 0)}",
            "Research Assessments",
            f"  Durable total:            {summary.get('research_durable_total', 0)}",
            f"  Reused for export:        {summary.get('research_reused', 0)}",
            f"  Created this run:         {summary.get('research_created', 0)}",
            f"  Research Candidates:      {summary.get('research_candidates', 0)}",
            f"Manifest entries:           {summary.get('manifest_entries', 0)}",
            "Outputs",
            f"  {output_dir / 'book_purchases.xlsx'}",
            f"  {output_dir / 'book_metadata.xlsx'}",
            f"  {output_dir / 'library_catalog.xlsx'}",
            f"  {output_dir / 'research_candidates.csv'}",
            f"  {output_dir / 'research_candidates.xlsx'}",
            f"  {output_dir / 'collector_workbook.xlsx'}",
        ]
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    summarize_parser = subparsers.add_parser("summarize")
    summarize_parser.add_argument("--input", required=True, type=Path)

    extract_parser = subparsers.add_parser("extract")
    extract_parser.add_argument("--input", required=True, type=Path)
    extract_parser.add_argument("--output", required=True, type=Path)

    enrich_parser = subparsers.add_parser("enrich-openlibrary")
    enrich_parser.add_argument("--input", required=True, type=Path)
    enrich_parser.add_argument("--output", required=True, type=Path)
    enrich_parser.add_argument(
        "--cache",
        type=Path,
        default=Path("output/openlibrary_cache.json"),
    )
    enrich_parser.add_argument("--delay", type=float, default=0.25)
    enrich_parser.add_argument("--limit", type=int)

    analyze_parser = subparsers.add_parser("analyze-enrichment")
    analyze_parser.add_argument("--input", required=True, type=Path)

    resolve_parser = subparsers.add_parser("resolve-missing")
    resolve_parser.add_argument("--input", required=True, type=Path)
    resolve_parser.add_argument("--output", required=True, type=Path)
    resolve_parser.add_argument(
        "--isbn-cache",
        type=Path,
        default=Path("output/openlibrary_cache.json"),
    )
    resolve_parser.add_argument(
        "--search-cache",
        type=Path,
        default=Path("output/openlibrary_search_cache.json"),
    )
    resolve_parser.add_argument("--delay", type=float, default=0.25)

    update_parser = subparsers.add_parser("update-library")
    update_parser.add_argument("--amazon-input", type=Path)
    update_parser.add_argument("--input-dir", type=Path, default=Path("input"))
    update_parser.add_argument("--data-dir", type=Path, default=Path("data"))
    update_parser.add_argument("--cache-dir", type=Path, default=Path("cache"))
    update_parser.add_argument("--config-dir", type=Path, default=Path("config"))
    update_parser.add_argument("--output-dir", type=Path, default=Path("output"))
    update_parser.add_argument(
        "--isbn-cache",
        type=Path,
    )
    update_parser.add_argument(
        "--search-cache",
        type=Path,
    )
    update_parser.add_argument("--delay", type=float, default=0.25)

    market_sample_parser = subparsers.add_parser("generate-market-validation-sample")
    market_sample_parser.add_argument("--output-dir", type=Path, default=Path("output"))
    market_sample_parser.add_argument("--data-dir", type=Path, default=Path("data"))
    market_sample_parser.add_argument("--sample-size-per-band", type=int, default=20)
    market_sample_parser.add_argument("--seed", type=int, default=42)

    abebooks_parser = subparsers.add_parser("collect-abebooks-observations")
    abebooks_parser.add_argument("--output-dir", type=Path, default=Path("output"))
    abebooks_parser.add_argument("--limit", type=int, default=30)
    abebooks_parser.add_argument("--delay", type=float, default=1.0)
    abebooks_parser.add_argument("--max-results-per-book", type=int, default=3)

    coverage_parser = subparsers.add_parser("report-market-observation-coverage")
    coverage_parser.add_argument("--output-dir", type=Path, default=Path("output"))

    analysis_parser = subparsers.add_parser("analyze-market-validation")
    analysis_parser.add_argument("--output-dir", type=Path, default=Path("output"))

    signal_review_parser = subparsers.add_parser("review-research-signal-effectiveness")
    signal_review_parser.add_argument("--output-dir", type=Path, default=Path("output"))

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "summarize":
            print(json.dumps(summarize(args.input), indent=2, sort_keys=True))
            return 0
        if args.command == "extract":
            count = extract_candidates(args.input, args.output)
            csv_path, xlsx_path = paired_output_paths(args.output)
            print(f"Wrote {count} book candidates to {csv_path} and {xlsx_path}")
            return 0
        if args.command == "enrich-openlibrary":
            count = enrich_openlibrary(args.input, args.output, args.cache, args.delay, args.limit)
            csv_path, xlsx_path = paired_output_paths(args.output)
            print(f"Wrote {count} enriched rows to {csv_path} and {xlsx_path}")
            return 0
        if args.command == "analyze-enrichment":
            print(json.dumps(analyze_enrichment(args.input), indent=2, sort_keys=True))
            return 0
        if args.command == "resolve-missing":
            counts = resolve_missing(args.input, args.output, args.isbn_cache, args.search_cache, args.delay)
            csv_path, xlsx_path = paired_output_paths(args.output)
            print(json.dumps(counts, indent=2, sort_keys=True))
            print(f"Wrote resolved rows to {csv_path} and {xlsx_path}")
            return 0
        if args.command == "update-library":
            paths = LibraryPaths(
                input_dir=args.input_dir,
                amazon_input_dir=args.input_dir / "amazon",
                data_dir=args.data_dir,
                cache_dir=args.cache_dir,
                openlibrary_cache_dir=args.cache_dir / "openlibrary",
                config_dir=args.config_dir,
                output_dir=args.output_dir,
            )
            amazon_input = args.amazon_input or discover_amazon_export(paths.amazon_input_dir)
            isbn_cache = args.isbn_cache or paths.openlibrary_isbn_cache_path
            search_cache = args.search_cache or paths.openlibrary_search_cache_path
            print("Using Amazon export:")
            print(f"  {amazon_input}")
            summary = update_library(
                amazon_input,
                args.output_dir,
                isbn_cache,
                search_cache,
                args.delay,
                paths=paths,
            )
            print(format_update_summary(summary, args.output_dir))
            send_macos_notification("Library update complete")
            return 0
        if args.command == "generate-market-validation-sample":
            count = generate_market_validation_sample(
                output_dir=args.output_dir,
                data_dir=args.data_dir,
                sample_size_per_band=args.sample_size_per_band,
                seed=args.seed,
            )
            csv_path, xlsx_path = paired_output_paths(args.output_dir / "market_validation_sample.csv")
            metadata_csv_path, metadata_xlsx_path = paired_output_paths(args.output_dir / "market_validation_sample_metadata.csv")
            print(f"Wrote {count} market validation sample rows to {csv_path} and {xlsx_path}")
            print(f"Wrote market validation sample metadata to {metadata_csv_path} and {metadata_xlsx_path}")
            return 0
        if args.command == "collect-abebooks-observations":
            count = collect_abebooks_observations(
                output_dir=args.output_dir,
                limit=args.limit,
                delay=args.delay,
                max_results_per_book=args.max_results_per_book,
            )
            csv_path, xlsx_path = paired_output_paths(args.output_dir / "market_observations.csv")
            print(f"Wrote {count} AbeBooks market observation rows to {csv_path} and {xlsx_path}")
            return 0
        if args.command == "report-market-observation-coverage":
            count = report_market_observation_coverage(args.output_dir)
            csv_path, xlsx_path = paired_output_paths(args.output_dir / "market_observation_coverage_report.csv")
            print(f"Wrote {count} market observation coverage rows to {csv_path} and {xlsx_path}")
            return 0
        if args.command == "analyze-market-validation":
            count = analyze_market_validation(args.output_dir)
            csv_path, xlsx_path = paired_output_paths(args.output_dir / "market_validation_analysis.csv")
            print(f"Wrote {count} market validation analysis rows to {csv_path} and {xlsx_path}")
            return 0
        if args.command == "review-research-signal-effectiveness":
            count = review_research_signal_effectiveness(args.output_dir)
            csv_path, xlsx_path = paired_output_paths(args.output_dir / "research_signal_effectiveness_review.csv")
            print(f"Wrote {count} research signal effectiveness rows to {csv_path} and {xlsx_path}")
            return 0
    except UserFacingError as error:
        print(f"Error: {error}", file=sys.stderr)
        if args.command == "update-library":
            send_macos_notification("Library update failed")
        return 1
    return 2


if __name__ == "__main__":
    raise SystemExit(main())

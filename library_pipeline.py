#!/usr/bin/env python3
"""Extract and enrich Amazon book purchases with library metadata."""

from __future__ import annotations

import argparse
import csv
import json
import re
import ssl
import sys
import time
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path
from xml.sax.saxutils import escape


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
        text = escape(str(value or ""))
        cells.append(f'<c r="{cell_ref}" t="inlineStr"{style_attr}><is><t>{text}</t></is></c>')
    return f'<row r="{row_index}">{"".join(cells)}</row>'


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
    candidates = []
    for row in iter_amazon_rows(input_path):
        candidate = book_candidate_from_row(row)
        if candidate:
            candidates.append(candidate)
    return candidates


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
) -> dict[str, int]:
    output_dir.mkdir(parents=True, exist_ok=True)
    purchases = extract_candidate_rows(amazon_input)
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
    catalog_rows = build_library_catalog_rows(purchases, metadata_rows)

    write_table_outputs(output_dir / "book_metadata.csv", BOOK_METADATA_FIELDNAMES, metadata_rows, "Book Metadata")
    write_table_outputs(output_dir / "library_catalog.csv", LIBRARY_CATALOG_FIELDNAMES, catalog_rows, "Library Catalog")
    save_cache(isbn_cache_path, isbn_cache)
    save_cache(search_cache_path, search_cache)

    return {
        "purchase_rows": len(purchases),
        "unique_books": len(metadata_rows),
        "metadata_matched": sum(1 for row in metadata_rows if row.get("openlibrary_status") == "matched"),
        "metadata_with_lcc": sum(1 for row in metadata_rows if row.get("lcc")),
        "metadata_manual_review": sum(1 for row in metadata_rows if row.get("resolution_source") == "manual_review"),
    }


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
) -> None:
    missing = [isbn for isbn in isbns if isbn and isbn not in isbn_cache]
    if not missing:
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
    update_parser.add_argument("--amazon-input", required=True, type=Path)
    update_parser.add_argument("--output-dir", type=Path, default=Path("output"))
    update_parser.add_argument(
        "--isbn-cache",
        type=Path,
        default=Path("output/openlibrary_cache.json"),
    )
    update_parser.add_argument(
        "--search-cache",
        type=Path,
        default=Path("output/openlibrary_search_cache.json"),
    )
    update_parser.add_argument("--delay", type=float, default=0.25)

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
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
        summary = update_library(args.amazon_input, args.output_dir, args.isbn_cache, args.search_cache, args.delay)
        print(json.dumps(summary, indent=2, sort_keys=True))
        print(f"Wrote monthly library outputs to {args.output_dir}")
        return 0
    return 2


if __name__ == "__main__":
    raise SystemExit(main())

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
from pathlib import Path


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
    output_path.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with output_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=BOOK_FIELDNAMES)
        writer.writeheader()
        for row in iter_amazon_rows(input_path):
            candidate = book_candidate_from_row(row)
            if candidate:
                writer.writerow(candidate)
                count += 1
    return count


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
    with cache_path.open("w", encoding="utf-8") as handle:
        json.dump(cache, handle, indent=2, sort_keys=True)


def openlibrary_lookup(isbn: str) -> dict:
    params = urllib.parse.urlencode(
        {
            "bibkeys": f"ISBN:{isbn}",
            "jscmd": "data",
            "format": "json",
        }
    )
    url = f"https://openlibrary.org/api/books?{params}"
    request = urllib.request.Request(url, headers={"User-Agent": "amazon-library-lcc/0.1"})
    context = ssl.create_default_context(cafile=ca_bundle_path())
    with urllib.request.urlopen(request, timeout=30, context=context) as response:
        data = json.load(response)
    return data.get(f"ISBN:{isbn}", {})


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


def enrich_openlibrary(input_path: Path, output_path: Path, cache_path: Path, delay: float, limit: int | None) -> int:
    cache = load_cache(cache_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    written = 0
    with input_path.open(newline="", encoding="utf-8-sig") as source, output_path.open(
        "w", newline="", encoding="utf-8"
    ) as target:
        reader = csv.DictReader(source)
        writer = csv.DictWriter(target, fieldnames=ENRICHED_FIELDNAMES)
        writer.writeheader()
        for row in reader:
            if limit is not None and written >= limit:
                break
            isbn = row.get("isbn13") or row.get("isbn10") or row.get("asin")
            if isbn not in cache:
                cache[isbn] = openlibrary_lookup(isbn)
                save_cache(cache_path, cache)
                time.sleep(delay)
            writer.writerow(enrich_row(row, cache[isbn]))
            written += 1
    save_cache(cache_path, cache)
    return written


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

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "summarize":
        print(json.dumps(summarize(args.input), indent=2, sort_keys=True))
        return 0
    if args.command == "extract":
        count = extract_candidates(args.input, args.output)
        print(f"Wrote {count} book candidates to {args.output}")
        return 0
    if args.command == "enrich-openlibrary":
        count = enrich_openlibrary(args.input, args.output, args.cache, args.delay, args.limit)
        print(f"Wrote {count} enriched rows to {args.output}")
        return 0
    if args.command == "analyze-enrichment":
        print(json.dumps(analyze_enrichment(args.input), indent=2, sort_keys=True))
        return 0
    return 2


if __name__ == "__main__":
    raise SystemExit(main())

"""Durable steward-reviewed estimates, separate from observed asking prices."""
from __future__ import annotations

import hashlib
import json
import re
import uuid
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path
from urllib.parse import urlsplit

CURRENCIES = ("USD", "GBP", "EUR", "CAD", "AUD", "CHF", "JPY", "NZD")
FILE_NAME = "reviewed_estimates.json"


def book_identity(book):
    fields = ("catalog_item_id", "isbn13", "isbn10", "title", "author", "publisher", "publication_year")
    return hashlib.sha256(json.dumps({name:getattr(book,name) for name in fields}, sort_keys=True).encode()).hexdigest()


def amount(value):
    if not isinstance(value, str) or not re.fullmatch(r"\d{1,9}(?:\.\d{1,2})?", value.strip()):
        raise ValueError("Enter a non-negative amount with at most two decimal places")
    try:
        number = Decimal(value.strip())
    except InvalidOperation as error:
        raise ValueError("Invalid estimate amount") from error
    return format(number.quantize(Decimal("0.01")), "f")


def validate_values(values, today):
    low, high = amount(values.get("low")), amount(values.get("high"))
    if Decimal(low) > Decimal(high):
        raise ValueError("The low estimate must not exceed the high estimate")
    currency = values.get("currency")
    if currency not in CURRENCIES:
        raise ValueError("Choose a supported currency")
    researched_on = values.get("researched_on", "")
    try:
        researched_on = date.fromisoformat(researched_on).isoformat()
        if date.fromisoformat(researched_on) > today:
            raise ValueError("The research date cannot be in the future")
    except (TypeError, ValueError) as error:
        raise ValueError("Enter a valid research date no later than today") from error
    note = values.get("note", "")
    if not isinstance(note, str) or not note.strip() or len(note) > 4000:
        raise ValueError("Explain the basis for your estimate in Answer or note (up to 4,000 characters)")
    links = values.get("source_urls", [])
    if not isinstance(links, list) or len(links) > 10:
        raise ValueError("Provide no more than 10 source links")
    clean = []
    for link in links:
        if not isinstance(link, str) or len(link) > 1000 or any(ord(c)<32 for c in link):
            raise ValueError("Invalid source link")
        parsed = urlsplit(link.strip())
        if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password:
            raise ValueError("Source links must be HTTP or HTTPS addresses without login details")
        if link.strip() not in clean:
            clean.append(link.strip())
    return dict(low=low, high=high, currency=currency, researched_on=researched_on,
                note=note.strip(), source_urls=clean)


def load_reviews(data_dir):
    path = Path(data_dir)/FILE_NAME
    if not path.exists():
        return []
    data = json.loads(path.read_text())
    if data.get("schema_version") != 1 or not isinstance(data.get("reviews"), list):
        raise ValueError("Unsupported reviewed-estimate repository")
    seen, latest = set(), {}
    for row in data["reviews"]:
        cid = row["catalog_item_id"]
        if row["review_id"] in seen or row.get("supersedes", "") != latest.get(cid, ""):
            raise ValueError("Conflicting reviewed-estimate history")
        if not re.fullmatch(r"[0-9a-f]{64}", row["book_identity"]):
            raise ValueError("Invalid reviewed-estimate book identity")
        validate_values(row, date.max)
        seen.add(row["review_id"]); latest[cid] = row["review_id"]
    return data["reviews"]


def current_reviews(data_dir, books):
    latest = {row["catalog_item_id"]:row for row in load_reviews(data_dir)}
    return {book.catalog_item_id:latest[book.catalog_item_id] for book in books
            if book.catalog_item_id in latest and latest[book.catalog_item_id]["book_identity"] == book_identity(book)}


def new_review(book, values, previous, timestamp):
    return dict(review_id="EST-"+str(uuid.uuid4()), catalog_item_id=book.catalog_item_id,
                book_identity=book_identity(book), title=book.title, isbn13=book.isbn13, isbn10=book.isbn10,
                saved_at=timestamp,
                supersedes=previous["review_id"] if previous else "", **values)


def rendered_reviews(reviews):
    return (json.dumps(dict(schema_version=1,reviews=reviews),indent=2,ensure_ascii=False)+"\n").encode()

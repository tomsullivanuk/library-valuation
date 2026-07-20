"""Pure, in-memory parsing for Libib CSV exports.

This module preserves source text alongside conservative normalized values. It
does not write files, create catalog identities, match records, or infer
holdings.
"""

from __future__ import annotations

import csv
import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from types import MappingProxyType
from typing import Mapping


LIBIB_EXPORT_COLUMNS = (
    "item_type",
    "title",
    "creators",
    "first_name",
    "last_name",
    "collection",
    "ean_isbn13",
    "upc_isbn10",
    "description",
    "publisher",
    "publish_date",
    "group",
    "tags",
    "notes",
    "price",
    "length",
    "number_of_discs",
    "number_of_players",
    "age_group",
    "ensemble",
    "aspect_ratio",
    "esrb",
    "rating",
    "review",
    "review_date",
    "status",
    "began",
    "completed",
    "added",
    "copies",
)

REQUIRED_COLUMNS = frozenset(
    {
        "item_type",
        "title",
        "creators",
        "first_name",
        "last_name",
        "collection",
        "ean_isbn13",
        "upc_isbn10",
        "publisher",
        "publish_date",
        "added",
        "copies",
    }
)
OPTIONAL_COLUMNS = frozenset(LIBIB_EXPORT_COLUMNS) - REQUIRED_COLUMNS

UNKNOWN_VALUES = frozenset({"unknown", "n/a", "na", "none", "null", "-", "?"})
SCIENTIFIC_NOTATION = re.compile(r"^[+-]?\d+(?:\.\d+)?[Ee][+-]?\d+$")
DIGITS = re.compile(r"^\d+$")


class LibibParseError(ValueError):
    """Raised when a file cannot be interpreted as a supported Libib export."""


@dataclass(frozen=True)
class LibibDiagnostic:
    code: str
    message: str
    row_number: int | None = None
    field: str | None = None


@dataclass(frozen=True)
class LibibSourceRecord:
    source_row_number: int
    raw_values: Mapping[str, str]
    raw_isbn10: str
    raw_isbn13: str
    raw_collection: str
    source_collection_label: str
    raw_publish_date: str
    raw_added_date: str
    raw_copies: str
    raw_creators: str
    raw_first_name: str
    raw_last_name: str
    raw_publisher: str
    normalized_isbn10: str | None
    normalized_isbn13: str | None
    isbn13_derived_from_isbn10: bool
    isbn_conflict: bool
    normalized_publish_date: str | None
    normalized_added_date: str | None
    normalized_creators: str | None
    primary_author_display: str | None
    normalized_publisher: str | None
    normalized_copies: int | None


@dataclass(frozen=True)
class LibibParseResult:
    records: tuple[LibibSourceRecord, ...]
    diagnostics: tuple[LibibDiagnostic, ...]
    columns: tuple[str, ...]
    unknown_columns: tuple[str, ...]


def parse_libib_csv(path: str | Path) -> LibibParseResult:
    """Parse a supported Libib CSV into immutable in-memory source records."""

    source = Path(path)
    try:
        with source.open(encoding="utf-8-sig", newline="") as handle:
            text = handle.read()
    except UnicodeDecodeError as exc:
        raise LibibParseError("Libib export must be UTF-8 encoded") from exc
    except OSError as exc:
        raise LibibParseError(f"Unable to read Libib export: {exc}") from exc

    reader = csv.DictReader(text.splitlines(keepends=True), dialect="excel")
    if reader.fieldnames is None:
        raise LibibParseError("Libib export is empty or has no header row")

    columns = tuple(_clean_header(value) for value in reader.fieldnames)
    if len(columns) != len(set(columns)):
        raise LibibParseError("Libib export contains duplicate column names")
    missing = sorted(REQUIRED_COLUMNS - set(columns))
    if missing:
        raise LibibParseError(f"Libib export is missing required columns: {', '.join(missing)}")
    reader.fieldnames = list(columns)

    diagnostics: list[LibibDiagnostic] = []
    unknown_columns = tuple(column for column in columns if column not in LIBIB_EXPORT_COLUMNS)
    if unknown_columns:
        diagnostics.append(
            LibibDiagnostic(
                code="unknown_columns",
                message=f"Preserved unknown Libib columns: {', '.join(unknown_columns)}",
            )
        )

    records: list[LibibSourceRecord] = []
    for row_number, row in enumerate(reader, start=2):
        if row.get(None):
            raise LibibParseError(f"Libib row {row_number} contains more values than the header")
        raw = {column: row.get(column, "") or "" for column in columns}
        records.append(_normalize_record(row_number, raw, diagnostics))

    return LibibParseResult(
        records=tuple(records),
        diagnostics=tuple(diagnostics),
        columns=columns,
        unknown_columns=unknown_columns,
    )


def _normalize_record(
    row_number: int, raw: dict[str, str], diagnostics: list[LibibDiagnostic]
) -> LibibSourceRecord:
    raw_isbn10 = raw["upc_isbn10"]
    raw_isbn13 = raw["ean_isbn13"]
    isbn10 = _normalize_isbn(raw_isbn10, 10, row_number, "upc_isbn10", diagnostics)
    isbn13 = _normalize_isbn(raw_isbn13, 13, row_number, "ean_isbn13", diagnostics)

    derived = False
    conflict = False
    if isbn10 and isbn13:
        conflict = isbn10_to_isbn13(isbn10) != isbn13
        if conflict:
            diagnostics.append(
                _diagnostic(
                    "isbn_conflict",
                    "Valid ISBN-10 and ISBN-13 values identify different editions or records",
                    row_number,
                    "ean_isbn13",
                )
            )
    elif isbn10:
        isbn13 = isbn10_to_isbn13(isbn10)
        derived = True

    return LibibSourceRecord(
        source_row_number=row_number,
        raw_values=MappingProxyType(dict(raw)),
        raw_isbn10=raw_isbn10,
        raw_isbn13=raw_isbn13,
        raw_collection=raw["collection"],
        source_collection_label=raw["collection"].strip(),
        raw_publish_date=raw["publish_date"],
        raw_added_date=raw["added"],
        raw_copies=raw["copies"],
        raw_creators=raw["creators"],
        raw_first_name=raw["first_name"],
        raw_last_name=raw["last_name"],
        raw_publisher=raw["publisher"],
        normalized_isbn10=isbn10,
        normalized_isbn13=isbn13,
        isbn13_derived_from_isbn10=derived,
        isbn_conflict=conflict,
        normalized_publish_date=_normalize_date(
            raw["publish_date"], row_number, "publish_date", diagnostics
        ),
        normalized_added_date=_normalize_date(raw["added"], row_number, "added", diagnostics),
        normalized_creators=_normalize_text(raw["creators"]),
        primary_author_display=_primary_author(raw["first_name"], raw["last_name"]),
        normalized_publisher=_normalize_text(raw["publisher"]),
        normalized_copies=_normalize_copies(raw["copies"], row_number, diagnostics),
    )


def _normalize_isbn(
    raw: str,
    length: int,
    row_number: int,
    field: str,
    diagnostics: list[LibibDiagnostic],
) -> str | None:
    value = raw.strip()
    if not value:
        return None
    if value.casefold() in UNKNOWN_VALUES:
        diagnostics.append(_diagnostic("unknown_value", "ISBN is marked unknown", row_number, field))
        return None
    if SCIENTIFIC_NOTATION.fullmatch(value):
        diagnostics.append(
            _diagnostic(
                "excel_scientific_notation",
                "ISBN appears to have been converted to scientific notation by spreadsheet software",
                row_number,
                field,
            )
        )
        return None
    if length == 10 and DIGITS.fullmatch(value) and len(value) == 9:
        diagnostics.append(
            _diagnostic(
                "excel_missing_leading_zero",
                "ISBN-10 has nine digits and may have lost a leading zero in spreadsheet software",
                row_number,
                field,
            )
        )
        return None
    if DIGITS.fullmatch(value) and len(value) < length:
        diagnostics.append(
            _diagnostic(
                "truncated_isbn",
                f"ISBN-{length} has fewer than {length} characters",
                row_number,
                field,
            )
        )
        return None
    valid = is_valid_isbn10(value) if length == 10 else is_valid_isbn13(value)
    if not valid:
        diagnostics.append(
            _diagnostic("invalid_isbn", f"Value is not a valid ISBN-{length}", row_number, field)
        )
        return None
    return value[:-1] + "X" if length == 10 and value[-1] in "xX" else value


def is_valid_isbn10(value: str) -> bool:
    if not re.fullmatch(r"\d{9}[\dXx]", value):
        return False
    total = sum((10 - index) * (10 if char in "Xx" else int(char)) for index, char in enumerate(value))
    return total % 11 == 0


def is_valid_isbn13(value: str) -> bool:
    if not re.fullmatch(r"\d{13}", value):
        return False
    return sum(int(char) * (1 if index % 2 == 0 else 3) for index, char in enumerate(value)) % 10 == 0


def isbn10_to_isbn13(value: str) -> str:
    if not is_valid_isbn10(value):
        raise ValueError("Cannot convert invalid ISBN-10")
    base = "978" + value[:9]
    check = (-sum(int(char) * (1 if index % 2 == 0 else 3) for index, char in enumerate(base))) % 10
    return base + str(check)


def _normalize_date(
    raw: str, row_number: int, field: str, diagnostics: list[LibibDiagnostic]
) -> str | None:
    value = raw.strip()
    if not value:
        return None
    if value.casefold() in UNKNOWN_VALUES:
        diagnostics.append(_diagnostic("unknown_value", "Date is marked unknown", row_number, field))
        return None
    if re.fullmatch(r"\d{1,2}/\d{1,2}/\d{2,4}", value):
        diagnostics.append(
            _diagnostic(
                "excel_locale_date",
                "Date uses an ambiguous locale-specific format associated with spreadsheet re-save",
                row_number,
                field,
            )
        )
        return None
    try:
        parsed = date.fromisoformat(value)
    except ValueError:
        diagnostics.append(
            _diagnostic("malformed_date", "Date must use Libib's observed YYYY-MM-DD format", row_number, field)
        )
        return None
    if len(value) != 10:
        diagnostics.append(
            _diagnostic("malformed_date", "Date must use Libib's observed YYYY-MM-DD format", row_number, field)
        )
        return None
    return parsed.isoformat()


def _normalize_copies(
    raw: str, row_number: int, diagnostics: list[LibibDiagnostic]
) -> int | None:
    value = raw.strip()
    if not value:
        return None
    if value.casefold() in UNKNOWN_VALUES:
        diagnostics.append(_diagnostic("unknown_value", "Copies is marked unknown", row_number, "copies"))
        return None
    if not DIGITS.fullmatch(value) or int(value) < 1:
        diagnostics.append(
            _diagnostic("invalid_copies", "Copies must be a positive integer", row_number, "copies")
        )
        return None
    return int(value)


def _primary_author(first_name: str, last_name: str) -> str | None:
    return _normalize_text(" ".join(part for part in (first_name.strip(), last_name.strip()) if part))


def _normalize_text(value: str) -> str | None:
    normalized = " ".join(value.split())
    return normalized or None


def _clean_header(value: str | None) -> str:
    return (value or "").strip().lstrip("\ufeff")


def _diagnostic(code: str, message: str, row_number: int, field: str) -> LibibDiagnostic:
    return LibibDiagnostic(code=code, message=message, row_number=row_number, field=field)

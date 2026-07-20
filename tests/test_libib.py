from pathlib import Path

import pytest

from valuation.libib import (
    LIBIB_EXPORT_COLUMNS,
    LibibParseError,
    isbn10_to_isbn13,
    is_valid_isbn10,
    is_valid_isbn13,
    parse_libib_csv,
)


FIXTURES = Path(__file__).parent / "fixtures" / "libib"


def test_parse_untouched_export_preserves_source_and_normalizes_records():
    result = parse_libib_csv(FIXTURES / "untouched_export.csv")

    assert len(result.records) == 3
    assert result.columns == LIBIB_EXPORT_COLUMNS
    assert result.unknown_columns == ()
    assert result.records[0].raw_isbn10 == "0306406152"
    assert result.records[0].raw_isbn13 == "9780306406157"
    assert result.records[0].raw_collection == "Study"
    assert result.records[0].source_collection_label == "Study"
    assert result.records[0].raw_publish_date == "1980-01-15"
    assert result.records[0].raw_added_date == "2026-07-19"
    assert result.records[0].raw_values["description"].startswith("A synthetic fixture")
    assert result.records[0].normalized_isbn10 == "0306406152"
    assert result.records[0].normalized_isbn13 == "9780306406157"
    assert result.records[0].normalized_publish_date == "1980-01-15"
    assert result.records[0].normalized_added_date == "2026-07-19"
    assert result.records[0].normalized_copies == 1


def test_missing_optional_columns_are_accepted_and_empty_values_remain_empty():
    result = parse_libib_csv(FIXTURES / "missing_optional_fields.csv")

    assert len(result.records) == 1
    assert result.records[0].raw_publisher == ""
    assert result.records[0].normalized_publisher is None
    assert result.records[0].normalized_publish_date is None
    assert result.diagnostics == ()


def test_missing_required_columns_raise_friendly_error():
    with pytest.raises(LibibParseError, match="copies, first_name, last_name"):
        parse_libib_csv(FIXTURES / "missing_required_fields.csv")


@pytest.mark.parametrize(
    ("value", "valid"),
    [("0306406152", True), ("0198786220", True), ("306406152", False), ("0306406153", False)],
)
def test_isbn10_validation_preserves_string_semantics(value, valid):
    assert is_valid_isbn10(value) is valid


@pytest.mark.parametrize(
    ("value", "valid"),
    [("9780306406157", True), ("9780198786221", True), ("9780306406158", False), ("9.78031E+12", False)],
)
def test_isbn13_validation(value, valid):
    assert is_valid_isbn13(value) is valid


def test_isbn13_is_derived_from_valid_isbn10_when_missing():
    result = parse_libib_csv(FIXTURES / "untouched_export.csv")
    record = result.records[2]

    assert isbn10_to_isbn13("0306406152") == "9780306406157"
    assert record.raw_isbn13 == ""
    assert record.normalized_isbn13 == "9780306406157"
    assert record.isbn13_derived_from_isbn10 is True


def test_valid_but_disagreeing_isbns_record_conflict(tmp_path):
    fixture = (FIXTURES / "missing_optional_fields.csv").read_text(encoding="utf-8")
    path = tmp_path / "conflict.csv"
    path.write_text(fixture.replace("9780306406157", "9780198786221"), encoding="utf-8")

    result = parse_libib_csv(path)

    assert result.records[0].isbn_conflict is True
    assert "isbn_conflict" in diagnostic_codes(result)


def test_author_normalization_uses_creators_and_primary_name_fields():
    result = parse_libib_csv(FIXTURES / "untouched_export.csv")

    assert result.records[0].raw_creators == "Curie, Marie"
    assert result.records[0].normalized_creators == "Curie, Marie"
    assert result.records[0].primary_author_display == "Marie Curie"


def test_collection_is_preserved_as_source_evidence_without_location_identity():
    result = parse_libib_csv(FIXTURES / "untouched_export.csv")

    assert result.records[2].source_collection_label == "Unmapped Catalog Label"
    assert not hasattr(result.records[2], "location_id")


def test_copies_are_normalized_but_do_not_create_holdings():
    result = parse_libib_csv(FIXTURES / "untouched_export.csv")

    assert result.records[1].raw_copies == "2"
    assert result.records[1].normalized_copies == 2
    assert not hasattr(result.records[1], "holding_id")


def test_excel_corruption_and_malformed_dates_produce_diagnostics():
    result = parse_libib_csv(FIXTURES / "excel_corrupted_export.csv")
    codes = diagnostic_codes(result)

    assert "excel_scientific_notation" in codes
    assert "excel_missing_leading_zero" in codes
    assert "truncated_isbn" in codes
    assert "excel_locale_date" in codes
    assert "malformed_date" in codes
    assert result.records[0].raw_isbn13 == "9.78031E+12"
    assert result.records[0].normalized_isbn13 is None
    assert result.records[0].normalized_added_date is None


def test_unknown_structured_values_are_preserved_and_diagnosed():
    result = parse_libib_csv(FIXTURES / "untouched_export.csv")
    record = result.records[2]

    assert record.raw_copies == "unknown"
    assert record.normalized_copies is None
    assert record.raw_values["review_date"] == "unknown"
    assert "unknown_value" in diagnostic_codes(result)


def test_unknown_columns_are_preserved_and_reported(tmp_path):
    fixture = (FIXTURES / "missing_optional_fields.csv").read_text(encoding="utf-8")
    header, row = fixture.splitlines()
    path = tmp_path / "future-column.csv"
    path.write_text(f"{header},future_field\n{row},source evidence\n", encoding="utf-8")

    result = parse_libib_csv(path)

    assert result.unknown_columns == ("future_field",)
    assert result.records[0].raw_values["future_field"] == "source evidence"
    assert "unknown_columns" in diagnostic_codes(result)


def diagnostic_codes(result):
    return {diagnostic.code for diagnostic in result.diagnostics}

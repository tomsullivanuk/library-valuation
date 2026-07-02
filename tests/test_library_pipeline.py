import zipfile
from pathlib import Path

from library_pipeline import (
    analyze_enrichment,
    book_candidate_from_row,
    classify_asin,
    is_valid_isbn10,
    is_valid_isbn13,
    isbn10_to_isbn13,
    paired_output_paths,
    write_table_outputs,
)


def test_isbn10_validation_and_conversion():
    assert is_valid_isbn10("006157127X")
    assert isbn10_to_isbn13("006157127X") == "9780061571275"


def test_isbn13_validation():
    assert is_valid_isbn13("9780061571275")
    assert not is_valid_isbn13("9780061571276")


def test_classify_amazon_asin_vs_book_isbn():
    assert classify_asin("B07RG97YN6") == "amazon_asin"
    assert classify_asin("0198786220") == "isbn10"


def test_book_candidate_excludes_private_fields():
    row = {
        "ASIN": "0198786220",
        "Billing Address": "private",
        "Shipping Address": "private",
        "Carrier Name & Tracking Number": "private",
        "Payment Method Type": "private",
        "Order Date": "2021-10-10T22:33:42Z",
        "Order ID": "111-1660384-0033033",
        "Product Name": "Cognitive Neuroscience",
        "Product Condition": "New",
        "Original Quantity": "1",
        "Unit Price": "11.95",
        "Currency": "USD",
        "Website": "Amazon.com",
    }

    candidate = book_candidate_from_row(row)

    assert candidate["isbn13"] == "9780198786221"
    assert "Billing Address" not in candidate
    assert "Payment Method Type" not in candidate


def test_analyze_enrichment(tmp_path):
    path = tmp_path / "enriched.csv"
    path.write_text(
        "\n".join(
            [
                "openlibrary_status,lcc,dewey,lccn,oclc,subjects",
                "matched,PN1995 .A1,791,123,456,Film",
                "not_found,,,,,",
            ]
        ),
        encoding="utf-8",
    )

    summary = analyze_enrichment(path)

    assert summary["rows"] == 2
    assert summary["matched"] == 1
    assert summary["with_lcc"] == 1
    assert summary["lcc_rate"] == "50.0%"


def test_paired_output_paths():
    output = Path("output/books.csv")
    csv_path, xlsx_path = paired_output_paths(output)

    assert csv_path == output
    assert xlsx_path == Path("output/books.xlsx")


def test_write_table_outputs_creates_csv_and_xlsx(tmp_path):
    output = tmp_path / "books.csv"
    rows = [{"isbn13": "9780198786221", "title": "Cognitive neuroscience"}]

    csv_path, xlsx_path = write_table_outputs(output, ["isbn13", "title"], rows, "Books")

    assert csv_path.exists()
    assert xlsx_path.exists()
    assert csv_path.read_text(encoding="utf-8").splitlines()[0] == "isbn13,title"
    with zipfile.ZipFile(xlsx_path) as workbook:
        assert "xl/workbook.xml" in workbook.namelist()
        sheet_xml = workbook.read("xl/worksheets/sheet1.xml").decode("utf-8")
    assert "Cognitive neuroscience" in sheet_xml
    assert '<pane ySplit="1"' in sheet_xml

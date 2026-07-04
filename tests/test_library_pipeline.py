import zipfile
from pathlib import Path

from library_pipeline import (
    LibraryPaths,
    analyze_enrichment,
    assign_catalog_item_ids,
    book_candidate_from_row,
    build_book_metadata_rows,
    build_library_catalog_rows,
    build_parser,
    classify_asin,
    format_catalog_item_id,
    is_valid_isbn10,
    is_valid_isbn13,
    isbn10_to_isbn13,
    paired_output_paths,
    text_similarity,
    title_query,
    valuation_extension_context,
    write_table_outputs,
    xml_safe_text,
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


def test_library_paths_default_layout():
    paths = LibraryPaths()

    assert paths.input_dir == Path("input")
    assert paths.amazon_input_dir == Path("input/amazon")
    assert paths.data_dir == Path("data")
    assert paths.cache_dir == Path("cache")
    assert paths.openlibrary_cache_dir == Path("cache/openlibrary")
    assert paths.config_dir == Path("config")
    assert paths.output_dir == Path("output")
    assert paths.openlibrary_isbn_cache_path == Path("cache/openlibrary/isbn.json")
    assert paths.openlibrary_search_cache_path == Path("cache/openlibrary/search.json")


def test_format_catalog_item_id():
    assert format_catalog_item_id(1) == "BK000001"
    assert format_catalog_item_id(42) == "BK000042"


def test_format_catalog_item_id_rejects_non_positive_sequence():
    try:
        format_catalog_item_id(0)
    except ValueError as error:
        assert "positive" in str(error)
    else:
        raise AssertionError("Expected non-positive catalog item sequence to fail")


def test_assign_catalog_item_ids_adds_unique_ids_without_mutating_records():
    records = [{"isbn13": "9780198786221"}, {"isbn13": "9780061571275"}]

    assigned = assign_catalog_item_ids(records)

    assert [row["catalog_item_id"] for row in assigned] == ["BK000001", "BK000002"]
    assert records == [{"isbn13": "9780198786221"}, {"isbn13": "9780061571275"}]


def test_library_paths_ensure_directories(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    paths = LibraryPaths(
        input_dir=Path("custom-input"),
        amazon_input_dir=Path("custom-input/amazon"),
        data_dir=Path("custom-data"),
        cache_dir=Path("custom-cache"),
        openlibrary_cache_dir=Path("custom-cache/openlibrary"),
        config_dir=Path("custom-config"),
        output_dir=Path("custom-output"),
    )

    paths.ensure_directories()

    assert paths.input_dir.is_dir()
    assert paths.amazon_input_dir.is_dir()
    assert paths.data_dir.is_dir()
    assert paths.cache_dir.is_dir()
    assert paths.openlibrary_cache_dir.is_dir()
    assert paths.config_dir.is_dir()
    assert paths.output_dir.is_dir()


def test_update_library_input_dir_is_root_input_directory():
    args = build_parser().parse_args(["update-library", "--amazon-input", "orders.csv"])

    assert args.input_dir == Path("input")


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


def test_title_query_removes_trailing_series_note():
    row = {"product_name": "Cognitive Neuroscience: A Very Short Introduction (Very Short Introductions)"}

    assert title_query(row) == "Cognitive Neuroscience: A Very Short Introduction"


def test_text_similarity_scores_overlap():
    assert text_similarity("Cell and Psyche", "Cell and psyche") == 1.0
    assert text_similarity("Cell and Psyche", "Elements of Logic") < 0.5


def test_xml_safe_text_removes_excel_breaking_control_chars():
    assert xml_safe_text("Time.\x1e 0") == "Time.  0"


def test_build_book_metadata_rows_deduplicates_by_isbn():
    purchases = [
        {
            "asin": "0198786220",
            "isbn10": "0198786220",
            "isbn13": "9780198786221",
            "order_date": "2021-10-10T22:33:42Z",
            "order_id": "1",
            "product_name": "Cognitive Neuroscience",
            "product_condition": "New",
            "quantity": "1",
            "unit_price": "11.95",
            "currency": "USD",
            "website": "Amazon.com",
        },
        {
            "asin": "0198786220",
            "isbn10": "0198786220",
            "isbn13": "9780198786221",
            "order_date": "2022-01-01T00:00:00Z",
            "order_id": "2",
            "product_name": "Cognitive Neuroscience",
            "product_condition": "New",
            "quantity": "2",
            "unit_price": "11.95",
            "currency": "USD",
            "website": "Amazon.com",
        },
    ]
    cache = {
        "9780198786221": {
            "title": "Cognitive neuroscience",
            "authors": [{"name": "Richard Passingham"}],
            "classifications": {"lc_classifications": ["QP360.5"]},
        }
    }

    rows = build_book_metadata_rows(purchases, cache, {}, delay=0)

    assert len(rows) == 1
    assert rows[0]["purchase_count"] == "2"
    assert rows[0]["total_quantity"] == "3"
    assert rows[0]["catalog_item_id"] == "BK000001"
    assert rows[0]["title"] == "Cognitive neuroscience"
    assert rows[0]["lcc"] == "QP360.5"


def test_build_library_catalog_rows_joins_metadata():
    purchases = [{"isbn13": "9780198786221", "isbn10": "0198786220", "product_name": "Raw title"}]
    metadata = [
        {
            "isbn13": "9780198786221",
            "catalog_item_id": "BK000001",
            "title": "Cognitive neuroscience",
            "authors": "Richard Passingham",
            "lcc": "QP360.5",
            "resolution_source": "already_matched",
            "resolution_confidence": "high",
        }
    ]

    catalog = build_library_catalog_rows(purchases, metadata)

    assert catalog[0]["title"] == "Cognitive neuroscience"
    assert catalog[0]["lcc"] == "QP360.5"
    assert catalog[0]["catalog_item_id"] == "BK000001"


def test_valuation_extension_context_names_post_catalog_handoff():
    purchases = [{"isbn13": "9780198786221"}]
    metadata = [{"isbn13": "9780198786221", "title": "Cognitive neuroscience"}]
    catalog = [{"isbn13": "9780198786221", "title": "Cognitive neuroscience"}]

    context = valuation_extension_context(purchases, metadata, catalog)

    assert context == {
        "stage": "post_catalog_rows",
        "purchases": purchases,
        "metadata_rows": metadata,
        "catalog_rows": catalog,
    }

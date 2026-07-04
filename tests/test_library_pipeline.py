import hashlib
import zipfile
from pathlib import Path

from library_pipeline import (
    LibraryPaths,
    analyze_enrichment,
    acquisition_id,
    book_candidate_from_row,
    build_acquisitions,
    build_book_metadata_rows,
    build_library_catalog_rows,
    build_research_assessment,
    build_parser,
    classify_asin,
    file_sha256,
    format_catalog_item_id,
    is_valid_isbn10,
    is_valid_isbn13,
    isbn10_to_isbn13,
    load_acquisitions,
    load_catalog_items,
    load_research_assessments,
    paired_output_paths,
    reconcile_research_assessments,
    reconcile_catalog_items,
    text_similarity,
    title_query,
    update_library,
    valuation_extension_context,
    write_table_outputs,
    xml_safe_text,
)
from valuation.repositories import (
    AcquisitionRepository,
    CatalogRepository,
    ImportManifestRepository,
    ResearchAssessmentRepository,
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
    assert paths.import_manifest_path == Path("data/import_manifest.csv")
    assert paths.research_priority_assessments_path == Path("data/research_priority_assessments.csv")


def test_catalog_repository_missing_file_returns_empty_list(tmp_path):
    repository = CatalogRepository(tmp_path / "catalog_items.csv")

    assert repository.load() == []


def test_catalog_repository_round_trip_persistence(tmp_path):
    repository = CatalogRepository(tmp_path / "data" / "catalog_items.csv")
    rows = [
        {
            "catalog_item_id": "BK000001",
            "isbn13": "9780198786221",
            "isbn10": "0198786220",
            "title": "Cognitive neuroscience",
            "author": "Richard Passingham",
            "publisher": "Oxford",
            "publication_year": "2016",
            "source_fingerprint": "",
            "match_confidence": "high",
            "ignored_extra_field": "not persisted",
        }
    ]

    repository.save(rows)

    assert repository.path.read_text(encoding="utf-8").splitlines()[0] == (
        "catalog_item_id,isbn13,isbn10,title,author,publisher,publication_year,source_fingerprint,match_confidence"
    )
    assert repository.load() == [
        {
            "catalog_item_id": "BK000001",
            "isbn13": "9780198786221",
            "isbn10": "0198786220",
            "title": "Cognitive neuroscience",
            "author": "Richard Passingham",
            "publisher": "Oxford",
            "publication_year": "2016",
            "source_fingerprint": "",
            "match_confidence": "high",
        }
    ]


def test_catalog_repository_load_fills_missing_fields(tmp_path):
    path = tmp_path / "catalog_items.csv"
    path.write_text("catalog_item_id,isbn13,title\nBK000001,9780198786221,Cognitive neuroscience\n", encoding="utf-8")

    rows = CatalogRepository(path).load()

    assert rows[0]["catalog_item_id"] == "BK000001"
    assert rows[0]["isbn13"] == "9780198786221"
    assert rows[0]["isbn10"] == ""
    assert rows[0]["match_confidence"] == ""


def test_acquisition_repository_missing_file_returns_empty_list(tmp_path):
    repository = AcquisitionRepository(tmp_path / "acquisitions.csv")

    assert repository.load() == []


def test_acquisition_repository_round_trip_persistence(tmp_path):
    repository = AcquisitionRepository(tmp_path / "data" / "acquisitions.csv")
    rows = [
        {
            "acquisition_id": "AMZ-123",
            "catalog_item_id": "BK000001",
            "source": "amazon",
            "source_order_id": "1",
            "source_item_id": "SRC-123",
            "order_date": "2021-10-10T22:33:42Z",
            "quantity": "1",
            "item_price": "11.95",
            "item_subtotal": "11.95",
            "currency": "USD",
            "source_title": "Cognitive Neuroscience",
            "source_asin": "0198786220",
            "isbn13": "9780198786221",
            "isbn10": "0198786220",
            "ignored_extra_field": "not persisted",
        }
    ]

    repository.save(rows)

    assert repository.path.read_text(encoding="utf-8").splitlines()[0] == (
        "acquisition_id,catalog_item_id,source,source_order_id,source_item_id,order_date,"
        "quantity,item_price,item_subtotal,currency,source_title,source_asin,isbn13,isbn10"
    )
    assert repository.load() == [
        {
            "acquisition_id": "AMZ-123",
            "catalog_item_id": "BK000001",
            "source": "amazon",
            "source_order_id": "1",
            "source_item_id": "SRC-123",
            "order_date": "2021-10-10T22:33:42Z",
            "quantity": "1",
            "item_price": "11.95",
            "item_subtotal": "11.95",
            "currency": "USD",
            "source_title": "Cognitive Neuroscience",
            "source_asin": "0198786220",
            "isbn13": "9780198786221",
            "isbn10": "0198786220",
        }
    ]


def test_acquisition_repository_load_fills_missing_fields(tmp_path):
    path = tmp_path / "acquisitions.csv"
    path.write_text("acquisition_id,catalog_item_id,source\nAMZ-123,BK000001,amazon\n", encoding="utf-8")

    rows = AcquisitionRepository(path).load()

    assert rows[0]["acquisition_id"] == "AMZ-123"
    assert rows[0]["catalog_item_id"] == "BK000001"
    assert rows[0]["source"] == "amazon"
    assert rows[0]["source_order_id"] == ""
    assert rows[0]["isbn13"] == ""


def test_import_manifest_repository_missing_file_returns_empty_list(tmp_path):
    repository = ImportManifestRepository(tmp_path / "import_manifest.csv")

    assert repository.load() == []


def test_import_manifest_repository_append_creates_file(tmp_path):
    repository = ImportManifestRepository(tmp_path / "data" / "import_manifest.csv")

    repository.append(
        {
            "import_id": "IMP-1",
            "filename": "orders.csv",
            "file_hash": "abc123",
            "imported_at": "2026-07-04T00:00:00Z",
            "pipeline_version": "0.2.0",
            "schema_version": "1",
            "amazon_row_count": "2",
            "book_candidates": "1",
            "catalog_matches": "0",
            "new_catalog_items": "1",
            "acquisition_rows": "1",
            "status": "success",
            "notes": "ignored",
            "ignored_extra_field": "not persisted",
        }
    )

    assert repository.load() == [
        {
            "import_id": "IMP-1",
            "filename": "orders.csv",
            "file_hash": "abc123",
            "imported_at": "2026-07-04T00:00:00Z",
            "pipeline_version": "0.2.0",
            "schema_version": "1",
            "amazon_row_count": "2",
            "book_candidates": "1",
            "catalog_matches": "0",
            "new_catalog_items": "1",
            "acquisition_rows": "1",
            "status": "success",
            "notes": "ignored",
        }
    ]


def test_import_manifest_repository_append_preserves_existing_rows(tmp_path):
    repository = ImportManifestRepository(tmp_path / "import_manifest.csv")

    repository.append({"import_id": "IMP-1", "filename": "first.csv"})
    repository.append({"import_id": "IMP-2", "filename": "second.csv"})

    rows = repository.load()
    assert [row["import_id"] for row in rows] == ["IMP-1", "IMP-2"]
    assert [row["filename"] for row in rows] == ["first.csv", "second.csv"]


def test_file_sha256_is_deterministic(tmp_path):
    path = tmp_path / "orders.csv"
    path.write_text("ASIN,Product Name\n0198786220,Cognitive Neuroscience\n", encoding="utf-8")

    assert file_sha256(path) == file_sha256(path)
    assert file_sha256(path) == hashlib.sha256(path.read_bytes()).hexdigest()


def test_research_assessment_repository_missing_file_returns_empty_list(tmp_path):
    repository = ResearchAssessmentRepository(tmp_path / "research_priority_assessments.csv")

    assert repository.load() == []


def test_research_assessment_repository_round_trip_persistence(tmp_path):
    repository = ResearchAssessmentRepository(tmp_path / "data" / "research_priority_assessments.csv")
    rows = [
        {
            "catalog_item_id": "BK000001",
            "isbn13": "9780198786221",
            "rps_score": "0.0000",
            "rps_band": "low",
            "rps_reasons": "No scoring signals available yet.",
            "rps_model_version": "0.2.0",
            "rps_config_hash": "abc123",
            "assessed_at": "2026-07-04T00:00:00Z",
            "assessment_status": "current",
            "assessment_method": "automatic",
            "reviewed_by": "",
            "metadata_snapshot_hash": "def456",
            "ignored_extra_field": "not persisted",
        }
    ]

    repository.save(rows)

    assert repository.load() == [
        {
            "catalog_item_id": "BK000001",
            "isbn13": "9780198786221",
            "rps_score": "0.0000",
            "rps_band": "low",
            "rps_reasons": "No scoring signals available yet.",
            "rps_model_version": "0.2.0",
            "rps_config_hash": "abc123",
            "assessed_at": "2026-07-04T00:00:00Z",
            "assessment_status": "current",
            "assessment_method": "automatic",
            "reviewed_by": "",
            "metadata_snapshot_hash": "def456",
        }
    ]


def test_build_research_assessment_populates_provenance():
    assessment = build_research_assessment(
        {
            "catalog_item_id": "BK000001",
            "isbn13": "9780198786221",
            "title": "Cognitive neuroscience",
            "authors": "Richard Passingham",
        }
    )

    assert assessment["catalog_item_id"] == "BK000001"
    assert assessment["isbn13"] == "9780198786221"
    assert assessment["rps_score"] == "0.0000"
    assert assessment["rps_band"] == "low"
    assert assessment["rps_model_version"] == "0.2.0"
    assert assessment["rps_config_hash"]
    assert assessment["assessment_status"] == "current"
    assert assessment["assessment_method"] == "automatic"
    assert assessment["metadata_snapshot_hash"]


def test_reconcile_research_assessments_reuses_existing_assessment():
    existing = [
        {
            "catalog_item_id": "BK000001",
            "isbn13": "9780198786221",
            "rps_score": "0.9000",
            "rps_band": "high",
            "rps_reasons": "Previously reviewed.",
            "rps_model_version": "0.1.0",
            "rps_config_hash": "old",
            "assessed_at": "2026-01-01T00:00:00Z",
            "assessment_status": "current",
            "assessment_method": "automatic",
            "reviewed_by": "",
            "metadata_snapshot_hash": "old-snapshot",
        }
    ]

    reconciled = reconcile_research_assessments(
        existing,
        [{"catalog_item_id": "BK000001", "isbn13": "9780198786221", "title": "Updated title"}],
    )

    assert reconciled == existing


def test_reconcile_research_assessments_assesses_only_unassessed_items():
    existing = [
        {
            "catalog_item_id": "BK000001",
            "isbn13": "9780198786221",
            "rps_score": "0.9000",
            "rps_band": "high",
            "rps_reasons": "Previously reviewed.",
            "rps_model_version": "0.1.0",
            "rps_config_hash": "old",
            "assessed_at": "2026-01-01T00:00:00Z",
            "assessment_status": "current",
            "assessment_method": "automatic",
            "reviewed_by": "",
            "metadata_snapshot_hash": "old-snapshot",
        }
    ]

    reconciled = reconcile_research_assessments(
        existing,
        [
            {"catalog_item_id": "BK000001", "isbn13": "9780198786221", "title": "Known"},
            {"catalog_item_id": "BK000002", "isbn13": "9780061571275", "title": "New"},
        ],
    )

    assert len(reconciled) == 2
    assert reconciled[0] == existing[0]
    assert reconciled[1]["catalog_item_id"] == "BK000002"
    assert reconciled[1]["assessment_method"] == "automatic"


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


def test_acquisition_id_is_deterministic():
    first = acquisition_id("amazon", "ORDER-1", "0198786220", "2021-10-10", "Cognitive Neuroscience", "11.95", "1")
    second = acquisition_id("amazon", "ORDER-1", "0198786220", "2021-10-10", "Cognitive Neuroscience", "11.95", "1")
    different = acquisition_id("amazon", "ORDER-2", "0198786220", "2021-10-10", "Cognitive Neuroscience", "11.95", "1")

    assert first == second
    assert first.startswith("AMZ-")
    assert first != different


def test_reconcile_catalog_items_empty_catalog_creates_new_ids():
    metadata = [
        {"isbn13": "9780198786221", "isbn10": "0198786220", "title": "Cognitive neuroscience", "authors": "Richard Passingham"},
        {"isbn13": "9780061571275", "isbn10": "006157127X", "title": "The botany of desire", "authors": "Michael Pollan"},
    ]

    reconciled, catalog_items = reconcile_catalog_items(metadata, [])

    assert [row["catalog_item_id"] for row in reconciled] == ["BK000001", "BK000002"]
    assert [row["catalog_item_id"] for row in catalog_items] == ["BK000001", "BK000002"]
    assert catalog_items[0]["match_confidence"] == "high"


def test_reconcile_catalog_items_reuses_existing_isbn13_match():
    existing = [
        {
            "catalog_item_id": "BK000007",
            "isbn13": "9780198786221",
            "isbn10": "0198786220",
            "title": "Old title",
            "author": "Old author",
            "publisher": "",
            "publication_year": "",
            "source_fingerprint": "",
            "match_confidence": "high",
        }
    ]
    metadata = [{"isbn13": "9780198786221", "isbn10": "", "title": "Cognitive neuroscience", "authors": "Richard Passingham"}]

    reconciled, catalog_items = reconcile_catalog_items(metadata, existing)

    assert reconciled[0]["catalog_item_id"] == "BK000007"
    assert catalog_items[0]["catalog_item_id"] == "BK000007"
    assert catalog_items[0]["title"] == "Old title"


def test_reconcile_catalog_items_new_unmatched_book_gets_next_available_id():
    existing = [
        {
            "catalog_item_id": "BK000009",
            "isbn13": "9780198786221",
            "isbn10": "",
            "title": "Cognitive neuroscience",
            "author": "Richard Passingham",
            "publisher": "",
            "publication_year": "",
            "source_fingerprint": "",
            "match_confidence": "high",
        }
    ]
    metadata = [{"isbn13": "9780061571275", "isbn10": "", "title": "The botany of desire", "authors": "Michael Pollan"}]

    reconciled, catalog_items = reconcile_catalog_items(metadata, existing)

    assert reconciled[0]["catalog_item_id"] == "BK000010"
    assert [row["catalog_item_id"] for row in catalog_items] == ["BK000009", "BK000010"]


def test_reconcile_catalog_items_preserves_existing_items_not_in_latest_export():
    existing = [
        {
            "catalog_item_id": "BK000003",
            "isbn13": "9780198786221",
            "isbn10": "",
            "title": "Cognitive neuroscience",
            "author": "Richard Passingham",
            "publisher": "",
            "publication_year": "",
            "source_fingerprint": "",
            "match_confidence": "high",
        }
    ]

    _, catalog_items = reconcile_catalog_items([], existing)

    assert catalog_items == existing


def test_reconcile_catalog_items_preserves_existing_manual_fields():
    existing = [
        {
            "catalog_item_id": "BK000004",
            "isbn13": "9780198786221",
            "isbn10": "",
            "title": "Manual title",
            "author": "Manual author",
            "publisher": "Manual publisher",
            "publication_year": "1999",
            "source_fingerprint": "manual-fingerprint",
            "match_confidence": "manual",
        }
    ]
    metadata = [
        {
            "isbn13": "9780198786221",
            "isbn10": "0198786220",
            "title": "Cognitive neuroscience",
            "authors": "Richard Passingham",
            "publishers": "Oxford",
            "publish_date": "2016",
        }
    ]

    _, catalog_items = reconcile_catalog_items(metadata, existing)

    assert catalog_items[0] == {
        **existing[0],
        "isbn10": "0198786220",
    }


def test_reconcile_catalog_items_duplicate_incoming_isbn_reuses_one_catalog_item():
    metadata = [
        {"isbn13": "9780198786221", "isbn10": "0198786220", "title": "Cognitive neuroscience", "authors": "Richard Passingham"},
        {"isbn13": "9780198786221", "isbn10": "0198786220", "title": "Cognitive neuroscience", "authors": "Richard Passingham"},
    ]

    reconciled, catalog_items = reconcile_catalog_items(metadata, [])

    assert [row["catalog_item_id"] for row in reconciled] == ["BK000001", "BK000001"]
    assert [row["catalog_item_id"] for row in catalog_items] == ["BK000001"]


def test_reconcile_catalog_items_next_id_uses_highest_existing_bk_number():
    existing = [
        {
            "catalog_item_id": "BK000100",
            "isbn13": "9780198786221",
            "isbn10": "",
            "title": "Cognitive neuroscience",
            "author": "Richard Passingham",
            "publisher": "",
            "publication_year": "",
            "source_fingerprint": "",
            "match_confidence": "high",
        },
        {
            "catalog_item_id": "MANUAL-ID",
            "isbn13": "9780061571275",
            "isbn10": "",
            "title": "The botany of desire",
            "author": "Michael Pollan",
            "publisher": "",
            "publication_year": "",
            "source_fingerprint": "",
            "match_confidence": "manual",
        },
    ]
    metadata = [{"isbn13": "9780307387899", "isbn10": "", "title": "The mindful brain", "authors": "Daniel Siegel"}]

    reconciled, _ = reconcile_catalog_items(metadata, existing)

    assert reconciled[0]["catalog_item_id"] == "BK000101"


def test_reconcile_catalog_items_title_author_fallback_requires_title_and_author():
    existing = [
        {
            "catalog_item_id": "BK000011",
            "isbn13": "",
            "isbn10": "",
            "title": "Cognitive neuroscience",
            "author": "",
            "publisher": "",
            "publication_year": "",
            "source_fingerprint": "",
            "match_confidence": "needs_review",
        }
    ]
    metadata = [{"isbn13": "", "isbn10": "", "title": "Cognitive neuroscience", "authors": ""}]

    reconciled, catalog_items = reconcile_catalog_items(metadata, existing)

    assert reconciled[0]["catalog_item_id"] == "BK000012"
    assert [row["catalog_item_id"] for row in catalog_items] == ["BK000011", "BK000012"]


def test_build_acquisitions_links_purchase_rows_to_catalog_items():
    purchases = [
        {
            "asin": "0198786220",
            "isbn10": "0198786220",
            "isbn13": "9780198786221",
            "order_date": "2021-10-10T22:33:42Z",
            "order_id": "1",
            "product_name": "Cognitive Neuroscience",
            "quantity": "2",
            "unit_price": "11.95",
            "currency": "USD",
        }
    ]
    metadata = [{"isbn13": "9780198786221", "catalog_item_id": "BK000001"}]

    acquisitions = build_acquisitions(purchases, metadata)

    assert len(acquisitions) == 1
    assert acquisitions[0]["catalog_item_id"] == "BK000001"
    assert acquisitions[0]["source"] == "amazon"
    assert acquisitions[0]["source_order_id"] == "1"
    assert acquisitions[0]["source_asin"] == "0198786220"
    assert acquisitions[0]["item_price"] == "11.95"
    assert acquisitions[0]["item_subtotal"] == "23.90"
    assert acquisitions[0]["acquisition_id"].startswith("AMZ-")


def test_build_acquisitions_allows_multiple_rows_for_same_catalog_item():
    purchases = [
        {
            "asin": "0198786220",
            "isbn10": "0198786220",
            "isbn13": "9780198786221",
            "order_date": "2021-10-10T22:33:42Z",
            "order_id": "1",
            "product_name": "Cognitive Neuroscience",
            "quantity": "1",
            "unit_price": "11.95",
            "currency": "USD",
        },
        {
            "asin": "0198786220",
            "isbn10": "0198786220",
            "isbn13": "9780198786221",
            "order_date": "2022-01-01T00:00:00Z",
            "order_id": "2",
            "product_name": "Cognitive Neuroscience",
            "quantity": "1",
            "unit_price": "12.95",
            "currency": "USD",
        },
    ]
    metadata = [{"isbn13": "9780198786221", "catalog_item_id": "BK000001"}]

    acquisitions = build_acquisitions(purchases, metadata)

    assert len(acquisitions) == 2
    assert {row["catalog_item_id"] for row in acquisitions} == {"BK000001"}
    assert acquisitions[0]["acquisition_id"] != acquisitions[1]["acquisition_id"]


def test_build_acquisitions_links_by_isbn10_when_isbn13_is_blank():
    purchases = [
        {
            "asin": "0198786220",
            "isbn10": "0198786220",
            "isbn13": "",
            "order_date": "2021-10-10T22:33:42Z",
            "order_id": "1",
            "product_name": "Cognitive Neuroscience",
            "quantity": "1",
            "unit_price": "11.95",
            "currency": "USD",
        }
    ]
    metadata = [{"isbn13": "", "isbn10": "0198786220", "catalog_item_id": "BK000001"}]

    acquisitions = build_acquisitions(purchases, metadata)

    assert acquisitions[0]["catalog_item_id"] == "BK000001"


def test_build_acquisitions_links_by_title_when_isbns_are_blank():
    purchases = [
        {
            "asin": "",
            "isbn10": "",
            "isbn13": "",
            "order_date": "2021-10-10T22:33:42Z",
            "order_id": "1",
            "product_name": "Cognitive Neuroscience",
            "quantity": "1",
            "unit_price": "11.95",
            "currency": "USD",
        }
    ]
    metadata = [{"isbn13": "", "isbn10": "", "title": "Cognitive neuroscience", "catalog_item_id": "BK000001"}]

    acquisitions = build_acquisitions(purchases, metadata)

    assert acquisitions[0]["catalog_item_id"] == "BK000001"


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


def test_update_library_writes_catalog_acquisitions_and_manifest_csv(tmp_path):
    amazon_input = tmp_path / "orders.csv"
    amazon_input.write_text(
        "\n".join(
            [
                "ASIN,Order Date,Order ID,Product Name,Product Condition,Original Quantity,Unit Price,Currency,Website",
                "0198786220,2021-10-10T22:33:42Z,1,Cognitive Neuroscience,New,1,11.95,USD,Amazon.com",
                "B07RG97YN6,2021-10-11T22:33:42Z,2,Kindle Cover,New,1,9.95,USD,Amazon.com",
            ]
        ),
        encoding="utf-8",
    )
    isbn_cache = tmp_path / "output" / "openlibrary_cache.json"
    search_cache = tmp_path / "output" / "openlibrary_search_cache.json"
    isbn_cache.parent.mkdir()
    isbn_cache.write_text(
        '{"9780198786221": {"title": "Cognitive neuroscience", "authors": [{"name": "Richard Passingham"}], "publishers": [{"name": "Oxford"}], "publish_date": "2016"}}',
        encoding="utf-8",
    )
    search_cache.write_text("{}", encoding="utf-8")
    paths = LibraryPaths(
        input_dir=tmp_path / "input",
        amazon_input_dir=tmp_path / "input" / "amazon",
        data_dir=tmp_path / "data",
        cache_dir=tmp_path / "cache",
        openlibrary_cache_dir=tmp_path / "cache" / "openlibrary",
        config_dir=tmp_path / "config",
        output_dir=tmp_path / "output",
    )

    update_library(amazon_input, paths.output_dir, isbn_cache, search_cache, delay=0, paths=paths)

    catalog_items = load_catalog_items(paths.catalog_items_path)
    assert catalog_items == [
        {
            "catalog_item_id": "BK000001",
            "isbn13": "9780198786221",
            "isbn10": "0198786220",
            "title": "Cognitive neuroscience",
            "author": "Richard Passingham",
            "publisher": "Oxford",
            "publication_year": "2016",
            "source_fingerprint": "",
            "match_confidence": "high",
        }
    ]
    acquisitions = load_acquisitions(paths.acquisitions_path)
    assert len(acquisitions) == 1
    assert acquisitions[0]["catalog_item_id"] == "BK000001"
    assert acquisitions[0]["source"] == "amazon"
    assert acquisitions[0]["source_order_id"] == "1"
    assert acquisitions[0]["source_title"] == "Cognitive Neuroscience"
    research_assessments = load_research_assessments(paths.research_priority_assessments_path)
    assert len(research_assessments) == 1
    assert research_assessments[0]["catalog_item_id"] == "BK000001"
    assert research_assessments[0]["isbn13"] == "9780198786221"
    assert research_assessments[0]["rps_score"] == "0.0000"
    assert research_assessments[0]["rps_band"] == "low"
    assert research_assessments[0]["assessment_status"] == "current"
    assert research_assessments[0]["assessment_method"] == "automatic"
    manifest_rows = ImportManifestRepository(paths.import_manifest_path).load()
    assert len(manifest_rows) == 1
    assert manifest_rows[0]["filename"] == "orders.csv"
    assert manifest_rows[0]["file_hash"] == file_sha256(amazon_input)
    assert manifest_rows[0]["pipeline_version"] == "0.2.0"
    assert manifest_rows[0]["schema_version"] == "1"
    assert manifest_rows[0]["amazon_row_count"] == "2"
    assert manifest_rows[0]["book_candidates"] == "1"
    assert manifest_rows[0]["catalog_matches"] == "0"
    assert manifest_rows[0]["new_catalog_items"] == "1"
    assert manifest_rows[0]["acquisition_rows"] == "1"
    assert manifest_rows[0]["status"] == "success"
    assert (paths.output_dir / "book_purchases.csv").exists()
    assert (paths.output_dir / "book_metadata.csv").exists()
    assert (paths.output_dir / "library_catalog.csv").read_text(encoding="utf-8").splitlines()[0].startswith("catalog_item_id,")


def test_update_library_appends_manifest_rows_for_multiple_imports(tmp_path):
    amazon_input = tmp_path / "orders.csv"
    amazon_input.write_text(
        "\n".join(
            [
                "ASIN,Order Date,Order ID,Product Name,Product Condition,Original Quantity,Unit Price,Currency,Website",
                "0198786220,2021-10-10T22:33:42Z,1,Cognitive Neuroscience,New,1,11.95,USD,Amazon.com",
            ]
        ),
        encoding="utf-8",
    )
    isbn_cache = tmp_path / "output" / "openlibrary_cache.json"
    search_cache = tmp_path / "output" / "openlibrary_search_cache.json"
    isbn_cache.parent.mkdir()
    isbn_cache.write_text(
        '{"9780198786221": {"title": "Cognitive neuroscience", "authors": [{"name": "Richard Passingham"}]}}',
        encoding="utf-8",
    )
    search_cache.write_text("{}", encoding="utf-8")
    paths = LibraryPaths(
        input_dir=tmp_path / "input",
        amazon_input_dir=tmp_path / "input" / "amazon",
        data_dir=tmp_path / "data",
        cache_dir=tmp_path / "cache",
        openlibrary_cache_dir=tmp_path / "cache" / "openlibrary",
        config_dir=tmp_path / "config",
        output_dir=tmp_path / "output",
    )

    update_library(amazon_input, paths.output_dir, isbn_cache, search_cache, delay=0, paths=paths)
    first_assessment = load_research_assessments(paths.research_priority_assessments_path)[0]
    update_library(amazon_input, paths.output_dir, isbn_cache, search_cache, delay=0, paths=paths)

    research_assessments = load_research_assessments(paths.research_priority_assessments_path)
    assert research_assessments == [first_assessment]
    manifest_rows = ImportManifestRepository(paths.import_manifest_path).load()
    assert len(manifest_rows) == 2
    assert [row["status"] for row in manifest_rows] == ["success", "success"]
    assert [row["new_catalog_items"] for row in manifest_rows] == ["1", "0"]
    assert [row["catalog_matches"] for row in manifest_rows] == ["0", "1"]


def test_update_library_monthly_incremental_workflow_regression(tmp_path):
    paths = LibraryPaths(
        input_dir=tmp_path / "input",
        amazon_input_dir=tmp_path / "input" / "amazon",
        data_dir=tmp_path / "data",
        cache_dir=tmp_path / "cache",
        openlibrary_cache_dir=tmp_path / "cache" / "openlibrary",
        config_dir=tmp_path / "config",
        output_dir=tmp_path / "output",
    )
    isbn_cache, search_cache = write_monthly_workflow_caches(tmp_path)
    history_a = write_amazon_history(
        paths.amazon_input_dir / "history-a.csv",
        [
            {
                "asin": "0198786220",
                "order_date": "2021-10-10T22:33:42Z",
                "order_id": "1",
                "product_name": "Cognitive Neuroscience",
                "quantity": "1",
                "unit_price": "11.95",
            }
        ],
    )
    history_b = write_amazon_history(
        paths.amazon_input_dir / "history-b.csv",
        [
            {
                "asin": "0198786220",
                "order_date": "2021-10-10T22:33:42Z",
                "order_id": "1",
                "product_name": "Cognitive Neuroscience",
                "quantity": "1",
                "unit_price": "11.95",
            },
            {
                "asin": "006157127X",
                "order_date": "2022-01-15T12:00:00Z",
                "order_id": "2",
                "product_name": "The Printing Revolution in Early Modern Europe",
                "quantity": "1",
                "unit_price": "14.50",
            },
        ],
    )

    update_library(history_a, paths.output_dir, isbn_cache, search_cache, delay=0, paths=paths)

    run1_catalog_ids = catalog_ids_by_isbn(paths)
    run1_acquisition_ids = acquisition_ids(paths)
    run1_assessment_count = len(load_research_assessments(paths.research_priority_assessments_path))
    assert paths.catalog_items_path.exists()
    assert paths.acquisitions_path.exists()
    assert paths.import_manifest_path.exists()
    assert paths.research_priority_assessments_path.exists()
    assert len(ImportManifestRepository(paths.import_manifest_path).load()) == 1
    assert run1_catalog_ids == {"9780198786221": "BK000001"}
    assert len(run1_acquisition_ids) == 1
    assert run1_assessment_count == 1
    assert_monthly_outputs_exist(paths)

    update_library(history_a, paths.output_dir, isbn_cache, search_cache, delay=0, paths=paths)

    assert catalog_ids_by_isbn(paths) == run1_catalog_ids
    assert acquisition_ids(paths) == run1_acquisition_ids
    assert len(load_research_assessments(paths.research_priority_assessments_path)) == run1_assessment_count
    assert len(ImportManifestRepository(paths.import_manifest_path).load()) == 2
    assert_monthly_outputs_exist(paths)

    update_library(history_b, paths.output_dir, isbn_cache, search_cache, delay=0, paths=paths)

    run3_catalog_ids = catalog_ids_by_isbn(paths)
    run3_assessments = load_research_assessments(paths.research_priority_assessments_path)
    assert run3_catalog_ids["9780198786221"] == run1_catalog_ids["9780198786221"]
    assert set(run3_catalog_ids) == {"9780198786221", "9780061571275"}
    assert run3_catalog_ids["9780061571275"] == "BK000002"
    assert len(run3_catalog_ids) == len(run1_catalog_ids) + 1
    assert len(run3_assessments) == run1_assessment_count + 1
    assert len(load_acquisitions(paths.acquisitions_path)) == len(run1_acquisition_ids) + 1
    assert len(ImportManifestRepository(paths.import_manifest_path).load()) == 3
    assert_monthly_outputs_exist(paths)


def write_monthly_workflow_caches(tmp_path):
    isbn_cache = tmp_path / "output" / "openlibrary_cache.json"
    search_cache = tmp_path / "output" / "openlibrary_search_cache.json"
    isbn_cache.parent.mkdir()
    isbn_cache.write_text(
        "\n".join(
            [
                "{",
                '  "9780198786221": {"title": "Cognitive neuroscience", "authors": [{"name": "Richard Passingham"}], "publishers": [{"name": "Oxford"}], "publish_date": "2016"},',
                '  "9780061571275": {"title": "The Printing Revolution in Early Modern Europe", "authors": [{"name": "Elizabeth Eisenstein"}], "publishers": [{"name": "Cambridge"}], "publish_date": "2012"}',
                "}",
            ]
        ),
        encoding="utf-8",
    )
    search_cache.write_text("{}", encoding="utf-8")
    return isbn_cache, search_cache


def write_amazon_history(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = ["ASIN,Order Date,Order ID,Product Name,Product Condition,Original Quantity,Unit Price,Currency,Website"]
    for row in rows:
        lines.append(
            ",".join(
                [
                    row["asin"],
                    row["order_date"],
                    row["order_id"],
                    row["product_name"],
                    "New",
                    row["quantity"],
                    row["unit_price"],
                    "USD",
                    "Amazon.com",
                ]
            )
        )
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def catalog_ids_by_isbn(paths):
    return {row["isbn13"]: row["catalog_item_id"] for row in load_catalog_items(paths.catalog_items_path)}


def acquisition_ids(paths):
    return [row["acquisition_id"] for row in load_acquisitions(paths.acquisitions_path)]


def assert_monthly_outputs_exist(paths):
    assert (paths.output_dir / "book_purchases.csv").exists()
    assert (paths.output_dir / "book_purchases.xlsx").exists()
    assert (paths.output_dir / "book_metadata.csv").exists()
    assert (paths.output_dir / "book_metadata.xlsx").exists()
    assert (paths.output_dir / "library_catalog.csv").exists()
    assert (paths.output_dir / "library_catalog.xlsx").exists()


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

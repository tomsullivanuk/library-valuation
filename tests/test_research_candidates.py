import csv

from valuation.research_candidates import (
    RESEARCH_CANDIDATE_FIELDNAMES,
    build_research_candidate_rows,
)


def test_build_research_candidate_rows_excludes_none_band_and_sorts_deterministically():
    catalog_items = [
        catalog_item("BK000001", "A Medium Book", "1970"),
        catalog_item("BK000002", "A High Book", "1960"),
        catalog_item("BK000003", "A None Book", "1940"),
        catalog_item("BK000004", "An Older High Book", "1930"),
    ]
    assessments = [
        assessment("BK000001", "medium", "18", "2"),
        assessment("BK000002", "high", "30", "1"),
        assessment("BK000003", "none", "0", "0"),
        assessment("BK000004", "high", "30", "1"),
    ]

    rows = build_research_candidate_rows(catalog_items, [], [], assessments)

    assert [row["catalog_item_id"] for row in rows] == ["BK000004", "BK000002", "BK000001"]
    assert all(row["research_priority_band"] != "none" for row in rows)


def test_build_research_candidate_rows_aggregates_acquisitions_and_metadata():
    catalog_items = [
        {
            "catalog_item_id": "BK000001",
            "isbn13": "9780198786221",
            "isbn10": "0198786220",
            "title": "Catalog title",
            "author": "Catalog author",
            "publisher": "Catalog publisher",
            "publication_year": "2016",
            "match_confidence": "high",
        }
    ]
    metadata_rows = [
        {
            "catalog_item_id": "BK000001",
            "isbn13": "9780198786221",
            "title": "Metadata title",
            "authors": "Metadata author",
            "publishers": "Metadata publisher",
            "publish_date": "2015",
            "lcc": "QP360.5",
            "oclc": "12345",
            "subjects": "Neuroscience; Cognition",
            "resolution_source": "openlibrary_isbn",
            "resolution_confidence": "high",
        }
    ]
    acquisitions = [
        acquisition("BK000001", "2022-01-15T12:00:00Z", "2", "B002"),
        acquisition("BK000001", "2021-10-10T22:33:42Z", "1", "B001"),
        acquisition("BK000001", "2023-05-20T12:00:00Z", "2", "B001"),
    ]

    rows = build_research_candidate_rows(
        catalog_items,
        metadata_rows,
        acquisitions,
        [assessment("BK000001", "low", "13", "2")],
    )

    assert rows == [
        {
            "catalog_item_id": "BK000001",
            "isbn13": "9780198786221",
            "title": "Metadata title",
            "authors": "Metadata author",
            "publisher": "Metadata publisher",
            "publication_year": "2015",
            "research_priority_score": "13",
            "research_priority_band": "low",
            "research_signal_count": "2",
            "research_signal_codes": "missing_lcc; missing_oclc",
            "research_signal_summary": "missing_lcc:+8; missing_oclc:+5",
            "research_signal_explanations": "Missing LCC. | Missing OCLC.",
            "acquisition_count": "3",
            "first_acquired_date": "2021-10-10T22:33:42Z",
            "latest_acquired_date": "2023-05-20T12:00:00Z",
            "source_asins": "B001; B002",
            "source_order_ids": "1; 2",
            "metadata_source": "openlibrary_isbn",
            "metadata_confidence": "high",
            "lcc": "QP360.5",
            "oclc": "12345",
            "subjects": "Neuroscience; Cognition",
            "openlibrary_work_key": "",
            "openlibrary_edition_key": "",
        }
    ]


def test_research_candidate_fieldnames_do_not_use_valuation_terminology():
    joined_fieldnames = ",".join(RESEARCH_CANDIDATE_FIELDNAMES)

    assert "valuation" not in joined_fieldnames
    assert "price" not in joined_fieldnames
    assert "value" not in joined_fieldnames


def test_research_candidate_csv_header_matches_schema(tmp_path):
    path = tmp_path / "research_candidates.csv"
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=RESEARCH_CANDIDATE_FIELDNAMES)
        writer.writeheader()

    assert path.read_text(encoding="utf-8").splitlines()[0] == ",".join(RESEARCH_CANDIDATE_FIELDNAMES)


def catalog_item(catalog_item_id, title, publication_year):
    return {
        "catalog_item_id": catalog_item_id,
        "isbn13": "",
        "isbn10": "",
        "title": title,
        "author": "",
        "publisher": "",
        "publication_year": publication_year,
        "match_confidence": "",
    }


def assessment(catalog_item_id, band, score, signal_count):
    return {
        "catalog_item_id": catalog_item_id,
        "isbn13": "",
        "research_priority_score": score,
        "research_priority_band": band,
        "research_signal_count": signal_count,
        "research_signal_codes": "missing_lcc; missing_oclc" if signal_count != "0" else "",
        "research_signal_summary": "missing_lcc:+8; missing_oclc:+5" if signal_count != "0" else "",
        "research_signal_explanations": "Missing LCC. | Missing OCLC." if signal_count != "0" else "No research signals generated.",
    }


def acquisition(catalog_item_id, order_date, order_id, asin):
    return {
        "catalog_item_id": catalog_item_id,
        "order_date": order_date,
        "source_order_id": order_id,
        "source_asin": asin,
    }

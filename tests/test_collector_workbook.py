import zipfile
from xml.etree import ElementTree

from valuation.collector_workbook import (
    COLLECTOR_WORKBOOK_SHEETS,
    GENERATED_WORKBOOK_NOTE,
    write_collector_workbook,
)


def test_write_collector_workbook_creates_expected_sheets_and_content(tmp_path):
    output_path = tmp_path / "collector_workbook.xlsx"
    research_candidates = [
        {
            "catalog_item_id": "BK000002",
            "isbn13": "9780000000002",
            "title": "High Candidate",
            "research_priority_score": "30",
            "research_priority_band": "high",
            "research_signal_codes": "old_publication_year",
            "research_signal_summary": "old_publication_year:+12",
            "research_signal_explanations": "Published before the configured threshold.",
        },
        {
            "catalog_item_id": "BK000001",
            "isbn13": "9780000000001",
            "title": "Low Candidate",
            "research_priority_score": "13",
            "research_priority_band": "low",
            "research_signal_codes": "missing_lcc",
            "research_signal_summary": "missing_lcc:+8",
            "research_signal_explanations": "Missing Library of Congress Classification.",
        },
    ]
    collector_reviews = [
        {
            "catalog_item_id": "BK000001",
            "workflow_state": "reviewed",
            "disposition": "keep",
            "priority_override": "",
            "reviewed_at": "2026-07-08T00:00:00Z",
            "reviewed_by": "Tom",
            "review_notes": "Already checked.",
            "created_at": "2026-07-08T00:00:00Z",
            "updated_at": "2026-07-08T00:00:00Z",
        }
    ]

    write_collector_workbook(
        output_path,
        catalog_items=[
            {
                "catalog_item_id": "BK000001",
                "isbn13": "9780000000001",
                "title": "Low Candidate",
                "author": "",
                "publisher": "",
                "publication_year": "",
                "match_confidence": "",
            }
        ],
        acquisitions=[
            {
                "acquisition_id": "AMZ-1",
                "catalog_item_id": "BK000001",
                "source": "amazon",
                "source_order_id": "1",
                "source_item_id": "SRC-1",
                "order_date": "2021-10-10T22:33:42Z",
                "quantity": "1",
                "item_price": "11.95",
                "item_subtotal": "11.95",
                "currency": "USD",
                "source_title": "Low Candidate",
                "source_asin": "0000000001",
                "isbn13": "9780000000001",
                "isbn10": "0000000001",
            }
        ],
        research_candidates=research_candidates,
        collector_reviews=collector_reviews,
        metadata_rows=[],
        latest_import="input/amazon/orders.csv",
        run_summary={
            "imported_at": "2026-07-08T00:00:00Z",
            "amazon_row_count": 10,
            "purchase_rows": 2,
            "catalog_new": 1,
            "acquisition_new": 1,
            "research_durable_total": 2,
            "research_reused": 1,
            "research_created": 1,
        },
    )

    with zipfile.ZipFile(output_path) as workbook:
        assert workbook_sheet_names(workbook) == COLLECTOR_WORKBOOK_SHEETS
        summary_xml = workbook.read("xl/worksheets/sheet1.xml").decode("utf-8")
        candidates_xml = workbook.read("xl/worksheets/sheet2.xml").decode("utf-8")
        reviewed_xml = workbook.read("xl/worksheets/sheet4.xml").decode("utf-8")
        metadata_gaps_xml = workbook.read("xl/worksheets/sheet5.xml").decode("utf-8")
        reviews_xml = workbook.read("xl/worksheets/sheet6.xml").decode("utf-8")

    assert GENERATED_WORKBOOK_NOTE in summary_xml
    assert "Import Summary" in summary_xml
    assert "Amazon rows processed" in summary_xml
    assert "New catalog items from this import" in summary_xml
    assert "New acquisitions from this import" in summary_xml
    assert "Research Assessments" in summary_xml
    assert "Newly generated" in summary_xml
    assert "Metadata Gap count" in summary_xml
    assert candidates_xml.index("BK000002") < candidates_xml.index("BK000001")
    assert "Research Rationale" in candidates_xml
    assert "Published before the configured threshold." in candidates_xml
    assert "research_signal_codes" not in candidates_xml
    assert "research_signal_summary" not in candidates_xml
    assert "Already checked." in reviewed_xml
    assert "Already checked." in reviews_xml
    assert "gap_category" in metadata_gaps_xml
    assert "gap_count" in metadata_gaps_xml
    assert "Missing Publication Metadata" in metadata_gaps_xml
    assert "authors; publisher; publication_year" in metadata_gaps_xml
    assert '<pane ySplit="1"' in summary_xml
    assert ' s="2"' in candidates_xml


def workbook_sheet_names(workbook):
    namespace = {"main": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
    root = ElementTree.fromstring(workbook.read("xl/workbook.xml"))
    return [sheet.attrib["name"] for sheet in root.findall("main:sheets/main:sheet", namespace)]

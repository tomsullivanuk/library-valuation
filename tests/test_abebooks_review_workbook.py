import csv
import zipfile
from xml.etree import ElementTree

from library_pipeline import main
from valuation.abebooks_review_workbook import (
    EDITION_CONDITION_FIELDNAMES,
    MANUAL_RESEARCH_FIELDNAMES,
    POSSIBLE_SALE_FIELDNAMES,
    REVIEW_QUEUE_FIELDNAMES,
    REVIEW_WORKBOOK_SHEETS,
    add_acquisition_context,
    review_sort_key,
    write_abebooks_review_workbook,
)


def evidence_row(catalog_item_id, title, recommendation, likely_mid, likely_high):
    return {
        "catalog_item_id": catalog_item_id,
        "isbn_13": f"978{catalog_item_id[-10:]}",
        "title": title,
        "author": "Author",
        "listing_count": "3",
        "source_count": "1",
        "observed_source_names": "abebooks",
        "best_match_confidence": "high",
        "outlier_sensitivity": "low_outlier_sensitivity",
        "market_confidence": "moderate_confidence_market_evidence",
        "likely_low": "50",
        "likely_mid": likely_mid,
        "likely_high": likely_high,
        "review_recommendation": recommendation,
        "review_reason": "test_reason",
        "research_score": "30",
        "research_band": "8-10",
        "technical_field": "preserved",
    }


def test_acquisition_context_uses_latest_valid_date_and_conservative_unknown():
    summary = [
        evidence_row("BK1", "Recent", "review_for_possible_sale", "100", "120"),
        evidence_row("BK2", "Old", "review_for_possible_sale", "90", "110"),
        evidence_row("BK3", "Unknown", "manual_market_research_needed", "", ""),
    ]
    enriched = add_acquisition_context(
        summary,
        [
            {"catalog_item_id": "BK1", "order_date": "2020-01-01T00:00:00Z"},
            {"catalog_item_id": "BK1", "order_date": "2022-03-04"},
            {"catalog_item_id": "BK2", "order_date": "2020-12-31T23:00:00Z"},
            {"catalog_item_id": "BK3", "order_date": "not-a-date"},
        ],
    )

    assert enriched[0]["latest_acquired_date"] == "2022-03-04"
    assert enriched[0]["acquisition_year"] == "2022"
    assert enriched[0]["possession_confidence"] == "likely_present"
    assert enriched[1]["possession_confidence"] == "possibly_absent"
    assert "verify physical possession" in enriched[1]["possession_note"]
    assert enriched[2]["possession_confidence"] == "unknown"


def test_review_sort_prioritizes_recommendation_then_possession_then_price():
    rows = add_acquisition_context(
        [
            evidence_row("BK1", "Manual", "manual_market_research_needed", "500", "600"),
            evidence_row("BK2", "Old Sale", "review_for_possible_sale", "200", "250"),
            evidence_row("BK3", "Recent Sale", "review_for_possible_sale", "100", "150"),
        ],
        [
            {"catalog_item_id": "BK2", "order_date": "2020-01-01"},
            {"catalog_item_id": "BK3", "order_date": "2021-01-01"},
        ],
    )

    assert [row["catalog_item_id"] for row in sorted(rows, key=review_sort_key)] == ["BK3", "BK2", "BK1"]


def test_review_workbook_has_expected_tabs_subsets_detail_and_definitions(tmp_path):
    output = tmp_path / "review.xlsx"
    rows = [
        evidence_row("BK1", "Sale Book", "review_for_possible_sale", "100", "120"),
        evidence_row("BK2", "Manual Book", "manual_market_research_needed", "", ""),
        evidence_row("BK3", "Edition Book", "review_edition_or_condition", "75", "90"),
    ]
    write_abebooks_review_workbook(
        output,
        summary_rows=rows,
        acquisitions=[{"catalog_item_id": "BK1", "order_date": "2022-01-01"}],
    )

    with zipfile.ZipFile(output) as workbook:
        assert workbook_sheet_names(workbook) == REVIEW_WORKBOOK_SHEETS
        review_queue = workbook.read("xl/worksheets/sheet1.xml").decode()
        possible_sale = workbook.read("xl/worksheets/sheet2.xml").decode()
        manual = workbook.read("xl/worksheets/sheet3.xml").decode()
        edition = workbook.read("xl/worksheets/sheet4.xml").decode()
        detail = workbook.read("xl/worksheets/sheet5.xml").decode()
        run_summary = workbook.read("xl/worksheets/sheet6.xml").decode()
        definitions = workbook.read("xl/worksheets/sheet7.xml").decode()

    assert "technical_field" not in review_queue
    for reviewer_sheet in (review_queue, possible_sale, manual, edition):
        assert "source_count" not in reviewer_sheet
        assert "observed_source_names" not in reviewer_sheet
    assert xml_header_values(review_queue) == REVIEW_QUEUE_FIELDNAMES
    assert xml_header_values(possible_sale) == POSSIBLE_SALE_FIELDNAMES
    assert xml_header_values(manual) == MANUAL_RESEARCH_FIELDNAMES
    assert xml_header_values(edition) == EDITION_CONDITION_FIELDNAMES
    assert "Sale Book" in possible_sale and "Manual Book" not in possible_sale
    assert "Manual Book" in manual and "Sale Book" not in manual
    assert "Edition Book" in edition and "Sale Book" not in edition
    assert "technical_field" in detail and "preserved" in detail
    assert "source_count" in detail and "observed_source_names" in detail
    assert "Possession confidence counts" in run_summary
    assert "Observed source-count counts" in run_summary
    assert "Observed source-name counts" in run_summary
    assert "possession_confidence" in definitions
    assert "never suppresses price evidence" in definitions
    assert "source_or_derivation" in definitions
    assert "example_values" in definitions
    assert "Observed AbeBooks asking-price-derived reference" in definitions
    assert "not an appraisal, fair market value, realized sale price" in definitions
    assert "Count of observed marketplace listings" not in definitions
    assert "Count of observation rows whose lookup status is observed" in definitions
    assert "See the canonical evidence model documentation" not in definitions


def test_cli_builds_review_workbook(tmp_path, capsys):
    summary_path = tmp_path / "summary.csv"
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    output = tmp_path / "review.xlsx"
    rows = [evidence_row("BK1", "Sale Book", "review_for_possible_sale", "100", "120")]
    with summary_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    (data_dir / "acquisitions.csv").write_text(
        "catalog_item_id,order_date\nBK1,2022-01-01\n", encoding="utf-8"
    )

    assert main(
        [
            "build-abebooks-review-workbook",
            "--summary",
            str(summary_path),
            "--output-xlsx",
            str(output),
            "--data-dir",
            str(data_dir),
        ]
    ) == 0
    assert output.exists()
    assert "Wrote 1 AbeBooks review rows" in capsys.readouterr().out


def workbook_sheet_names(workbook):
    namespace = {"main": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
    root = ElementTree.fromstring(workbook.read("xl/workbook.xml"))
    return [sheet.attrib["name"] for sheet in root.findall("main:sheets/main:sheet", namespace)]


def xml_header_values(sheet_xml):
    namespace = {"main": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
    root = ElementTree.fromstring(sheet_xml)
    first_row = root.find("main:sheetData/main:row", namespace)
    return ["".join(cell.itertext()) for cell in first_row.findall("main:c", namespace)]

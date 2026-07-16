"""Generated collector workbook output."""

from __future__ import annotations

import zipfile
from collections import Counter
from collections.abc import Iterable, Mapping
from pathlib import Path
from xml.sax.saxutils import escape

from valuation.repositories import ACQUISITION_FIELDNAMES, COLLECTOR_REVIEW_FIELDNAMES
from valuation.research_candidates import RESEARCH_CANDIDATE_FIELDNAMES


GENERATED_WORKBOOK_NOTE = (
    "This workbook is generated output. Edits made here are not imported. "
    "Durable collector review state lives in data/collector_reviews.csv."
)

COLLECTOR_WORKBOOK_SHEETS = [
    "Summary",
    "Research Candidates",
    "Current Acquisitions",
    "Reviewed Items",
    "Metadata Gaps",
    "Collector Reviews",
]

SUMMARY_FIELDNAMES = ["section", "metric", "value", "note"]
WORKBOOK_RESEARCH_CANDIDATE_FIELDNAMES = [
    field
    for field in RESEARCH_CANDIDATE_FIELDNAMES
    if field not in {"research_signal_codes", "research_signal_summary", "research_signal_explanations"}
]
WORKBOOK_RESEARCH_CANDIDATE_FIELDNAMES.insert(
    WORKBOOK_RESEARCH_CANDIDATE_FIELDNAMES.index("acquisition_count"),
    "Research Rationale",
)
METADATA_GAP_FIELDNAMES = [
    "catalog_item_id",
    "isbn13",
    "title",
    "gap_category",
    "gap_count",
    "missing_fields",
    "metadata_source",
    "metadata_confidence",
    "lcc",
    "oclc",
]


def write_collector_workbook(
    output_path: Path,
    *,
    catalog_items: list[dict[str, str]],
    acquisitions: list[dict[str, str]],
    research_candidates: list[dict[str, str]],
    collector_reviews: list[dict[str, str]],
    metadata_rows: list[dict[str, str]],
    latest_import: str,
    run_summary: Mapping[str, str | int] | None = None,
) -> None:
    sheets = [
        (
            "Summary",
            SUMMARY_FIELDNAMES,
            summary_rows(
                catalog_items,
                acquisitions,
                research_candidates,
                collector_reviews,
                metadata_rows,
                latest_import,
                run_summary=run_summary,
            ),
        ),
        (
            "Research Candidates",
            WORKBOOK_RESEARCH_CANDIDATE_FIELDNAMES,
            workbook_research_candidate_rows(research_candidates),
        ),
        ("Current Acquisitions", ACQUISITION_FIELDNAMES, acquisitions),
        ("Reviewed Items", COLLECTOR_REVIEW_FIELDNAMES, reviewed_items(collector_reviews)),
        ("Metadata Gaps", METADATA_GAP_FIELDNAMES, metadata_gap_rows(catalog_items, metadata_rows)),
        ("Collector Reviews", COLLECTOR_REVIEW_FIELDNAMES, collector_reviews),
    ]
    write_workbook(output_path, sheets)


def summary_rows(
    catalog_items: list[dict[str, str]],
    acquisitions: list[dict[str, str]],
    research_candidates: list[dict[str, str]],
    collector_reviews: list[dict[str, str]],
    metadata_rows: list[dict[str, str]],
    latest_import: str,
    run_summary: Mapping[str, str | int] | None = None,
) -> list[dict[str, str]]:
    run_summary = run_summary or {}
    band_counts = Counter(row.get("research_priority_band", "") for row in research_candidates)
    reviewed = reviewed_items(collector_reviews)
    ignored_or_excluded = [
        row
        for row in collector_reviews
        if row.get("workflow_state", "").lower() in {"ignored", "excluded"}
        or row.get("disposition", "").lower() in {"ignore", "ignored", "exclude", "excluded"}
    ]
    metadata_gaps = metadata_gap_rows(catalog_items, metadata_rows)
    return [
        summary_row("", "Generated output note", GENERATED_WORKBOOK_NOTE),
        summary_row("Import Summary", "Import source", latest_import),
        summary_row("Import Summary", "Import date", run_summary.get("imported_at", "")),
        summary_row("Import Summary", "Amazon rows processed", run_summary.get("amazon_row_count", "")),
        summary_row("Import Summary", "Book candidates detected", run_summary.get("purchase_rows", "")),
        summary_row("Catalog", "Total catalog items", len(catalog_items)),
        summary_row("Catalog", "New catalog items from this import", run_summary.get("catalog_new", "")),
        summary_row("Acquisitions", "Total acquisitions", len(acquisitions)),
        summary_row("Acquisitions", "New acquisitions from this import", run_summary.get("acquisition_new", "")),
        summary_row("Research Assessments", "Total assessments", run_summary.get("research_durable_total", "")),
        summary_row("Research Assessments", "Reused", run_summary.get("research_reused", "")),
        summary_row("Research Assessments", "Newly generated", run_summary.get("research_created", "")),
        summary_row("Research Candidates", "Total", len(research_candidates)),
        summary_row("Research Candidates", "High", band_counts.get("high", 0)),
        summary_row("Research Candidates", "Medium", band_counts.get("medium", 0)),
        summary_row("Research Candidates", "Low", band_counts.get("low", 0)),
        summary_row("Collector Reviews", "Total review rows", len(collector_reviews)),
        summary_row("Collector Reviews", "Reviewed", len(reviewed)),
        summary_row("Collector Reviews", "Ignored", len(ignored_or_excluded)),
        summary_row("Metadata", "Metadata Gap count", len(metadata_gaps)),
        {
            "section": "Current Acquisitions",
            "metric": "Current Acquisitions note",
            "value": "Current acquisition rows",
            "note": "The pipeline currently rebuilds acquisitions from the selected full-history export.",
        },
    ]


def summary_row(section: str, metric: str, value: str | int, note: str = "") -> dict[str, str]:
    return {"section": section, "metric": metric, "value": str(value), "note": note}


def workbook_research_candidate_rows(research_candidates: Iterable[Mapping[str, str]]) -> list[dict[str, str]]:
    rows = []
    for candidate in research_candidates:
        row = {
            field: candidate.get(field, "")
            for field in WORKBOOK_RESEARCH_CANDIDATE_FIELDNAMES
            if field != "Research Rationale"
        }
        row["Research Rationale"] = candidate.get("research_signal_explanations", "")
        rows.append(row)
    return rows


def reviewed_items(collector_reviews: Iterable[Mapping[str, str]]) -> list[dict[str, str]]:
    rows = []
    for review in collector_reviews:
        if any(
            review.get(field, "")
            for field in ("workflow_state", "disposition", "priority_override", "reviewed_at", "review_notes")
        ):
            rows.append({field: review.get(field, "") for field in COLLECTOR_REVIEW_FIELDNAMES})
    return rows


def metadata_gap_rows(
    catalog_items: Iterable[Mapping[str, str]],
    metadata_rows: Iterable[Mapping[str, str]],
) -> list[dict[str, str]]:
    metadata_by_id = {
        row.get("catalog_item_id", ""): row
        for row in metadata_rows
        if row.get("catalog_item_id")
    }
    rows = []
    for item in catalog_items:
        catalog_item_id = item.get("catalog_item_id", "")
        metadata = metadata_by_id.get(catalog_item_id, {})
        merged = {
            "catalog_item_id": catalog_item_id,
            "isbn13": metadata.get("isbn13") or item.get("isbn13", ""),
            "title": metadata.get("title") or item.get("title", ""),
            "authors": metadata.get("authors") or item.get("author", ""),
            "publisher": metadata.get("publishers") or item.get("publisher", ""),
            "publication_year": first_year(metadata.get("publish_date", "")) or item.get("publication_year", ""),
            "lcc": metadata.get("lcc", ""),
            "oclc": metadata.get("oclc", ""),
            "metadata_source": metadata.get("resolution_source") or metadata.get("openlibrary_status", ""),
            "metadata_confidence": metadata.get("resolution_confidence") or item.get("match_confidence", ""),
        }
        required_fields = [
            ("title", "title"),
            ("authors", "authors"),
            ("publisher", "publisher"),
            ("publication_year", "publication_year"),
        ]
        if metadata:
            required_fields.extend(
                [
                    ("lcc", "lcc"),
                    ("oclc", "oclc"),
                    ("metadata_source", "metadata_source"),
                    ("metadata_confidence", "metadata_confidence"),
                ]
            )
        missing = [label for label, field in required_fields if not merged.get(field)]
        if missing:
            gap_categories = metadata_gap_categories(missing)
            rows.append(
                {
                    "catalog_item_id": merged["catalog_item_id"],
                    "isbn13": merged["isbn13"],
                    "title": merged["title"],
                    "gap_category": gap_category(gap_categories),
                    "gap_count": str(len(missing)),
                    "missing_fields": "; ".join(missing),
                    "metadata_source": merged["metadata_source"],
                    "metadata_confidence": merged["metadata_confidence"],
                    "lcc": merged["lcc"],
                    "oclc": merged["oclc"],
                }
            )
    return sorted(rows, key=lambda row: row.get("catalog_item_id", ""))


def metadata_gap_categories(missing_fields: Iterable[str]) -> list[str]:
    categories = []
    missing_set = set(missing_fields)
    if "lcc" in missing_set:
        categories.append("Missing Classification")
    if "oclc" in missing_set:
        categories.append("Missing Identifier")
    if {"title", "authors", "publisher", "publication_year"} & missing_set:
        categories.append("Missing Publication Metadata")
    if {"metadata_source", "metadata_confidence"} & missing_set:
        categories.append("Missing Subject Metadata")
    return categories


def gap_category(categories: list[str]) -> str:
    if len(categories) > 1:
        return "Multiple Metadata Gaps"
    return categories[0] if categories else "Metadata Gap"


def write_workbook(output_path: Path, sheets: list[tuple[str, list[str], list[dict[str, str]]]]) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", content_types_xml(len(sheets)))
        archive.writestr("_rels/.rels", ROOT_RELS_XML)
        archive.writestr("docProps/app.xml", APP_XML)
        archive.writestr("docProps/core.xml", CORE_XML)
        archive.writestr("xl/workbook.xml", workbook_xml([sheet[0] for sheet in sheets]))
        archive.writestr("xl/_rels/workbook.xml.rels", workbook_rels_xml(len(sheets)))
        archive.writestr("xl/styles.xml", STYLES_XML)
        for index, (_, fieldnames, rows) in enumerate(sheets, start=1):
            archive.writestr(
                f"xl/worksheets/sheet{index}.xml",
                sheet_xml(fieldnames, rows, selected=index == 1, wrap_fields=wrapped_text_fields(fieldnames)),
            )


def sheet_xml(
    fieldnames: list[str],
    rows: list[dict[str, str]],
    selected: bool = False,
    wrap_fields: set[str] | None = None,
) -> str:
    row_count = len(rows) + 1
    col_count = max(len(fieldnames), 1)
    dimension = f"A1:{excel_col(col_count)}{row_count}"
    widths = column_widths(fieldnames, rows)
    cols = "".join(
        f'<col min="{index}" max="{index}" width="{width}" customWidth="1"/>'
        for index, width in enumerate(widths, start=1)
    )
    tab_selected = ' tabSelected="1"' if selected else ""
    body = [row_xml(1, fieldnames, style="1")]
    for index, row in enumerate(rows, start=2):
        body.append(
            row_xml(
                index,
                [row.get(field, "") for field in fieldnames],
                fieldnames=fieldnames,
                wrap_fields=wrap_fields,
            )
        )
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        f'<dimension ref="{dimension}"/>'
        f'<sheetViews><sheetView{tab_selected} workbookViewId="0">'
        '<pane ySplit="1" topLeftCell="A2" activePane="bottomLeft" state="frozen"/>'
        '<selection pane="bottomLeft" activeCell="A2" sqref="A2"/>'
        '</sheetView></sheetViews>'
        '<sheetFormatPr defaultRowHeight="15"/>'
        f"<cols>{cols}</cols>"
        f"<sheetData>{''.join(body)}</sheetData>"
        f'<autoFilter ref="{dimension}"/>'
        "</worksheet>"
    )


def row_xml(
    row_index: int,
    values: list[str],
    style: str | None = None,
    fieldnames: list[str] | None = None,
    wrap_fields: set[str] | None = None,
) -> str:
    cells = []
    for col_index, value in enumerate(values, start=1):
        cell_ref = f"{excel_col(col_index)}{row_index}"
        text = escape(xml_safe_text(value))
        cell_style = style
        if not cell_style and fieldnames and wrap_fields and fieldnames[col_index - 1] in wrap_fields:
            cell_style = "2"
        style_attr = f' s="{cell_style}"' if cell_style else ""
        cells.append(f'<c r="{cell_ref}" t="inlineStr"{style_attr}><is><t>{text}</t></is></c>')
    return f'<row r="{row_index}">{"".join(cells)}</row>'


def wrapped_text_fields(fieldnames: list[str]) -> set[str]:
    return {
        field
        for field in fieldnames
        if field
        in {
            "Research Rationale",
            "review_notes",
            "missing_fields",
            "note",
            "possession_note",
            "review_reason",
            "meaning",
            "interpretation",
            "what_it_means",
            "source_or_derivation",
            "example_values",
            "reviewer_guidance",
        }
    }


def column_widths(fieldnames: list[str], rows: list[dict[str, str]]) -> list[int]:
    widths = []
    for field in fieldnames:
        max_len = len(field)
        for row in rows[:1000]:
            max_len = max(max_len, len(str(row.get(field, ""))))
        widths.append(min(max(max_len + 2, 10), 60))
    return widths


def excel_col(index: int) -> str:
    letters = ""
    while index:
        index, remainder = divmod(index - 1, 26)
        letters = chr(65 + remainder) + letters
    return letters


def first_year(value: str) -> str:
    for part in value.replace(",", " ").split():
        digits = "".join(character for character in part if character.isdigit())
        if len(digits) == 4:
            return digits
    return ""


def xml_safe_text(value: str) -> str:
    text = str(value or "")
    safe_chars = []
    for char in text[:32767]:
        codepoint = ord(char)
        if char in "\t\n\r" or codepoint >= 32 and not (0xD800 <= codepoint <= 0xDFFF) and codepoint not in (0xFFFE, 0xFFFF):
            safe_chars.append(char)
        else:
            safe_chars.append(" ")
    return "".join(safe_chars)


def workbook_xml(sheet_names: list[str]) -> str:
    sheets = "".join(
        f'<sheet name="{escape(name)}" sheetId="{index}" r:id="rId{index}"/>'
        for index, name in enumerate(sheet_names, start=1)
    )
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        f"<sheets>{sheets}</sheets>"
        "</workbook>"
    )


def workbook_rels_xml(sheet_count: int) -> str:
    worksheet_relationships = "".join(
        f'<Relationship Id="rId{index}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet{index}.xml"/>'
        for index in range(1, sheet_count + 1)
    )
    styles_id = sheet_count + 1
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        f"{worksheet_relationships}"
        f'<Relationship Id="rId{styles_id}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>'
        "</Relationships>"
    )


def content_types_xml(sheet_count: int) -> str:
    sheet_overrides = "".join(
        f'<Override PartName="/xl/worksheets/sheet{index}.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
        for index in range(1, sheet_count + 1)
    )
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        '<Override PartName="/docProps/app.xml" ContentType="application/vnd.openxmlformats-officedocument.extended-properties+xml"/>'
        '<Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/>'
        '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
        f"{sheet_overrides}"
        '<Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>'
        "</Types>"
    )


ROOT_RELS_XML = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>
  <Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/>
  <Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/extended-properties" Target="docProps/app.xml"/>
</Relationships>"""

APP_XML = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/extended-properties" xmlns:vt="http://schemas.openxmlformats.org/officeDocument/2006/docPropsVTypes">
  <Application>Library Valuation</Application>
</Properties>"""

CORE_XML = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:dcterms="http://purl.org/dc/terms/" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
  <dc:creator>Library Valuation</dc:creator>
  <dc:title>Collector Workbook</dc:title>
</cp:coreProperties>"""

STYLES_XML = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
  <fonts count="2"><font><sz val="11"/><name val="Calibri"/></font><font><b/><sz val="11"/><name val="Calibri"/></font></fonts>
  <fills count="2"><fill><patternFill patternType="none"/></fill><fill><patternFill patternType="gray125"/></fill></fills>
  <borders count="1"><border><left/><right/><top/><bottom/><diagonal/></border></borders>
  <cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>
  <cellXfs count="3"><xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/><xf numFmtId="0" fontId="1" fillId="0" borderId="0" xfId="0" applyFont="1"/><xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0" applyAlignment="1"><alignment wrapText="1" vertical="top"/></xf></cellXfs>
  <cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles>
</styleSheet>"""

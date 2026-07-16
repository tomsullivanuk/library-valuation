"""Static, reviewer-facing HTML report for the full-library AbeBooks baseline."""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable, Mapping
from html import escape
from pathlib import Path

from valuation.abebooks_review_workbook import POSSESSION_PRIORITY, add_acquisition_context, number_value


SECTION_SPECS = [
    ("Possible Sale", "review_for_possible_sale", [
        "title", "author", "acquired", "abebooks_range", "listing_count", "isbn_13",
        "catalog_item_id",
    ]),
    ("Manual Research", "manual_market_research_needed", [
        "title", "author", "acquired", "abebooks_range", "listing_count", "isbn_13",
        "catalog_item_id",
    ]),
    ("Edition / Condition", "review_edition_or_condition", [
        "title", "author", "acquired", "abebooks_range", "listing_count", "isbn_13",
        "catalog_item_id",
    ]),
    ("Fallback", "fallback_research_priority", [
        "title", "author", "acquired", "research_band", "isbn_13", "catalog_item_id",
    ]),
    ("Metadata Cleanup", "metadata_cleanup_needed", [
        "title", "author", "acquired", "isbn_13", "catalog_item_id",
    ]),
]

SECTION_RATIONALES = {
    "review_for_possible_sale": "Review these first. Verify physical possession, edition, condition, and current comparable listings before taking any sale action.",
    "manual_market_research_needed": "These need manual checking because the AbeBooks evidence is thin, uncertain, or unusually sensitive to listing differences.",
    "review_edition_or_condition": "Confirm the exact edition, format, condition, and match quality before relying on the displayed range.",
    "fallback_research_priority": "These lack usable AbeBooks market evidence, but Research Signals suggest they may still deserve attention.",
    "metadata_cleanup_needed": "Fix or confirm bibliographic details before relying on market lookup results.",
}

REASON_LABELS = {
    "asking_price_range_meets_initial_sale_review_threshold": "Asking-price range merits a closer sale review",
    "usable_market_evidence_below_sale_review_threshold": "Usable evidence; asking-price range is below the initial sale-review threshold",
    "uncertain_market_evidence_requires_manual_research": "Market evidence is uncertain; research current listings manually",
    "thin_market_evidence_requires_manual_research": "Too few comparable listings; research manually",
    "fragile_asking_price_evidence": "Observed range is sensitive to unusual listings",
    "ambiguous_edition_or_condition_match": "Confirm the edition and condition before relying on the range",
    "market_evidence_unavailable_high_research_priority": "No usable market evidence; high fallback research priority",
    "market_evidence_unavailable_medium_research_priority": "No usable market evidence; medium fallback research priority",
    "market_evidence_unavailable_low_research_priority": "No usable market evidence; low fallback research priority",
    "insufficient_metadata_for_market_lookup": "Add or correct bibliographic details before searching again",
}

GLOSSARY = [
    ("AbeBooks Range", "A conservative reference range derived from observed AbeBooks asking prices. It is not an appraisal or sale estimate."),
    ("Listing Count", "The number of observed AbeBooks listings summarized for the book."),
    ("Acquired", "The latest known acquisition year. Older or unknown acquisitions are marked for physical-possession verification."),
    ("Suggested Next Step", "The short instruction above each tab explains why that review queue exists and what the reviewer should do next."),
    ("Research Band", "The existing fallback Research Assessment band, used only when market evidence is unavailable."),
    ("ISBN-13", "The thirteen-digit book identifier; confirm that it matches the edition physically in hand."),
    ("Catalog Item ID", "The stable internal identifier used to reconcile the report row to catalog records."),
    ("Sort Order", "Rows are sorted first by possession priority, then by asking-price references, then by title and Catalog Item ID. Possession priority is likely present, unknown, then possibly absent. Within those groups, rows sort by likely_mid descending, likely_high descending, title alphabetically without regard to case, and Catalog Item ID as a stable tie-breaker. Possible Sale, Manual Research, and Edition / Condition generally show likely-present books first and then higher AbeBooks asking-price references. Fallback and Metadata Cleanup usually lack price ranges, so they mostly sort by possession priority and title. Possession confidence is not displayed as a separate column, but acquisition-date rules still influence sorting."),
]


def write_abebooks_review_report(
    output_path: Path,
    *,
    summary_rows: list[dict[str, str]],
    acquisitions: Iterable[Mapping[str, str]],
    summary_filename: str,
) -> None:
    """Write a portable HTML report without modifying canonical summary rows."""
    rows = add_acquisition_context(summary_rows, acquisitions)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(render_report(rows, summary_filename=summary_filename), encoding="utf-8")


def render_report(rows: list[Mapping[str, str]], *, summary_filename: str) -> str:
    recommendation_counts = Counter(row.get("review_recommendation", "") for row in rows)
    generated_at = next(
        (row.get("evidence_generated_at", "") for row in rows if row.get("evidence_generated_at")), ""
    )
    controls = "".join(
        f'<input class="tab-control" type="radio" name="review-tab" id="tab-{index}"'
        f'{" checked" if index == 0 else ""}>'
        for index in range(len(SECTION_SPECS))
    )
    panels = "".join(
        render_section(index, title, recommendation, fields, rows)
        for index, (title, recommendation, fields) in enumerate(SECTION_SPECS)
    )
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Library Review Report — AbeBooks Baseline</title><style>
:root{{--ink:#20242a;--muted:#616975;--line:#d9dde3;--accent:#244d72;--accent-soft:#eaf0f5;--warn:#fff4df}}
*{{box-sizing:border-box}} body{{font-family:system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;color:var(--ink);margin:0;background:#f5f6f8;line-height:1.45}}
main{{max-width:1500px;min-height:100vh;margin:auto;background:white;padding:2rem clamp(1rem,3vw,3rem)}} h1,h2{{color:var(--accent)}} h1{{margin:.1rem 0 0;font-size:clamp(1.7rem,3vw,2.5rem)}}
.subtitle{{margin:0 0 .35rem;color:var(--muted);font-size:1.2rem;font-weight:650}} .brief-caveat{{color:#7a4a00;font-weight:650;margin:.45rem 0 1rem}} .meta,.empty{{color:var(--muted);font-size:.88rem}}
.tabs{{display:flex;flex-wrap:wrap;align-items:flex-end;border-bottom:2px solid var(--accent);gap:.25rem;margin-top:1.2rem}} .tab-control{{position:absolute;opacity:0;pointer-events:none}}
.tab-label{{cursor:pointer;padding:.7rem .9rem;border:1px solid var(--line);border-bottom:0;border-radius:7px 7px 0 0;background:#f3f5f7;color:#39424c;font-weight:650}}
.tab-label span{{display:inline-block;min-width:1.7em;padding:.05rem .42rem;margin-left:.3rem;border-radius:999px;background:#dce3e9;text-align:center;font-size:.78rem}}
.tab-label:hover,.tab-label:focus-visible{{background:var(--accent-soft)}} .panel{{display:none;padding-top:.8rem}} .panel h2{{margin:.4rem 0 .2rem}}
#tab-0:checked~.tabs label[for="tab-0"],#tab-1:checked~.tabs label[for="tab-1"],#tab-2:checked~.tabs label[for="tab-2"],#tab-3:checked~.tabs label[for="tab-3"],#tab-4:checked~.tabs label[for="tab-4"]{{background:var(--accent);border-color:var(--accent);color:white}}
#tab-0:checked~.tabs label[for="tab-0"] span,#tab-1:checked~.tabs label[for="tab-1"] span,#tab-2:checked~.tabs label[for="tab-2"] span,#tab-3:checked~.tabs label[for="tab-3"] span,#tab-4:checked~.tabs label[for="tab-4"] span{{background:transparent;color:white;border:1px solid white}}
#tab-0:checked~.panels #panel-0,#tab-1:checked~.panels #panel-1,#tab-2:checked~.panels #panel-2,#tab-3:checked~.panels #panel-3,#tab-4:checked~.panels #panel-4{{display:block}}
.table-wrap{{overflow-x:auto}} table{{border-collapse:collapse;width:100%;font-size:.9rem;margin:.75rem 0 1.4rem}} th,td{{border-bottom:1px solid var(--line);padding:.58rem .65rem;vertical-align:top}}
th{{background:var(--accent-soft);text-align:left;position:sticky;top:0;white-space:nowrap}} td.range{{font-weight:650;white-space:nowrap}} td.count{{text-align:center}} td.acquired{{white-space:nowrap}} tr.verify{{background:#fffaf0}}
.reason-note{{display:block;color:var(--muted);font-size:.79rem;margin-top:.18rem}} .support{{margin-top:2.5rem;padding-top:1rem;border-top:1px solid var(--line)}}
.caveats{{border-left:5px solid #b16d00;background:var(--warn);padding:.7rem 1.2rem}} .caveats ul{{margin:.35rem 0}} dt{{font-weight:700;margin-top:.8rem}} dd{{margin-left:0;color:#343a40}}
code{{white-space:nowrap}} @media(max-width:700px){{.tab-label{{flex:1 1 45%;border-radius:5px;border-bottom:1px solid var(--line)}}.tabs{{border:0}}}}
@media print{{body{{background:white}} main{{max-width:none;padding:0}} .tab-control,.tab-label{{display:none}} .panel{{display:block!important;break-before:page}} .panel:first-child{{break-before:auto}} th{{position:static}}}}
</style></head><body><main>
<header><h1>Library Review Report</h1><p class="subtitle">AbeBooks Baseline</p>
<p class="brief-caveat">AbeBooks asking prices only; not appraisals or sale estimates.</p>
<section><h2>How to Use This Report</h2><ol><li>Start with Possible Sale, then work through the other tabs.</li><li>Locate each book and verify its edition, condition, dust jacket, and signatures.</li><li>For older or unknown acquisitions, confirm that the book is still physically present.</li><li>Use the AbeBooks range only as a research signal; inspect current comparable listings before deciding what to do.</li></ol></section></header>
{controls}<nav class="tabs" aria-label="Review sections">{''.join(f'<label class="tab-label" for="tab-{i}">{escape(title)} <span>{recommendation_counts[recommendation]}</span></label>' for i, (title, recommendation, _fields) in enumerate(SECTION_SPECS))}</nav>
<div class="panels">{panels}</div>
<div class="support"><section><h2>Field Guide</h2>{render_glossary()}</section>
<p class="meta">Source: <code>{escape(Path(summary_filename).name)}</code>{(' · Report generated: <code>' + escape(generated_at) + '</code>') if generated_at else ''}</p>
<section><h2>Full Caveats</h2><div class="caveats"><ul><li>This report uses observed AbeBooks asking-price evidence.</li><li>Asking prices are not appraisals.</li><li>Asking prices are not fair market value.</li><li>Asking prices are not realized sale prices or expected sale proceeds.</li><li>Physical possession should be verified before sale or further research, especially for older acquisitions.</li><li>Edition, condition, dust jacket, signature, and seller credibility may materially affect value.</li><li>eBay and other market sources are not included yet.</li></ul></div></section></div>
</main></body></html>"""


def render_section(
    index: int, title: str, recommendation: str, fields: list[str], rows: list[Mapping[str, str]]
) -> str:
    selected = [row for row in rows if row.get("review_recommendation") == recommendation]
    selected.sort(key=lambda row: (
        POSSESSION_PRIORITY.get(row.get("possession_confidence", ""), 99),
        -number_value(row.get("likely_mid", "")), -number_value(row.get("likely_high", "")),
        row.get("title", "").casefold(), row.get("catalog_item_id", ""),
    ))
    if selected:
        header = "".join(f'<th scope="col">{escape(field_label(field))}</th>' for field in fields)
        body = "".join(render_table_row(row, fields) for row in selected)
        content = f'<div class="table-wrap"><table><thead><tr>{header}</tr></thead><tbody>{body}</tbody></table></div>'
    else:
        content = '<p class="empty">No books in this section.</p>'
    rationale = SECTION_RATIONALES[recommendation]
    return f'<section class="panel" id="panel-{index}"><h2>Suggested Next Step</h2><p>{escape(rationale)}</p>{content}</section>'


def render_table_row(row: Mapping[str, str], fields: list[str]) -> str:
    cells = []
    for field in fields:
        css = {"abebooks_range": "range", "listing_count": "count", "acquired": "acquired"}.get(field, "")
        cells.append(f'<td{f" class={css!r}" if css else ""}>{format_field(field, row)}</td>')
    verify_class = ' class="verify"' if row.get("possession_confidence") != "likely_present" else ""
    return f"<tr{verify_class}>{''.join(cells)}</tr>"


def format_field(field: str, row: Mapping[str, str]) -> str:
    if field == "acquired":
        year = row.get("acquisition_year", "")
        if not year:
            return "Unknown <span class=\"reason-note\">Verify possession</span>"
        if int(year) < 2021:
            return f"{escape(year)} <span class=\"reason-note\">Verify possession</span>"
        return escape(year)
    if field == "abebooks_range":
        return format_range(row.get("likely_low", ""), row.get("likely_mid", ""), row.get("likely_high", ""))
    if field == "review_reason":
        labels = [reason_label(reason.strip()) for reason in row.get(field, "").split(";") if reason.strip()]
        return "<br>".join(escape(value) for value in labels) or "&mdash;"
    value = row.get(field, "")
    return escape(value) if value else "&mdash;"


def format_range(low: str, mid: str, high: str) -> str:
    values = [currency(value) for value in (low, mid, high) if value]
    if not values:
        return "No range available"
    if len(values) == 1:
        return values[0]
    return f"{values[0]}–{values[-1]}"


def currency(value: str) -> str:
    try:
        return f"${float(value):,.2f}"
    except (TypeError, ValueError):
        return escape(value)


def reason_label(reason: str) -> str:
    return REASON_LABELS.get(reason, reason.replace("_", " ").capitalize())


def field_label(field: str) -> str:
    return {
        "acquired": "Acquired", "abebooks_range": "AbeBooks Range", "isbn_13": "ISBN-13",
        "catalog_item_id": "Catalog Item ID", "listing_count": "Listings", "review_reason": "Suggested Next Step",
        "research_band": "Research Band",
    }.get(field, field.replace("_", " ").title())


def render_glossary() -> str:
    return "<dl>" + "".join(
        f"<dt>{escape(term)}</dt><dd>{escape(definition)}</dd>" for term, definition in GLOSSARY
    ) + "</dl>"

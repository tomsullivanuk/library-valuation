"""Deterministic self-contained Steward Workspace and Library renderer.

The renderer consumes only an already-built :class:`StewardPresentation`. It
does not read repositories, recalculate domain rules, write files, or provide
browser-side persistence.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass

from valuation.steward_presentation import (
    PRESENTATION_MODEL_VERSION,
    BookView,
    ReportView,
    StewardPresentation,
)


WORKSPACE_RENDERER_VERSION = "steward_workspace_v1"


class StewardWorkspaceRenderError(ValueError):
    """Raised when a presentation model is not compatible with this client."""


@dataclass(frozen=True)
class ExploreQuery:
    search: str = ""
    collection_scope: str = "default"
    inventory_status: str = ""
    acquisition_status: str = ""
    market_evidence_status: str = ""
    review_status: str = ""
    sort_by: str = "title"


@dataclass(frozen=True)
class WorkspaceRecommendation:
    recommendation_id: str
    queue_key: str
    entity_type: str
    entity_id: str
    entity_label: str
    suggested_action: str
    explanation: str
    confidence: str
    reason_codes: tuple[str, ...]
    primary_route: str
    evidence_routes: tuple[tuple[str, str], ...]
    source_kind: str
    advisory: bool


@dataclass(frozen=True)
class RecommendationQueue:
    queue_key: str
    title: str
    purpose: str
    recommendations: tuple[WorkspaceRecommendation, ...]


@dataclass(frozen=True)
class WorkspaceReport:
    report_key: str
    category_key: str
    name: str
    purpose: str
    audience: str
    format: str
    public_path: str
    producing_workflow: str
    status: str
    generated_at: str
    limitations: str
    content_sha256: str
    can_open: bool


@dataclass(frozen=True)
class ReportGroup:
    category_key: str
    title: str
    purpose: str
    reports: tuple[WorkspaceReport, ...]


_QUEUE_DEFINITIONS = (
    (
        "physical_identity",
        "Identify a physical copy",
        "Clarify which physical copy an inventory record represents.",
    ),
    (
        "catalog_identity",
        "Identify the correct book",
        "Connect a physical copy to the correct catalog entry.",
    ),
    (
        "audit_coverage",
        "Review what has been checked",
        "Clarify incomplete or uncertain inventory coverage.",
    ),
    (
        "location",
        "Verify locations",
        "Confirm where physical copies are believed to be.",
    ),
    (
        "newly_discovered",
        "Review newly discovered books",
        "Review books first identified through physical inventory.",
    ),
    (
        "market_evidence",
        "Review market evidence",
        "Investigate current market-evidence questions and limitations.",
    ),
    (
        "research",
        "Review research candidates",
        "Inspect books already surfaced by the research workflow.",
    ),
    (
        "steward_priority",
        "Review steward priorities",
        "Return to books explicitly prioritized by the Steward.",
    ),
    (
        "other",
        "Other review conditions",
        "Review supported conditions that do not fit another queue.",
    ),
)
_QUEUE_BY_SOURCE = {
    "inventory_physical_review": "physical_identity",
    "inventory_catalog_review": "catalog_identity",
    "inventory_audit_coverage": "audit_coverage",
    "inventory_location_review": "location",
    "inventory_newly_discovered": "newly_discovered",
    "market_evidence": "market_evidence",
    "research_candidate": "research",
    "steward_priority": "steward_priority",
}
_CONFIDENCE_ORDER = {"high": 0, "medium": 1, "low": 2, "unknown": 3, "": 4}
_REPORT_GROUPS = (
    (
        "inventory_audit",
        "Inventory and audit",
        "Reports for physical inventory, audit coverage, and identity review.",
    ),
    (
        "catalog_research",
        "Catalog and research",
        "Reports for catalog review and collection research.",
    ),
    (
        "market_evidence",
        "Market evidence",
        "Reports that summarize current market observations and limitations.",
    ),
    (
        "steward_review",
        "Steward review",
        "Reports prepared for the Steward's own review.",
    ),
    (
        "family_external",
        "Family or external communication",
        "Reports prepared to communicate collection information to other people.",
    ),
    (
        "other",
        "Other reports",
        "Prepared reports that do not fit another purpose.",
    ),
)
_REPORT_STATUS_ORDER = {
    "current": 0,
    "stale": 1,
    "missing": 2,
    "unavailable": 3,
    "incompatible": 4,
}


def build_recommendation_queues(
    presentation: StewardPresentation,
) -> tuple[RecommendationQueue, ...]:
    """Organize existing advisory records without creating new domain guidance."""

    books = {row.catalog_item_id: row for row in presentation.books}
    scope = presentation.completed_inventory
    current_observations = set(scope.unresolved_observation_ids)
    current_observations.update(h.latest_inventory_observation_id for h in presentation.holdings if h.holding_id in scope.holding_ids)
    holdings = {row.holding_id: row for row in presentation.holdings}
    observations = {
        row.inventory_observation_id: row for row in presentation.observations
    }
    seen: set[str] = set()
    grouped: dict[str, list[WorkspaceRecommendation]] = {
        key: [] for key, _, _ in _QUEUE_DEFINITIONS
    }
    for row in presentation.recommendations:
        if (presentation.completed_inventory.completed
                and row.entity_type == "catalog_item"
                and row.entity_id not in presentation.completed_inventory.catalog_item_ids):
            continue
        if scope.completed and (
            (row.entity_type == "holding" and row.entity_id not in scope.holding_ids)
            or (row.entity_type == "inventory_observation" and row.entity_id not in current_observations)
        ):
            continue
        if row.recommendation_id in seen:
            continue
        seen.add(row.recommendation_id)
        queue_key = _QUEUE_BY_SOURCE.get(row.source_kind, "other")
        entity_label = row.entity_id
        if row.entity_type == "catalog_item" and row.entity_id in books:
            entity_label = books[row.entity_id].title or row.entity_id
        elif row.entity_type == "holding" and row.entity_id in holdings:
            holding = holdings[row.entity_id]
            book = books.get(holding.catalog_item_id)
            entity_label = book.title if book and book.title else row.entity_id
        elif row.entity_type == "inventory_observation" and row.entity_id in observations:
            entity_label = observations[row.entity_id].title or row.entity_id
        grouped[queue_key].append(
            WorkspaceRecommendation(
                recommendation_id=row.recommendation_id,
                queue_key=queue_key,
                entity_type=row.entity_type,
                entity_id=row.entity_id,
                entity_label=entity_label,
                suggested_action=row.suggested_action,
                explanation=row.explanation,
                confidence=row.confidence,
                reason_codes=row.reason_codes,
                primary_route=_entity_route(row.entity_type, row.entity_id),
                evidence_routes=tuple(
                    route
                    for reference in row.evidence_references
                    if (route := _evidence_route(reference))
                ),
                source_kind=row.source_kind,
                advisory=row.advisory,
            )
        )
    queues: list[RecommendationQueue] = []
    for queue_key, title, purpose in _QUEUE_DEFINITIONS:
        rows = grouped[queue_key]
        rows.sort(
            key=lambda item: (
                _CONFIDENCE_ORDER.get(item.confidence, 3),
                item.entity_label.casefold(),
                item.suggested_action.casefold(),
                item.recommendation_id,
            )
        )
        if rows:
            queues.append(RecommendationQueue(queue_key, title, purpose, tuple(rows)))
    return tuple(queues)


def build_report_groups(
    presentation: StewardPresentation,
) -> tuple[ReportGroup, ...]:
    """Group explicitly registered reports without discovering or recalculating them."""

    grouped: dict[str, list[WorkspaceReport]] = {
        key: [] for key, _, _ in _REPORT_GROUPS
    }
    seen: set[str] = set()
    for row in presentation.reports:
        if row.report_key in seen:
            continue
        seen.add(row.report_key)
        category_key = _report_category(row)
        grouped[category_key].append(
            WorkspaceReport(
                report_key=row.report_key,
                category_key=category_key,
                name=row.name,
                purpose=row.purpose,
                audience=row.audience,
                format=row.format,
                public_path=row.public_path,
                producing_workflow=row.producing_workflow,
                status=row.status,
                generated_at=row.generated_at,
                limitations=row.limitations,
                content_sha256=row.content_sha256,
                can_open=row.status in {"current", "stale"} and bool(row.public_path),
            )
        )
    groups: list[ReportGroup] = []
    for category_key, title, purpose in _REPORT_GROUPS:
        rows = grouped[category_key]
        rows.sort(
            key=lambda item: (
                _REPORT_STATUS_ORDER.get(item.status, 5),
                item.name.casefold(),
                item.report_key,
            )
        )
        if rows:
            groups.append(ReportGroup(category_key, title, purpose, tuple(rows)))
    return tuple(groups)


def _report_category(report: ReportView) -> str:
    text = " ".join(
        (
            report.report_key,
            report.name,
            report.purpose,
            report.producing_workflow,
        )
    ).casefold()
    categories = (
        ("inventory_audit", ("inventory", "audit", "holding", "reconciliation")),
        ("market_evidence", ("market", "valuation", "price", "comparable")),
        ("catalog_research", ("catalog", "research", "bibliographic", "metadata")),
        ("family_external", ("family", "external", "dealer", "prospectus", "communication")),
        ("steward_review", ("steward", "review", "priority", "decision")),
    )
    return next(
        (
            category
            for category, keywords in categories
            if any(keyword in text for keyword in keywords)
        ),
        "other",
    )


def query_explore(
    presentation: StewardPresentation, query: ExploreQuery = ExploreQuery()
) -> tuple[str, ...]:
    """Return deterministic catalog IDs using the Explore client's semantics."""

    normalized_search = query.search.strip().casefold()
    scope = presentation.completed_inventory
    selected_scope = query.collection_scope
    if selected_scope == "default":
        selected_scope = "present" if scope.completed else "all"
    if selected_scope not in {"present", "history", "all"}:
        raise ValueError("Unknown collection scope")
    active_ids = set(scope.catalog_item_ids)
    rows = [
        book
        for book in presentation.books
        if (selected_scope == "all"
            or (selected_scope == "present" and book.catalog_item_id in active_ids)
            or (selected_scope == "history" and book.catalog_item_id not in active_ids))
        and _matches_book(presentation, book, query, normalized_search)
    ]
    rows.sort(key=lambda book: _book_sort_key(book, query.sort_by))
    return tuple(book.catalog_item_id for book in rows)


def render_steward_workspace(presentation: StewardPresentation, *, action_items=()) -> bytes:
    """Render deterministic HTML bytes without reading or writing project state."""

    if presentation.snapshot.model_version != PRESENTATION_MODEL_VERSION:
        raise StewardWorkspaceRenderError(
            "Unsupported Steward Presentation Model version "
            f"{presentation.snapshot.model_version!r}"
        )
    embedded_json = (
        presentation.to_json_bytes()
        .decode("utf-8")
        .replace("&", "\\u0026")
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
    )
    recommendation_json = json.dumps(
        [asdict(queue) for queue in build_recommendation_queues(presentation)],
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    recommendation_json = (
        recommendation_json.replace("&", "\\u0026")
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
    )
    report_json = json.dumps(
        [asdict(group) for group in build_report_groups(presentation)],
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    report_json = (
        report_json.replace("&", "\\u0026")
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
    )
    return (
        _DOCUMENT.replace("__WORKSPACE_DATA__", embedded_json)
        .replace("__WORKSPACE_RECOMMENDATIONS__", recommendation_json)
        .replace("__WORKSPACE_REPORTS__", report_json)
        .replace("__WORKSPACE_ACTIONS__", json.dumps(list(action_items), ensure_ascii=True).replace("<", "\\u003c").replace("&", "\\u0026"))
        .replace("__RENDERER_VERSION__", WORKSPACE_RENDERER_VERSION)
        .encode("utf-8")
    )


def _entity_route(entity_type: str, entity_id: str) -> str:
    prefix = {
        "catalog_item": "book",
        "holding": "holding",
        "inventory_observation": "observation",
    }.get(entity_type, "explore")
    return f"{prefix}/{entity_id}" if prefix != "explore" else prefix


def _evidence_route(reference: str) -> tuple[str, str] | None:
    kind, separator, identifier = reference.partition(":")
    if not separator or not identifier:
        return None
    route = {
        "catalog": f"book/{identifier}",
        "holding": f"holding/{identifier}",
        "observation": f"observation/{identifier}",
        "assessment": f"assessment/assessment:{identifier}",
        "market": f"market/market:{identifier}",
        "review": f"review/review:{identifier}",
    }.get(kind)
    return (reference, route) if route else None


def _matches_book(
    presentation: StewardPresentation,
    book: BookView,
    query: ExploreQuery,
    normalized_search: str,
) -> bool:
    if query.inventory_status and book.inventory_status != query.inventory_status:
        return False
    if query.acquisition_status and book.acquisition_status != query.acquisition_status:
        return False
    if (
        query.market_evidence_status
        and book.market_evidence_status != query.market_evidence_status
    ):
        return False
    if query.review_status == "needs_review" and not book.recommendation_ids:
        return False
    if query.review_status == "no_review" and book.recommendation_ids:
        return False
    if not normalized_search:
        return True
    searchable = (
        book.catalog_item_id,
        book.isbn13,
        book.isbn10,
        book.title,
        book.author,
        book.publisher,
        *book.holding_ids,
        *book.acquisition_ids,
    )
    return normalized_search in " ".join(searchable).casefold()


def _book_sort_key(book: BookView, sort_by: str) -> tuple[object, ...]:
    if sort_by == "author":
        return (book.author.casefold(), book.title.casefold(), book.catalog_item_id)
    if sort_by == "publication_year":
        year = int(book.publication_year) if book.publication_year.isdigit() else 99999
        return (year, book.title.casefold(), book.catalog_item_id)
    if sort_by == "catalog_item_id":
        return (book.catalog_item_id,)
    return (book.title.casefold(), book.author.casefold(), book.catalog_item_id)


_DOCUMENT = r"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="generator" content="__RENDERER_VERSION__">
  <title>Library Valuation — Steward Workspace</title>
  <style>
    :root {
      color-scheme: light;
      --ink: #202423;
      --muted: #66706c;
      --paper: #ffffff;
      --surface: #ffffff;
      --line: #dde2df;
      --brand: #27624d;
      --brand-dark: #1d4f3d;
      --accent: #b85c38;
      --warning: #7a4b00;
      --warning-bg: #fff2d6;
      --focus: #1b6fc2;
      --shadow: 0 1px 2px rgba(32, 37, 31, .05);
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      background: var(--paper);
      color: var(--ink);
      font-family: ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont,
        "Segoe UI", sans-serif;
      line-height: 1.5;
    }
    a { color: var(--brand-dark); }
    a:focus-visible, button:focus-visible, input:focus-visible,
    select:focus-visible, summary:focus-visible {
      outline: 3px solid var(--focus);
      outline-offset: 3px;
    }
    .skip-link {
      position: absolute;
      left: .75rem;
      top: -5rem;
      z-index: 10;
      padding: .75rem 1rem;
      background: white;
    }
    .skip-link:focus { top: .75rem; }
    header {
      background: white;
      color: var(--ink);
      padding: .6rem clamp(1rem, 4vw, 3rem);
      border-bottom: 1px solid var(--line);
    }
    .brand {
      display: flex;
      align-items: baseline;
      justify-content: space-between;
      gap: 1rem;
      max-width: 86rem;
      margin: auto;
    }
    .brand strong { font-family: Georgia, serif; font-size: 1.15rem; }
    .read-only { font-size: .88rem; }
    nav {
      position: sticky;
      top: 0;
      z-index: 5;
      display: flex;
      gap: .25rem;
      padding: .3rem clamp(1rem, 4vw, 3rem);
      overflow-x: auto;
      background: var(--surface);
      border-bottom: 1px solid var(--line);
    }
    nav a {
      padding: .65rem .85rem;
      border-radius: .35rem;
      text-decoration: none;
      white-space: nowrap;
    }
    nav a[aria-current="page"] {
      background: var(--brand);
      color: white;
    }
    nav [aria-disabled="true"] {
      padding: .65rem .85rem;
      color: var(--muted);
      white-space: nowrap;
      cursor: not-allowed;
    }
    main {
      max-width: 86rem;
      min-height: 60vh;
      margin: auto;
      padding: .65rem clamp(1rem, 4vw, 3rem) 2rem;
    }
    h1, h2, h3 { font-family: Georgia, serif; line-height: 1.2; }
    h1 { font-size: clamp(2rem, 4vw, 3.2rem); margin-top: 0; }
    .lede { max-width: 54rem; font-size: 1.12rem; color: var(--muted); }
    .grid {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(15rem, 1fr));
      gap: 1rem;
    }
    .card, .panel, details {
      background: var(--surface);
      border: 1px solid var(--line);
      border-radius: .65rem;
      box-shadow: var(--shadow);
    }
    .card { display: block; padding: 1.15rem; text-decoration: none; }
    .card:hover { border-color: var(--brand); }
    .card h2, .card h3 { margin-top: 0; color: var(--brand-dark); }
    .card-actions {
      display: flex;
      flex-wrap: wrap;
      align-items: center;
      gap: .5rem;
      margin-top: .9rem;
    }
    .panel { padding: 1.15rem; margin-block: 1rem; }
    .metric strong { display: block; font-size: 1.8rem; color: var(--brand-dark); }
    .muted { color: var(--muted); }
    .notice {
      padding: .85rem 1rem;
      margin-block: .75rem;
      border-left: .35rem solid var(--warning);
      background: var(--warning-bg);
    }
    .controls {
      display: grid;
      grid-template-columns: minmax(16rem, 2fr) repeat(4, minmax(10rem, 1fr));
      gap: .75rem;
      align-items: end;
      margin-block: 1rem;
    }
    .library-controls {
      display: grid;
      gap: .4rem;
      margin-block: 0 .45rem;
    }
    .search-row { max-width: 50rem; }
    .filter-row {
      display: grid;
      grid-template-columns: repeat(3, minmax(10rem, 1fr)) auto;
      gap: .55rem;
      align-items: end;
    }
    .library-actions {
      display: flex;
      flex-wrap: wrap;
      gap: .5rem;
      align-items: center;
      margin-block: .25rem .55rem;
      padding-block: .35rem;
      border-block: 1px solid var(--line);
    }
    .library-actions .export-action { margin-left: auto; }
    .library-actions .result-count { margin: 0; color: var(--muted); }
    .sort-menu { position: relative; }
    .sort-menu summary {
      min-width: 10rem;
      padding: .45rem .7rem;
      border: 1px solid var(--brand);
      border-radius: .35rem;
      background: white;
      color: var(--brand-dark);
      font-weight: 650;
      cursor: pointer;
      list-style: none;
    }
    .sort-menu summary::-webkit-details-marker { display: none; }
    .sort-menu > div {
      position: absolute;
      z-index: 8;
      display: grid;
      min-width: 13rem;
      padding: .35rem;
      background: white;
      border: 1px solid var(--line);
      border-radius: .35rem;
      box-shadow: 0 5px 16px rgba(32, 37, 31, .12);
    }
    .sort-menu > div button {
      border: 0;
      text-align: left;
      font-weight: 500;
    }
    button {
      min-height: 2.4rem;
      padding: .45rem .7rem;
      border: 1px solid var(--brand);
      border-radius: .35rem;
      background: white;
      color: var(--brand-dark);
      font: inherit;
      font-weight: 650;
      cursor: pointer;
    }
    button[aria-pressed="true"], button.primary {
      background: var(--brand);
      color: white;
    }
    .library-card-grid {
      display: grid;
      grid-template-columns: 1fr;
      gap: .5rem;
    }
    .library-card {
      display: grid;
      grid-template-columns: minmax(17rem, 2fr) minmax(18rem, 1.15fr);
      gap: 1rem;
      align-items: start;
      padding: .7rem .85rem;
      background: var(--surface);
      border: 1px solid var(--line);
      border-radius: .45rem;
    }
    .library-card h2 { margin: 0; font-size: 1.16rem; font-weight: 750; }
    .book-title-link { text-decoration-thickness: 1px; text-underline-offset: .18em; }
    .book-title-link:hover { color: var(--brand); text-decoration-thickness: 2px; }
    .library-card p { margin: .15rem 0; }
    .publication-line { font-size: .82rem; color: var(--muted); }
    .book-facts { display: grid; gap: .25rem; margin: 0 0 .65rem; }
    .book-facts div { display: grid; grid-template-columns: 6.2rem 1fr; gap: .4rem; }
    .book-facts dt {
      font-family: ui-sans-serif, system-ui, sans-serif;
      font-size: .7rem;
      font-weight: 650;
      letter-spacing: .02em;
      text-transform: uppercase;
      color: var(--muted);
    }
    .book-facts dd { font-size: .9rem; }
    .book-facts dt:last-of-type,
    .book-facts dd:last-of-type { opacity: .62; }
    label { display: grid; gap: .3rem; font-weight: 650; }
    input, select {
      width: 100%;
      min-height: 2.75rem;
      padding: .55rem .65rem;
      border: 1px solid #8c938b;
      border-radius: .35rem;
      background: white;
      color: var(--ink);
      font: inherit;
    }
    .result-list { display: grid; gap: .65rem; }
    .badges { display: flex; flex-wrap: wrap; gap: .35rem; }
    .badge {
      display: inline-block;
      padding: .18rem .45rem;
      border: 1px solid var(--line);
      border-radius: 999px;
      background: #f2f1eb;
      font-size: .82rem;
    }
    .badge[data-status="current"] { background: #e2f2e8; border-color: #7aa88b; }
    .badge[data-status="stale"],
    .badge[data-status="incompatible"] { background: var(--warning-bg); }
    .badge[data-status="missing"],
    .badge[data-status="unavailable"] { border-style: dashed; color: var(--muted); }
    .button-link {
      display: inline-block;
      padding: .5rem .7rem;
      border-radius: .35rem;
      background: var(--brand);
      color: white;
      text-decoration: none;
    }
    .button-link.secondary {
      background: transparent;
      color: var(--brand-dark);
      border: 1px solid var(--brand);
    }
    .detail-heading { display: flex; justify-content: space-between; gap: 1rem; }
    dl {
      display: grid;
      grid-template-columns: minmax(9rem, auto) 1fr;
      gap: .4rem 1rem;
      margin: 0;
    }
    dt { font-weight: 700; }
    dd { margin: 0; overflow-wrap: anywhere; }
    details { margin-block: .8rem; box-shadow: none; }
    summary { cursor: pointer; padding: .9rem 1rem; font-weight: 750; }
    details > div { padding: 0 1rem 1rem; }
    .link-list { display: flex; flex-wrap: wrap; gap: .5rem; padding: 0; list-style: none; }
    .empty {
      padding: 2rem;
      text-align: center;
      background: var(--surface);
      border: 1px dashed #92988f;
      border-radius: .65rem;
    }
    footer {
      max-width: 86rem;
      margin: auto;
      padding: 2rem clamp(1rem, 4vw, 3rem);
      color: var(--muted);
      border-top: 1px solid var(--line);
    }
    @media (max-width: 70rem) {
      .controls { grid-template-columns: repeat(2, minmax(12rem, 1fr)); }
      .filter-row { grid-template-columns: repeat(3, minmax(10rem, 1fr)); }
    }
    @media (max-width: 42rem) {
      .brand, .results-header, .detail-heading { display: block; }
      .controls { grid-template-columns: 1fr; }
      .filter-row { grid-template-columns: 1fr; }
      .library-card { grid-template-columns: 1fr; }
      .library-actions .export-action { margin-left: 0; }
      dl { grid-template-columns: 1fr; }
      dd { margin-bottom: .45rem; }
    }
    @media print {
      nav, .skip-link, .controls { display: none; }
      body { background: white; }
      .card, .panel, details { box-shadow: none; }
    }
  </style>
</head>
<body>
  <a class="skip-link" href="#main-content">Skip to main content</a>
  <header>
    <div class="brand">
      <strong>Library Valuation</strong>
      <span class="read-only">Your library workspace</span>
    </div>
  </header>
  <nav aria-label="Primary">
    <a href="#library" data-nav="library">Library</a>
    <span aria-disabled="true" title="Import remains in the established command workflow">Import</span>
    <a href="#actions" data-nav="actions">Action Items</a>
    <a href="#reports" data-nav="reports">Reports</a>
    <a href="#settings" data-nav="settings">Settings</a>
  </nav>
  <main id="main-content" tabindex="-1"></main>
  <footer>
    <p id="save-status">Open the local workspace to save decisions. <a href="#about">About this data</a></p>
  </footer>
  <noscript>
    <p class="notice">JavaScript is required to explore this self-contained local workspace.</p>
  </noscript>
  <script id="action-data" type="application/json">__WORKSPACE_ACTIONS__</script>
  <script id="workspace-data" type="application/json">__WORKSPACE_DATA__</script>
  <script id="recommendation-data" type="application/json">__WORKSPACE_RECOMMENDATIONS__</script>
  <script id="report-data" type="application/json">__WORKSPACE_REPORTS__</script>
  <script>
  "use strict";
  (() => {
    const DATA = JSON.parse(document.getElementById("workspace-data").textContent);
    const QUEUES = JSON.parse(document.getElementById("recommendation-data").textContent);
    const REPORT_GROUPS = JSON.parse(document.getElementById("report-data").textContent);
    let workspaceState = {connected:false, revision:0, token:"", dispositions:{}, actions:JSON.parse(document.getElementById("action-data").textContent)};
    let actionFilter = "open";
    let actionCategory = "Book checks";
    let actionLimit = 50;
    const main = document.getElementById("main-content");
    const index = {
      books: new Map(DATA.books.map(row => [row.catalog_item_id, row])),
      holdings: new Map(DATA.holdings.map(row => [row.holding_id, row])),
      acquisitions: new Map(DATA.acquisitions.map(row => [row.acquisition_reference, row])),
      assessments: new Map(DATA.assessments.map(row => [row.assessment_id, row])),
      reviews: new Map(DATA.steward_reviews.map(row => [row.review_id, row])),
      observations: new Map(DATA.observations.map(row => [row.inventory_observation_id, row])),
      decisions: new Map(DATA.decisions.map(row => [row.decision_id, row])),
      market: new Map(DATA.market_evidence.map(row => [row.market_evidence_id, row])),
      recommendations: new Map(QUEUES.flatMap(queue => queue.recommendations).map(row => [row.recommendation_id, row])),
      reports: new Map(REPORT_GROUPS.flatMap(group => group.reports).map(row => [row.report_key, row]))
    };

    function node(tag, attrs = {}, text = "") {
      const value = document.createElement(tag);
      for (const [key, attr] of Object.entries(attrs)) {
        if (key === "class") value.className = attr;
        else value.setAttribute(key, attr);
      }
      if (text !== "") value.textContent = String(text);
      return value;
    }
    function append(parent, ...children) {
      for (const child of children) if (child) parent.append(child);
      return parent;
    }
    function clear() { main.replaceChildren(); }
    function valueOrUnknown(value) { return value || "Not recorded"; }
    function human(value) {
      if (!value) return "Unknown";
      return value.replaceAll("_", " ").replace(/\b\w/g, match => match.toUpperCase());
    }
    function friendlyExplanation(value) {
      if (!value) return "No additional explanation was supplied.";
      return value.includes("_") && !value.includes(" ") ? human(value) : value;
    }
    const STATUS_LABELS = {
      current: "Current",
      stale: "May be out of date",
      missing: "Not available",
      unavailable: "Not included",
      incompatible: "Cannot be used",
      unknown: "Not known",
      not_stated: "Not stated",
      advisory: "Steward decides",
      needs_review: "Needs attention",
      no_review: "No current review item",
      verified_present: "Confirmed present",
      not_yet_audited: "Not yet checked",
      outside_audit_scope: "Outside this audit",
      possible_missing: "May be missing",
      complete_scope: "Complete for this area",
      partial_scope: "Partial for this area"
    };
    const SOURCE_LABELS = {
      catalog: "Library catalog",
      acquisitions: "Acquisition history",
      inventory: "Physical inventory",
      research_assessments: "Research priorities",
      collector_reviews: "Steward reviews",
      market_evidence: "Market research",
      research_candidates: "Research candidates",
      registered_reports: "Reports"
    };
    function statusLabel(status) {
      return STATUS_LABELS[status] || human(status);
    }
    function sourceLabel(key) {
      if (key.startsWith("report:")) return "Registered report";
      return SOURCE_LABELS[key] || human(key);
    }
    function sourceStatusExplanation(status) {
      return {
        stale: "This information was prepared from a different catalog view and is not treated as current.",
        missing: "Expected information could not be found.",
        unavailable: "This information was not included when the workspace was created.",
        incompatible: "This information could not be used safely."
      }[status] || "Review the data details for more information.";
    }
    function evidenceStatus(kind, status) {
      const labels = {
        inventory: {
          current: "Holding recorded",
          missing: "No holding recorded",
          unavailable: "Inventory not included",
          stale: "Inventory may be out of date",
          incompatible: "Inventory cannot be used"
        },
        acquisition: {
          current: "Acquisition recorded",
          missing: "No acquisition record",
          unavailable: "Acquisition history not included",
          stale: "Acquisition history may be out of date",
          incompatible: "Acquisition history cannot be used"
        },
        market: {
          current: "Current research",
          missing: "No market research",
          unavailable: "Market research not included",
          stale: "Research may be out of date",
          incompatible: "Research cannot be used"
        }
      };
      return labels[kind]?.[status] || statusLabel(status);
    }
    function badge(label, status, display = "") {
      return node("span", {class: "badge", "data-status": status || ""}, `${label}: ${display || statusLabel(status)}`);
    }
    function routeLink(label, route, className = "", ariaLabel = "") {
      const attrs = {href: `#${route}`, class: className};
      if (ariaLabel) attrs["aria-label"] = ariaLabel;
      return node("a", attrs, label);
    }
    function definitionList(values) {
      const list = node("dl");
      for (const [term, description] of values) {
        append(list, node("dt", {}, term), node("dd", {}, valueOrUnknown(description)));
      }
      return list;
    }
    function detailSection(title, content, open = false) {
      const details = node("details", open ? {open: ""} : {});
      append(details, node("summary", {}, title), append(node("div"), content));
      return details;
    }
    function linkList(entries) {
      const list = node("ul", {class: "link-list"});
      for (const [label, route] of entries) {
        append(list, append(node("li"), routeLink(label, route, "button-link")));
      }
      return list;
    }
    function heading(title, intro = "") {
      append(main, node("h1", {}, title));
      if (intro) append(main, node("p", {class: "lede"}, intro));
    }
    function sourceMessages() {
      const fragment = document.createDocumentFragment();
      const noteworthy = DATA.snapshot.sources.filter(source => source.status !== "current");
      if (!noteworthy.length && !DATA.snapshot.warnings.length) return fragment;
      append(fragment, node(
        "p",
        {class: "notice"},
        "Some information is not included or may need review. The workspace will not guess when evidence is unavailable."
      ));
      const affected = node("ul");
      for (const source of noteworthy) {
        append(affected, node(
          "li",
          {},
          `${sourceLabel(source.source_key)}: ${statusLabel(source.status)}. ${sourceStatusExplanation(source.status)}`
        ));
      }
      for (const warning of DATA.snapshot.warnings) {
        append(affected, node("li", {}, warning));
      }
      append(fragment, detailSection("What information is affected", affected));
      return fragment;
    }
    function metric(label, value, note) {
      const card = node("div", {class: "panel metric"});
      append(card, node("strong", {}, value), node("span", {}, label));
      if (note) append(card, node("p", {class: "muted"}, note));
      return card;
    }

    function renderHome() {
      clear();
      heading(
        "What would you like to accomplish today?",
        "Start with the task that matters. Detailed evidence remains available when you need it."
      );
      const choices = node("div", {class: "grid"});
      const explore = node("a", {class: "card", href: "#explore"});
      append(explore, node("h2", {}, "Explore the library"), node("p", {}, "Find a book and understand what is known about it."));
      const recommendations = node("a", {class: "card", href: "#recommendations"});
      append(recommendations, node("h2", {}, "Review what needs attention"), node("p", {}, "See evidence-backed next steps grouped by the kind of work involved."));
      const reports = node("a", {class: "card", href: "#reports"});
      append(reports, node("h2", {}, "Open reports"), node("p", {}, "Choose a prepared report and see whether it reflects this workspace."));
      append(choices, explore, recommendations, reports);
      append(main, choices, node("h2", {}, "Collection at a glance"));
      const metrics = node("div", {class: "grid"});
      append(
        metrics,
        metric("Books in the catalog", DATA.collection.catalog_item_count),
        metric("Physical copies recorded", DATA.collection.holding_count, sourceStatus("inventory")),
        metric("Purchase records", DATA.collection.acquisition_count, sourceStatus("acquisitions")),
        metric("Items needing attention", DATA.collection.recommendation_count)
      );
      append(main, metrics, node("h2", {}, "Information included in this workspace"));
      const messages = sourceMessages();
      append(main, DATA.snapshot.sources.every(source => source.status === "current") && !DATA.snapshot.warnings.length
        ? node("p", {class: "panel"}, "All included information is current for this workspace.")
        : messages);
    }

    function sourceStatus(key) {
      const source = DATA.snapshot.sources.find(row => row.source_key === key);
      return source ? statusLabel(source.status) : "Not included";
    }
    function statusOptions(field) {
      const values = [...new Set(DATA.books.map(book => book[field]).filter(Boolean))].sort();
      return values;
    }
    function selectControl(id, labelText, values, display = statusLabel) {
      const label = node("label", {for: id}, labelText);
      const select = node("select", {id});
      append(select, node("option", {value: ""}, "All"));
      for (const value of values) append(select, node("option", {value}, display(value)));
      append(label, select);
      return label;
    }
    const completedInventory = DATA.completed_inventory;
    const activeCatalogIds = new Set(completedInventory.catalog_item_ids);
    const libraryState = {
      scope: completedInventory.completed ? "present" : "",
      search: "", acquisition: "", market: "", location: "",
      sort: "title", sortDirection: 1, visibleBooks: []
    };
    function bookMatches(book, state) {
      if (state.scope === "present" && !activeCatalogIds.has(book.catalog_item_id)) return false;
      if (state.scope === "history" && activeCatalogIds.has(book.catalog_item_id)) return false;
      if (state.acquisition && book.acquisition_status !== state.acquisition) return false;
      if (state.market && book.resale_market_status !== state.market) return false;
      if (state.location === "__not_recorded__" && book.location_values.length) return false;
      if (state.location && state.location !== "__not_recorded__" && !book.location_values.includes(state.location)) return false;
      if (!state.search) return true;
      const searchable = [
        book.catalog_item_id, book.isbn13, book.isbn10, book.title, book.author,
        book.publisher, ...book.holding_ids, ...book.acquisition_ids
      ].join(" ").toLocaleLowerCase();
      return searchable.includes(state.search);
    }
    function bookCompare(sortBy, direction = 1) {
      return (left, right) => {
        if (sortBy === "estimated_value") {
          const leftLowRaw = String(left.estimated_value_sort_low ?? "").trim();
          const leftHighRaw = String(left.estimated_value_sort_high ?? "").trim();
          const rightLowRaw = String(right.estimated_value_sort_low ?? "").trim();
          const rightHighRaw = String(right.estimated_value_sort_high ?? "").trim();
          const leftLow = Number(leftLowRaw);
          const leftHigh = Number(leftHighRaw);
          const rightLow = Number(rightLowRaw);
          const rightHigh = Number(rightHighRaw);
          const leftHasValue = leftLowRaw !== "" && leftHighRaw !== ""
            && Number.isFinite(leftLow) && Number.isFinite(leftHigh);
          const rightHasValue = rightLowRaw !== "" && rightHighRaw !== ""
            && Number.isFinite(rightLow) && Number.isFinite(rightHigh);
          if (leftHasValue !== rightHasValue) return leftHasValue ? -1 : 1;
          if (leftHasValue && rightHasValue) {
            const valueOrder = direction === 1
              ? (leftLow - rightLow) || (leftHigh - rightHigh)
              : (rightHigh - leftHigh) || (rightLow - leftLow);
            return valueOrder
              || left.title.localeCompare(right.title)
              || left.catalog_item_id.localeCompare(right.catalog_item_id);
          }
          const titleOrder = left.title.localeCompare(right.title);
          return titleOrder || left.catalog_item_id.localeCompare(right.catalog_item_id);
        }
        let leftKey;
        let rightKey;
        if (sortBy === "author") {
          leftKey = [left.author, left.title, left.catalog_item_id];
          rightKey = [right.author, right.title, right.catalog_item_id];
        } else if (sortBy === "purchase_date") {
          leftKey = [left.purchase_date || "", left.title, left.catalog_item_id];
          rightKey = [right.purchase_date || "", right.title, right.catalog_item_id];
        } else if (sortBy === "location_summary" || sortBy === "disposition") {
          leftKey = [left[sortBy], left.title, left.catalog_item_id];
          rightKey = [right[sortBy], right.title, right.catalog_item_id];
        } else {
          leftKey = [left.title, left.author, left.catalog_item_id];
          rightKey = [right.title, right.author, right.catalog_item_id];
        }
        return leftKey.map(value => String(value).toLocaleLowerCase()).join("\u0000")
          .localeCompare(rightKey.map(value => String(value).toLocaleLowerCase()).join("\u0000")) * direction;
      };
    }
    function displayLocation(value) { return String(value || "").replace(/^Box\s+/i, ""); }
    function distinctTitles() {
      const ids = new Set(completedInventory.unresolved_observation_ids);
      for (const h of DATA.holdings) if (completedInventory.holding_ids.includes(h.holding_id)) ids.add(h.latest_inventory_observation_id);
      return new Set(DATA.observations.filter(o => ids.has(o.inventory_observation_id) && o.title.trim()).map(o => o.title.normalize("NFKC").toLocaleLowerCase().replace(/\s+/g," ").trim())).size;
    }
    function dispositionLabel(book) {
      const value = Object.hasOwn(workspaceState.dispositions, book.catalog_item_id) ? workspaceState.dispositions[book.catalog_item_id] : book.disposition;
      return value && value !== "information_not_included" ? human(value) : "";
    }
    async function connectWorkspace() {
      const footer = document.getElementById("save-status");
      if (!/^https?:$/.test(location.protocol)) {
        footer.replaceChildren(node("a", {href:"http://127.0.0.1:8765"}, "Open the local workspace to save decisions"), document.createTextNode(" • "), routeLink("About this data", "about"));
        return;
      }
      try {
        const response = await fetch("/api/state", {cache:"no-store"});
        if (!response.ok) throw new Error("The local saving service is unavailable.");
        workspaceState = {...await response.json(), connected:true};
        footer.replaceChildren(document.createTextNode("Decisions are saved in your project records. "), routeLink("About this data", "about"));
        renderRoute();
      } catch (error) {
        footer.textContent = "Saving is unavailable. Open the local workspace service and reload.";
      }
    }
    async function saveWorkspace(change, status, button) {
      if (!workspaceState.connected) return;
      button.disabled = true; status.textContent = "Saving…";
      try {
        const response = await fetch("/api/state", {method:"POST", headers:{"Content-Type":"application/json", "X-Workspace-Token":workspaceState.token}, body:JSON.stringify({...change, revision:workspaceState.revision})});
        const result = await response.json();
        if (!response.ok) throw new Error(result.error || "The change could not be saved.");
        workspaceState = {...result, connected:true};
        status.textContent = "Saved.";
      } catch (error) { status.textContent = error.message; }
      finally { button.disabled = !workspaceState.connected; }
    }
    function dispositionEditor(book) {
      const form = node("form");
      const label = node("label", {}, "Disposition ");
      const select = node("select", {"aria-label":"Disposition"});
      const choices = workspaceState.disposition_choices || ["", "keep", "sell", "donate", "gift", "recycle", "undecided"];
      const saved = Object.hasOwn(workspaceState.dispositions, book.catalog_item_id) ? workspaceState.dispositions[book.catalog_item_id] : book.disposition;
      if (saved && !choices.includes(saved) && saved !== "information_not_included") choices.push(saved);
      for (const value of choices) append(select, node("option", {value}, value ? human(value) : "Not assigned"));
      select.value = saved === "information_not_included" ? "" : saved;
      const button = node("button", {type:"submit"}, "Save disposition"); button.disabled = !workspaceState.connected;
      const status = node("p", {role:"status", "aria-live":"polite"}, workspaceState.connected ? "" : "Open the local workspace to save a disposition.");
      append(label, select); append(form, label, button, status);
      form.addEventListener("submit", async event => { event.preventDefault(); await saveWorkspace({kind:"disposition", id:book.catalog_item_id, value:select.value}, status, button); });
      return form;
    }
    function actionStatus(task) {
      if (task.status === "deferred" && task.deferred_until <= new Date().toLocaleDateString("en-CA", {timeZone:"America/Chicago"})) return "open";
      return task.status || "open";
    }
    function renderActions(selectedId = "") {
      clear(); heading("Action Items", "Book checks and optional research, ready when you are.");
      if (!workspaceState.connected) append(main, node("p", {class:"notice"}, "This is an offline view. Open the local workspace to save Complete, Defer, or Dismiss decisions."));
      const filter = selectControl("action-filter", "Show", ["open", "deferred", "complete", "dismissed"], human);
      filter.querySelector("select").value = actionFilter;
      filter.addEventListener("change", () => { actionFilter = filter.querySelector("select").value; renderActions(); });
      append(main, filter);
      const category = selectControl("action-category", "Task type", [...new Set(workspaceState.actions.map(t => t.category))], value => value);
      category.querySelector("select").value = actionCategory;
      category.addEventListener("change", () => { actionCategory = category.querySelector("select").value; actionLimit = 50; renderActions(); });
      append(main, category);
      const tasks = workspaceState.actions.filter(task => selectedId ? task.id === selectedId : (!actionFilter || actionStatus(task) === actionFilter) && (!actionCategory || task.category === actionCategory));
      append(main, node("p", {role:"status"}, `${tasks.length.toLocaleString()} items`));
      if (!tasks.length) append(main, node("p", {class:"empty"}, "No items in this view."));
      for (const task of tasks.slice(0, actionLimit)) {
        const card = node("article", {class:"panel"});
        append(card, node("h2", {}, task.title), node("p", {class:"muted"}, `${task.category}${task.location ? " • Location " + displayLocation(task.location) : ""} • ${human(actionStatus(task))}`), node("p", {}, task.action));
        if (task.evidence) append(card, detailSection("Recorded evidence", node("p", {}, task.evidence)));
        const noteLabel = node("label", {}, "Answer or note "); const note = node("textarea", {rows:"2", "aria-label":`Answer or note for ${task.title}`}); note.value = task.note || ""; append(noteLabel, note);
        const dateLabel = node("label", {}, "Defer until "); const until = node("input", {type:"date", "aria-label":`Defer until for ${task.title}`}); until.value = task.deferred_until || ""; append(dateLabel, until);
        append(card, noteLabel, dateLabel);
        const status = node("p", {role:"status", "aria-live":"polite"});
        const buttons = node("div", {class:"card-actions"});
        for (const [value, text] of [["complete","Complete"],["deferred","Defer"],["dismissed","Dismiss"],["open","Reopen"]]) {
          const button = node("button", {type:"button"}, text); button.disabled = !workspaceState.connected;
          button.addEventListener("click", async () => { await saveWorkspace({kind:"action", id:task.id, fingerprint:task.fingerprint, status:value, deferred_until:until.value, note:note.value}, status, button); if (status.textContent === "Saved.") { renderActions(selectedId); } });
          append(buttons, button);
        }
        append(card, buttons, status, routeLink("View book or inventory record", task.route));
        append(main, card);
      }
      if (tasks.length > actionLimit) {
        const more = node("button", {type:"button"}, "Show next 50");
        more.addEventListener("click", () => { actionLimit += 50; renderActions(selectedId); });
        append(main, more);
      }
    }
    function renderSettings() {
      clear(); heading("Settings", "Your workspace and saved decisions");
      append(main, node("p", {}, workspaceState.connected ? "Saving is connected. Dispositions and action statuses are stored with the project and survive workspace regeneration." : "Saving is disconnected. Start the local workspace service to edit decisions."), node("p", {}, "Library browsing defaults to physically inventoried books. Historical and all-record views are available under Reports."), routeLink("About this data", "about"));
    }

    function renderLibrary(reportScope = "") {
      libraryState.scope = reportScope || (completedInventory.completed ? "present" : "");
      clear();
      const controls = node("form", {class: "library-controls", role: "search"});
      const searchRow = node("div", {class: "search-row"});
      const searchLabel = node("label", {for: "library-search"}, "Search");
      const search = node("input", {
        id: "library-search",
        type: "search",
        placeholder: "Title, author, ISBN, publisher, or ID",
        autocomplete: "off"
      });
      search.value = libraryState.search;
      append(searchLabel, search);
      append(searchRow, searchLabel);
      const filterRow = node("div", {class: "filter-row"});

      const market = selectControl("market-filter", "Resale market", statusOptions("resale_market_status"), value => ({
        estimate_available: "Estimate available",
        no_reliable_estimate: "No reliable estimate",
        not_researched: "Not researched"
      })[value] || statusLabel(value));
      const knownLocations = [...new Set(DATA.books.flatMap(book => book.location_values))].sort((left, right) => left.localeCompare(right, undefined, {numeric:true}));
      const location = selectControl("location-filter", "Location", [...knownLocations, "__not_recorded__"], value => value === "__not_recorded__" ? "Not Located" : value);
      const clearButton = node("button", {type: "button"}, "Clear");
      if (completedInventory.completed) {
        if (reportScope) {
          const scope = selectControl("library-scope", "Report collection", ["present", "history"], value => ({present: "Physically inventoried books", history: "Historical records"})[value]);
          scope.querySelector("option").textContent = "All records including history";
          scope.querySelector("select").value = reportScope === "all" ? "" : reportScope;
          append(filterRow, scope);
        } else {
          append(controls, node("p", {class: "lede"}, `${completedInventory.source_copies.toLocaleString()} physical books, ${distinctTitles().toLocaleString()} distinct recorded titles`));
        }
      }
      append(filterRow, market, location, clearButton);
      append(controls, searchRow, filterRow);
      const marketSource = DATA.snapshot.sources.find(source => source.source_key === "market_evidence");
      if (marketSource && marketSource.status !== "current") {
        append(
          controls,
          node("p", {class: "muted"}, `Resale-market information: ${statusLabel(marketSource.status)}. ${sourceStatusExplanation(marketSource.status)}`)
        );
      }
      for (const [id, value] of [["market-filter", libraryState.market], ["location-filter", libraryState.location]]) controls.querySelector(`#${id}`).value = value;
      const actions = node("div", {class: "library-actions"});
      const sortNames = {
        title: "Title",
        author: "Author",
        estimated_value: "Estimated value",
        purchase_date: "Acquisition date"
      };
      const sort = node("details", {class: "sort-menu"});
      const sortSummary = node("summary");
      const sortChoices = node("div");
      for (const [value, label] of Object.entries(sortNames)) {
        const choice = node("button", {type: "button"}, label);
        choice.addEventListener("click", () => {
          libraryState.sortDirection = libraryState.sort === value
            ? -libraryState.sortDirection
            : 1;
          libraryState.sort = value;
          sort.removeAttribute("open");
          update();
        });
        append(sortChoices, choice);
      }
      append(sort, sortSummary, sortChoices);
      const exportButton = node("button", {type: "button", class: "export-action"}, "Export filtered CSV");
      const count = node("p", {id: "result-count", class: "result-count", role: "status", "aria-live": "polite"});
      append(actions, sort, count, exportButton);
      const results = node("div", {id: "library-results"});
      append(main, controls, actions, results);

      function update() {
        if (reportScope) libraryState.scope = controls.querySelector("#library-scope").value;
        libraryState.search = search.value.trim().toLocaleLowerCase();
        libraryState.acquisition = "";
        libraryState.market = controls.querySelector("#market-filter").value;
        libraryState.location = controls.querySelector("#location-filter").value;
        sortSummary.textContent = `Sort: ${sortNames[libraryState.sort]} ${libraryState.sortDirection === 1 ? "↑" : "↓"}`;
        const books = DATA.books.filter(book => bookMatches(book, libraryState)).sort(bookCompare(libraryState.sort, libraryState.sortDirection));
        libraryState.visibleBooks = books;
        results.replaceChildren();
        const filtered = Boolean(libraryState.search || libraryState.acquisition || libraryState.market || libraryState.location);
        count.textContent = `${books.length.toLocaleString()} ${books.length === 1 ? "book" : "books"}${filtered ? " match" : ""}`;
        if (!books.length) {
          append(results, node("p", {class: "empty"}, "No books match these filters."));
          return;
        }
        results.className = "library-card-grid";
        for (const book of books) append(results, bookCard(book));
      }
      controls.addEventListener("input", update);
      controls.addEventListener("change", update);
      controls.addEventListener("submit", event => event.preventDefault());
      clearButton.addEventListener("click", () => {
        search.value = "";
        for (const select of controls.querySelectorAll("select")) select.value = "";
        if (reportScope) controls.querySelector("#library-scope").value = "present";
        libraryState.sort = "title";
        libraryState.sortDirection = 1;
        update();
      });
      exportButton.addEventListener("click", exportFilteredCsv);
      update();
    }
    function bookCard(book) {
      const article = node("article", {class: "library-card"});
      const identity = node("div");
      const publication = [book.publisher, book.publication_year].filter(Boolean).join(" • ");
      const title = node("h2");
      append(
        title,
        routeLink(
          valueOrUnknown(book.title),
          `book/${encodeURIComponent(book.catalog_item_id)}`,
          "book-title-link",
          `View details for ${valueOrUnknown(book.title)}`
        )
      );
      append(
        identity,
        title,
        node("p", {class: "muted"}, valueOrUnknown(book.author))
      );
      if (publication) append(identity, node("p", {class: "publication-line"}, publication));
      if (book.isbn13 || book.isbn10) append(identity, node("p", {class: "publication-line"}, `ISBN ${book.isbn13 || book.isbn10}`));
      if (book.copy_count > 1) append(identity, node("p", {class: "publication-line"}, `${book.copy_count} copies`));
      const conclusionRows = [
        ["Location", book.location_summary],
        ["Acquired", book.purchase_summary],
        ["Disposition", dispositionLabel(book)]
      ];
      if (book.resale_market_card_summary) {
        conclusionRows.splice(2, 0, ["Resale market", book.resale_market_card_summary]);
      }
      const conclusions = definitionList(conclusionRows);
      conclusions.className = "book-facts";
      append(
        article,
        identity,
        conclusions
      );
      return article;
    }
    function csvCell(value) {
      return `"${String(value ?? "").replaceAll('"', '""')}"`;
    }
    function filteredCsvText(books) {
      const columns = [["Catalog ID", "catalog_item_id"], ["Title", "title"], ["Author", "author"], ["ISBN-13", "isbn13"], ["Publisher", "publisher"], ["Location", "location_summary"], ["Acquisition Source", "acquisition_source"], ["Acquisition Month", "acquisition_month"], ["Acquisition Count", "acquisition_count"], ["Estimate Low", "estimated_value_precise_low"], ["Estimate High", "estimated_value_precise_high"], ["Currency", "estimated_value_currency"], ["Resale Market Display", "estimated_value_display"], ["Disposition", "disposition"]];
      const lines = [columns.map(([label]) => csvCell(label)).join(",")];
      for (const book of books) lines.push(columns.map(([, key]) => csvCell(book[key])).join(","));
      return `${lines.join("\r\n")}\r\n`;
    }
    function exportFilteredCsv() {
      const url = URL.createObjectURL(new Blob([filteredCsvText(libraryState.visibleBooks)], {type: "text/csv;charset=utf-8"}));
      const link = node("a", {href: url, download: "library-filtered.csv"});
      document.body.append(link); link.click(); link.remove(); URL.revokeObjectURL(url);
    }

    function renderBook(bookId) {
      const book = index.books.get(bookId);
      if (!book) return renderNotFound("book", bookId);
      clear();
      append(main, routeLink("← Back to Library", "library"));
      const title = node("div", {class: "detail-heading"});
      append(title, node("h1", {}, valueOrUnknown(book.title)), node("span"));
      append(main, title, node("p", {class: "lede"}, valueOrUnknown(book.author)));
      if (completedInventory.completed && !activeCatalogIds.has(bookId)) append(main, node("p", {class: "notice"}, "Outside the completed physical inventory. Presumed no longer present; purchase history is preserved. An unresolved inventory entry may still match this record. No disposal has been recorded."));
      append(
        main,
        definitionList([
          ["Publisher", book.publisher],
          ["Publication year", book.publication_year],
          ["ISBN", book.isbn13 || book.isbn10]
        ])
      );
      if (book.description) {
        append(main, node("p", {class: "panel"}, book.description));
      }
      append(main, definitionList([["Location", book.location_summary], ["Copies", String(book.copy_count)], ["Acquired", book.purchase_summary], ["Resale market", book.resale_market_summary]]));
      append(main, node("h2", {}, "Disposition"), dispositionEditor(book));
      append(main, node("h2", {}, "Physical copies"));
      const currentHoldings = book.holding_ids.map(id => index.holdings.get(id)).filter(Boolean).filter(h => !completedInventory.completed || completedInventory.holding_ids.includes(h.holding_id));
      if (!currentHoldings.length) append(main, node("p", {}, "No current physical copy is linked."));
      for (const h of currentHoldings) append(main, definitionList([["Location", displayLocation(h.source_collection_label || h.current_location_id)], ["Copies", h.copies], ["Last inventoried", h.last_verified_at.slice(0, 10)]]));
      append(main, node("h2", {}, "Acquisition history"));
      if (!book.acquisition_ids.length) append(main, node("p", {}, "No acquisition record is linked. The book may have come from another source."));
      for (const ref of book.acquisition_ids) {
        const a = index.acquisitions.get(ref);
        if (a) append(main, definitionList([["Source", a.source], ["Date", a.order_date.slice(0, 10)], ["Quantity", a.quantity], ["Cost per copy", a.item_price ? `${a.currency} ${a.item_price}` : "Not recorded"], ["Subtotal", a.item_subtotal ? `${a.currency} ${a.item_subtotal}` : "Not recorded"]]));
      }
      append(main, node("h2", {}, "Research priority"));
      const assessment = index.assessments.get(book.assessment_id);
      if (assessment) append(main, definitionList([["Priority", assessment.priority_band], ["Score", assessment.priority_score], ["Why", assessment.signal_summary], ["Assessed", assessment.assessed_at.slice(0, 10)]]));
      else append(main, node("p", {}, "Not assessed."));
      append(main, node("h2", {}, "Market research"));
      const market = index.market.get(book.market_evidence_id);
      if (market) append(main, definitionList([["Estimate", book.resale_market_summary], ["Sources", market.observed_sources], ["Listings", market.listing_count], ["Confidence", market.market_confidence], ["Evidence status", market.evidence_status], ["Research date", market.generated_at.slice(0,10)], ["Notes", market.review_reason]]), node("p", {class:"muted"}, "Asking-price evidence is not a confirmed sale price."));
      else append(main, node("p", {}, "Not researched."));
      const tasks = workspaceState.actions.filter(task => task.catalog_item_id === bookId);
      if (tasks.length) {
        append(main, node("h2", {}, "Action items"));
        for (const task of tasks) append(main, routeLink(`${task.action} — ${actionStatus(task)}`, `actions/${encodeURIComponent(task.id)}`));
      }
      append(main, routeLink("About this record", `about/${encodeURIComponent(bookId)}`));
    }

    function renderHolding(holdingId) {
      const holding = index.holdings.get(holdingId);
      if (!holding) return renderNotFound("holding", holdingId);
      clear();
      const book = index.books.get(holding.catalog_item_id);
      append(main, routeLink("← Back to book", book ? `book/${encodeURIComponent(book.catalog_item_id)}` : "explore"));
      heading(book ? book.title : "Unresolved physical copy", "Details about one physical copy represented in the inventory.");
      append(main, definitionList([
        ["Inventory status", statusLabel(holding.inventory_status)],
        ["Copies represented", holding.copies],
        ["Record type", human(holding.holding_state_type)],
        ["Location", displayLocation(holding.source_collection_label || holding.current_location_id)],
        ["Collection label from source", holding.source_collection_label],
        ["Last verified", holding.last_verified_at],
        ["Area checked", holding.verification_scope],
        ["Audit coverage", statusLabel(holding.verification_completeness)]
      ]));
      const evidence = node("div");
      if (holding.observation_ids.length) append(evidence, node("h3", {}, "Inventory evidence"), linkList(holding.observation_ids.map((id, index) => [`View inventory observation ${index + 1}`, `observation/${encodeURIComponent(id)}`])));
      else append(evidence, node("p", {}, "No linked inventory observation is available."));
      append(main, detailSection("Evidence", evidence, true));
      const provenance = node("div");
      const links = [
        ...holding.physical_decision_ids.map(id => [`Physical decision ${id}`, `decision/${encodeURIComponent(id)}`]),
        ...holding.catalog_decision_ids.map(id => [`Catalog decision ${id}`, `decision/${encodeURIComponent(id)}`])
      ];
      append(provenance, definitionList([["Holding ID", holding.holding_id], ["Catalog item ID", holding.catalog_item_id]]));
      if (links.length) append(provenance, node("h3", {}, "Reconciliation decisions"), linkList(links));
      append(main, detailSection("Technical provenance", provenance));
    }

    function renderAcquisition(reference) {
      const row = index.acquisitions.get(reference);
      if (!row) return renderNotFound("acquisition", reference);
      clear();
      append(main, routeLink("← Back to book", `book/${encodeURIComponent(row.catalog_item_id)}`));
      heading("Acquisition evidence", reference);
      append(main, definitionList([
        ["Source", row.source],
        ["Order date", row.order_date],
        ["Quantity", row.quantity],
        ["Currency", row.currency],
        ["Durable acquisition ID", row.acquisition_id],
        ["Catalog item ID", row.catalog_item_id]
      ]));
      append(main, node("p", {class: "notice"}, "Acquisition history is distinct from current physical possession."));
    }
    function renderAssessment(id) {
      const row = index.assessments.get(id);
      if (!row) return renderNotFound("assessment", id);
      clear();
      append(main, routeLink("← Back to book", `book/${encodeURIComponent(row.catalog_item_id)}`));
      heading("Research assessment", id);
      append(main, definitionList([
        ["Priority band", row.priority_band],
        ["Priority score", row.priority_score],
        ["Signal count", row.signal_count],
        ["Signal summary", row.signal_summary],
        ["Assessment status", row.assessment_status],
        ["Assessed at", row.assessed_at]
      ]));
      append(main, detailSection("Technical provenance", definitionList([
        ["Model version", row.model_version],
        ["Configuration hash", row.config_hash],
        ["Acquisition snapshot hash", row.acquisition_snapshot_hash],
        ["Metadata snapshot hash", row.metadata_snapshot_hash]
      ])));
    }
    function renderReview(id) {
      const row = index.reviews.get(id);
      if (!row) return renderNotFound("review", id);
      clear();
      append(main, routeLink("← Back to book", `book/${encodeURIComponent(row.catalog_item_id)}`));
      heading("Steward-owned review", id);
      append(main, definitionList([
        ["Workflow state", row.workflow_state],
        ["Disposition hint", row.disposition],
        ["Priority override", row.priority_override],
        ["Reviewed at", row.reviewed_at],
        ["Notes", row.review_notes]
      ]));
      append(main, node("p", {class: "notice"}, "This workspace displays existing review state but does not change or save it."));
    }
    function renderMarket(id) {
      const row = index.market.get(id);
      if (!row) return renderNotFound("market evidence", id);
      clear();
      append(main, routeLink("← Back to book", `book/${encodeURIComponent(row.catalog_item_id)}`));
      heading("Market evidence summary", id);
      append(main, definitionList([
        ["Freshness", human(row.status)],
        ["Evidence status", human(row.evidence_status)],
        ["Observed sources", row.observed_sources],
        ["Listings", row.listing_count],
        ["Confidence", human(row.market_confidence)],
        ["Likely range", [row.likely_low, row.likely_mid, row.likely_high].filter(Boolean).join(" / ")],
        ["Currency", row.currency],
        ["Existing review guidance", row.review_recommendation],
        ["Reason", row.review_reason]
      ]));
      append(main, detailSection("Technical provenance", definitionList([
        ["Generated at", row.generated_at],
        ["Model version", row.model_version]
      ])));
    }
    function renderObservation(id) {
      const row = index.observations.get(id);
      if (!row) return renderNotFound("inventory observation", id);
      clear();
      heading("Inventory observation", id);
      append(main, definitionList([
        ["Title as observed", row.title],
        ["Creator as observed", row.creators],
        ["ISBN-13", row.normalized_isbn13],
        ["ISBN-10", row.normalized_isbn10],
        ["Publisher", row.publisher],
        ["Source collection", row.source_collection_label],
        ["Audit scope", row.audit_scope],
        ["Audit completeness", human(row.audit_completeness)],
        ["Observed copies", row.observed_copies],
        ["Observed at", row.observed_at]
      ]));
      const related = DATA.decisions.filter(decision => decision.inventory_observation_id === id);
      if (related.length) append(main, detailSection("Reconciliation context", linkList(related.map(row => [row.decision_id, `decision/${encodeURIComponent(row.decision_id)}`])), true));
      append(main, detailSection("Technical provenance", definitionList([
        ["Import ID", row.inventory_import_id],
        ["Parser version", row.parser_version],
        ["Normalization version", row.normalization_version],
        ["Diagnostic codes", row.diagnostic_codes.join(", ")]
      ])));
    }
    function renderDecision(id) {
      const row = index.decisions.get(id);
      if (!row) return renderNotFound("reconciliation decision", id);
      clear();
      heading(`${human(row.decision_type)} reconciliation decision`, id);
      append(main, definitionList([
        ["Outcome", human(row.outcome)],
        ["Basis", human(row.decision_basis)],
        ["Confidence", human(row.confidence)],
        ["Explanation", row.explanation],
        ["Current decision", row.is_current ? "Yes" : "No"],
        ["Origin", human(row.decision_origin)],
        ["Decision time", row.decision_timestamp]
      ]));
      const related = [];
      if (row.holding_id) related.push(["View holding", `holding/${encodeURIComponent(row.holding_id)}`]);
      if (row.catalog_item_id) related.push(["View book", `book/${encodeURIComponent(row.catalog_item_id)}`]);
      if (row.inventory_observation_id) related.push(["View observation", `observation/${encodeURIComponent(row.inventory_observation_id)}`]);
      if (related.length) append(main, detailSection("Related evidence", linkList(related), true));
      append(main, detailSection("Technical provenance", definitionList([
        ["Decision ID", row.decision_id],
        ["Model version", row.model_version],
        ["Reason codes", row.reason_codes.join(", ")],
        ["Supersedes", row.supersedes_decision_id],
        ["Candidate IDs", row.candidate_ids.join(", ")]
      ])));
    }
    function recommendationCard(row, compact = false) {
      const card = node("article", {class: "card"});
      append(card, node("h3", {}, row.suggested_action));
      append(card, node("p", {class: "muted"}, row.entity_label));
      append(card, node("p", {}, friendlyExplanation(row.explanation)));
      const statuses = node("div", {class: "badges"});
      append(statuses, badge("Confidence", row.confidence || "not_stated"));
      append(card, statuses);
      if (!compact) {
        const technical = node("div");
        append(technical, definitionList([
          ["Area", human(row.queue_key)],
          ["Evidence source", human(row.source_kind)],
          ["Reason codes", row.reason_codes.join(", ")],
          ["Recommendation reference", row.recommendation_id]
        ]));
        if (row.evidence_routes.length) {
          append(technical, node("h3", {}, "Supporting evidence"), linkList(row.evidence_routes));
        }
        append(card, detailSection("Why this is here", technical));
      }
      const actions = node("div", {class: "card-actions"});
      append(
        actions,
        routeLink("Review this item", `recommendation/${encodeURIComponent(row.recommendation_id)}`, "button-link", `Review ${row.suggested_action} for ${row.entity_label}`),
        routeLink("View related book or copy", row.primary_route, "button-link secondary", `View related book or physical copy for ${row.entity_label}`)
      );
      append(card, actions);
      return card;
    }
    function renderLegacyRecommendations() {
      clear();
      heading(
        "Recommendations",
        "Review evidence-backed next steps, grouped by the kind of attention they need."
      );
      append(main, node("p", {class: "notice"}, "Recommendations are advisory and read-only. The Steward retains every decision."));
      append(main, sourceMessages());
      if (!QUEUES.length) {
        append(main, node("p", {class: "empty"}, "No review items can be shown from the information included here. This is not necessarily an all-clear."));
        return;
      }
      const starting = QUEUES.slice(0, 3).map(queue => queue.recommendations[0]);
      append(main, node("h2", {}, "Start here"));
      append(main, node("p", {class: "muted"}, "A useful first item from up to three different areas needing attention."));
      const startingGrid = node("div", {class: "grid"});
      for (const row of starting) append(startingGrid, recommendationCard(row, true));
      append(main, startingGrid, node("h2", {}, "All areas needing attention"));
      for (const queue of QUEUES) {
        const section = node("section", {class: "panel"});
        append(
          section,
          node("h2", {}, queue.title),
          node("p", {class: "muted"}, `${queue.purpose} ${queue.recommendations.length} ${queue.recommendations.length === 1 ? "item" : "items"}.`)
        );
        const rows = node("div", {class: "result-list"});
        for (const row of queue.recommendations) append(rows, recommendationCard(row));
        append(section, rows);
        append(main, section);
      }
    }
    function renderRecommendation(id) {
      const row = index.recommendations.get(id);
      if (!row) return renderNotFound("recommendation", id);
      clear();
      append(main, routeLink("← Back to Recommendations", "recommendations"));
      heading(row.suggested_action, row.entity_label);
      append(main, node("p", {}, friendlyExplanation(row.explanation)));
      append(main, definitionList([
        ["Confidence", human(row.confidence || "not_stated")],
        ["Decision", row.advisory ? "Advisory — you decide what to do" : "Not stated"]
      ]));
      append(main, routeLink("View related book or copy", row.primary_route, "button-link"));
      if (row.evidence_routes.length) append(main, detailSection("Supporting evidence", linkList(row.evidence_routes), true));
      append(main, detailSection("Technical details", definitionList([
        ["Area", human(row.queue_key)],
        ["Evidence source", human(row.source_kind)],
        ["Reason codes", row.reason_codes.join(", ")],
        ["Recommendation reference", row.recommendation_id]
      ])));
      append(main, node("p", {class: "notice"}, "This workspace does not save acceptance, dismissal, notes, or decisions."));
    }
    function reportCard(row) {
      const card = node("article", {class: "card"});
      append(
        card,
        node("h3", {}, row.name || row.report_key),
        badge("Status", row.status, {
          current: "Ready for this workspace",
          stale: "Available, but may be out of date",
          missing: "File not found",
          incompatible: "File cannot be used safely",
          unavailable: "Not available"
        }[row.status] || statusLabel(row.status)),
        node("p", {}, row.purpose || "No purpose was supplied."),
        definitionList([
          ["Prepared for", row.audience],
          ["File type", row.format.toUpperCase()],
          ["Prepared", row.generated_at]
        ])
      );
      if (row.limitations) append(card, node("p", {class: "notice"}, `Keep in mind: ${row.limitations}`));
      const actions = node("div", {class: "card-actions"});
      append(actions, routeLink("About this report", `report/${encodeURIComponent(row.report_key)}`, "button-link secondary", `About ${row.name || row.report_key}`));
      if (row.can_open) {
        append(
          actions,
          node("a", {href: row.public_path, class: "button-link", target: "_blank", rel: "noopener", "aria-label": `Open ${row.name || row.report_key}`}, "Open report"),
          node("a", {href: row.public_path, class: "button-link secondary", download: "", "aria-label": `Download ${row.name || row.report_key}`}, "Download a copy")
        );
      } else {
        append(actions, node("span", {class: "muted"}, "This report cannot be opened from the current workspace."));
      }
      append(card, actions);
      return card;
    }
    function renderReports() {
      clear();
      append(main, node("h2", {}, "Catalog reports"), routeLink("Physically inventoried books", "catalog-report/present", "button-link"), routeLink("Historical records", "catalog-report/history", "button-link secondary"), routeLink("All records including history", "catalog-report/all", "button-link secondary"));
      heading("Reports", "Choose a prepared report by what you want to review or share.");
      append(main, node("p", {class: "notice"}, "Every report shown here was registered and checked for this workspace. Other project files are not shown automatically."));
      append(main, sourceMessages());
      if (!REPORT_GROUPS.length) {
        append(main, node("p", {class: "empty"}, "No reports were prepared for this workspace. Other reports may still be available through their established workflows."));
        return;
      }
      for (const group of REPORT_GROUPS) {
        const section = node("section", {class: "panel"});
        append(
          section,
          node("h2", {}, group.title),
          node("p", {class: "muted"}, `${group.purpose} ${group.reports.length} ${group.reports.length === 1 ? "report" : "reports"}.`)
        );
        const rows = node("div", {class: "result-list"});
        for (const row of group.reports) append(rows, reportCard(row));
        append(section, rows);
        append(main, section);
      }
    }
    function renderReport(id) {
      const row = index.reports.get(id);
      if (!row) return renderNotFound("report", id);
      clear();
      append(main, routeLink("← Back to Reports", "reports"));
      heading(row.name || row.report_key, row.purpose);
      append(main, badge("Status", row.status, {
        current: "Ready for this workspace",
        stale: "Available, but may be out of date",
        missing: "File not found",
        incompatible: "File cannot be used safely",
        unavailable: "Not available"
      }[row.status] || statusLabel(row.status)));
      if (row.status === "stale") {
        append(main, node("p", {class: "notice"}, "This report can be opened, but it was prepared from an older view of the catalog."));
      } else if (row.status === "missing") {
        append(main, node("p", {class: "notice"}, "This report was expected, but its file could not be found."));
      } else if (row.status === "incompatible") {
        append(main, node("p", {class: "notice"}, "This report's file type and filename do not agree, so it cannot be opened safely."));
      } else if (row.status === "unavailable") {
        append(main, node("p", {class: "notice"}, "This report is not available in the current workspace."));
      }
      append(main, definitionList([
        ["Prepared for", row.audience],
        ["File type", row.format.toUpperCase()],
        ["Prepared", row.generated_at],
        ["Limitations", row.limitations]
      ]));
      if (row.can_open) {
        const actions = node("div", {class: "badges"});
        append(
          actions,
          node("a", {href: row.public_path, class: "button-link", target: "_blank", rel: "noopener", "aria-label": `Open ${row.name || row.report_key}`}, "Open report"),
          node("a", {href: row.public_path, class: "button-link secondary", download: "", "aria-label": `Download ${row.name || row.report_key}`}, "Download a copy")
        );
        append(main, actions);
      }
      append(main, detailSection("Technical provenance", definitionList([
        ["Producing workflow", row.producing_workflow],
        ["Report key", row.report_key],
        ["Public path", row.public_path],
        ["Content SHA-256", row.content_sha256],
        ["Workspace snapshot", DATA.snapshot.snapshot_id]
      ])));
      append(main, node("p", {class: "notice"}, "Opening or downloading a report does not modify project state."));
    }
    function renderAbout(bookId = "") {
      clear();
      heading("About this data", "Technical context is available here without leading the Steward experience.");
      append(main, node("p", {}, "The local workspace saves dispositions and action statuses in project records. Offline HTML is read-only. Acquisition history and raw inventory evidence are preserved."));
      if (bookId) append(main, definitionList([["Catalog item ID", bookId]]));
      append(main, definitionList([
        ["Snapshot ID", DATA.snapshot.snapshot_id],
        ["Presentation model", DATA.snapshot.model_version],
        ["Generated at", DATA.snapshot.generated_at],
        ["Workspace renderer", "__RENDERER_VERSION__"]
      ]));
      const sources = node("div", {class: "grid"});
      for (const source of DATA.snapshot.sources) {
        const card = node("article", {class: "panel"});
        append(card, node("h2", {}, human(source.source_key)), badge("Status", source.status), definitionList([
          ["Authority", source.authority],
          ["Rows", String(source.row_count)],
          ["Schema or contract", source.schema_version],
          ["Generated at", source.generated_at],
          ["Explanation", source.explanation]
        ]));
        append(sources, card);
      }
      append(main, sources);
    }
    function renderNotFound(kind, id) {
      clear();
      heading("Not found", `No ${kind} matches ${id}.`);
      append(main, routeLink("Return to Library", "library", "button-link"));
    }
    function currentRoute() {
      const raw = location.hash.slice(1) || "library";
      const slash = raw.indexOf("/");
      if (slash === -1) return [raw, ""];
      return [raw.slice(0, slash), decodeURIComponent(raw.slice(slash + 1))];
    }
    function renderRoute() {
      const [route, id] = currentRoute();
      document.querySelectorAll("[data-nav]").forEach(link => {
        const active = link.dataset.nav === route
          || (["recommendations", "recommendation"].includes(route) && link.dataset.nav === "actions")
          || (["book", "holding", "acquisition", "assessment", "review", "market", "observation", "decision", "recommendation", "report"].includes(route) && link.dataset.nav === "library")
          || (["home", "explore"].includes(route) && link.dataset.nav === "library");
        if (active) link.setAttribute("aria-current", "page");
        else link.removeAttribute("aria-current");
      });
      if (route === "library" || route === "home" || route === "explore") renderLibrary();
      else if (route === "recommendations" || route === "actions") renderActions(id);
      else if (route === "settings") renderSettings();
      else if (route === "catalog-report") renderLibrary(id || "all");
      else if (route === "reports") renderReports();
      else if (route === "about") renderAbout(id);
      else if (route === "book") renderBook(id);
      else if (route === "holding") renderHolding(id);
      else if (route === "acquisition") renderAcquisition(id);
      else if (route === "assessment") renderAssessment(id);
      else if (route === "review") renderReview(id);
      else if (route === "market") renderMarket(id);
      else if (route === "observation") renderObservation(id);
      else if (route === "decision") renderDecision(id);
      else if (route === "recommendation") renderActions(id);
      else if (route === "report") renderReport(id);
      else renderNotFound("workspace route", route);
      document.title = `${main.querySelector("h1")?.textContent || "Steward Workspace"} — Library Valuation`;
      main.focus({preventScroll: true});
      window.scrollTo(0, 0);
    }
    window.addEventListener("hashchange", renderRoute);
    renderRoute();
    connectWorkspace();
  })();
  </script>
</body>
</html>
"""

"""Deterministic self-contained Steward Workspace shell and Explore renderer.

The renderer consumes only an already-built :class:`StewardPresentation`. It
does not read repositories, recalculate domain rules, write files, or provide
browser-side persistence.
"""

from __future__ import annotations

from dataclasses import dataclass

from valuation.steward_presentation import (
    PRESENTATION_MODEL_VERSION,
    BookView,
    StewardPresentation,
)


WORKSPACE_RENDERER_VERSION = "steward_workspace_v1"


class StewardWorkspaceRenderError(ValueError):
    """Raised when a presentation model is not compatible with this client."""


@dataclass(frozen=True)
class ExploreQuery:
    search: str = ""
    inventory_status: str = ""
    acquisition_status: str = ""
    market_evidence_status: str = ""
    review_status: str = ""
    sort_by: str = "title"


def query_explore(
    presentation: StewardPresentation, query: ExploreQuery = ExploreQuery()
) -> tuple[str, ...]:
    """Return deterministic catalog IDs using the Explore client's semantics."""

    normalized_search = query.search.strip().casefold()
    rows = [
        book
        for book in presentation.books
        if _matches_book(presentation, book, query, normalized_search)
    ]
    rows.sort(key=lambda book: _book_sort_key(book, query.sort_by))
    return tuple(book.catalog_item_id for book in rows)


def render_steward_workspace(presentation: StewardPresentation) -> bytes:
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
    return (
        _DOCUMENT.replace("__WORKSPACE_DATA__", embedded_json)
        .replace("__RENDERER_VERSION__", WORKSPACE_RENDERER_VERSION)
        .encode("utf-8")
    )


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
      --ink: #20251f;
      --muted: #5c655b;
      --paper: #f6f3eb;
      --surface: #fffdf7;
      --line: #d8d4c9;
      --brand: #295c48;
      --brand-dark: #173d2e;
      --accent: #b85c38;
      --warning: #7a4b00;
      --warning-bg: #fff2d6;
      --focus: #1b6fc2;
      --shadow: 0 8px 24px rgba(32, 37, 31, .08);
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
      background: var(--brand-dark);
      color: white;
      padding: 1rem clamp(1rem, 4vw, 3rem);
    }
    .brand {
      display: flex;
      align-items: baseline;
      justify-content: space-between;
      gap: 1rem;
      max-width: 86rem;
      margin: auto;
    }
    .brand strong { font-family: Georgia, serif; font-size: 1.35rem; }
    .read-only { font-size: .88rem; }
    nav {
      position: sticky;
      top: 0;
      z-index: 5;
      display: flex;
      gap: .25rem;
      padding: .5rem clamp(1rem, 4vw, 3rem);
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
    main {
      max-width: 86rem;
      min-height: 60vh;
      margin: auto;
      padding: clamp(1rem, 4vw, 3rem);
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
    .results-header {
      display: flex;
      justify-content: space-between;
      align-items: baseline;
      gap: 1rem;
      margin-block: 1.25rem .5rem;
    }
    .result-list { display: grid; gap: .65rem; }
    .book-row {
      display: grid;
      grid-template-columns: minmax(12rem, 2fr) minmax(9rem, 1fr) auto;
      gap: 1rem;
      align-items: center;
      padding: .9rem 1rem;
      background: var(--surface);
      border: 1px solid var(--line);
      border-radius: .5rem;
    }
    .book-row h3 { margin: 0; font-size: 1.05rem; }
    .badges { display: flex; flex-wrap: wrap; gap: .35rem; }
    .badge {
      display: inline-block;
      padding: .18rem .45rem;
      border: 1px solid var(--line);
      border-radius: 999px;
      background: #f2f1eb;
      font-size: .78rem;
    }
    .badge[data-status="current"] { background: #e2f2e8; border-color: #7aa88b; }
    .badge[data-status="stale"],
    .badge[data-status="incompatible"] { background: var(--warning-bg); }
    .button-link {
      display: inline-block;
      padding: .5rem .7rem;
      border-radius: .35rem;
      background: var(--brand);
      color: white;
      text-decoration: none;
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
    }
    @media (max-width: 42rem) {
      .brand, .results-header, .detail-heading { display: block; }
      .controls { grid-template-columns: 1fr; }
      .book-row { grid-template-columns: 1fr; }
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
      <span class="read-only">Read-only Steward Workspace — changes are not saved</span>
    </div>
  </header>
  <nav aria-label="Primary">
    <a href="#home" data-nav="home">Home</a>
    <a href="#explore" data-nav="explore">Explore</a>
    <a href="#recommendations" data-nav="recommendations">Recommendations</a>
    <a href="#reports" data-nav="reports">Reports</a>
    <a href="#about" data-nav="about">About this data</a>
  </nav>
  <main id="main-content" tabindex="-1"></main>
  <footer>
    <p>This generated workspace is a view of project evidence. It does not save
      decisions or modify the catalog, inventory, acquisitions, or reviews.</p>
  </footer>
  <noscript>
    <p class="notice">JavaScript is required to explore this self-contained local workspace.</p>
  </noscript>
  <script id="workspace-data" type="application/json">__WORKSPACE_DATA__</script>
  <script>
  "use strict";
  (() => {
    const DATA = JSON.parse(document.getElementById("workspace-data").textContent);
    const main = document.getElementById("main-content");
    const RESULT_LIMIT = 250;
    const index = {
      books: new Map(DATA.books.map(row => [row.catalog_item_id, row])),
      holdings: new Map(DATA.holdings.map(row => [row.holding_id, row])),
      acquisitions: new Map(DATA.acquisitions.map(row => [row.acquisition_reference, row])),
      assessments: new Map(DATA.assessments.map(row => [row.assessment_id, row])),
      reviews: new Map(DATA.steward_reviews.map(row => [row.review_id, row])),
      observations: new Map(DATA.observations.map(row => [row.inventory_observation_id, row])),
      decisions: new Map(DATA.decisions.map(row => [row.decision_id, row])),
      market: new Map(DATA.market_evidence.map(row => [row.market_evidence_id, row]))
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
    function valueOrUnknown(value) { return value || "Unknown"; }
    function human(value) {
      if (!value) return "Unknown";
      return value.replaceAll("_", " ").replace(/\b\w/g, match => match.toUpperCase());
    }
    function badge(label, status) {
      return node("span", {class: "badge", "data-status": status || ""}, `${label}: ${human(status)}`);
    }
    function routeLink(label, route, className = "") {
      return node("a", {href: `#${route}`, class: className}, label);
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
      for (const source of noteworthy) {
        append(fragment, node(
          "p",
          {class: "notice"},
          `${human(source.source_key)} — ${human(source.status)}. ${source.explanation}`
        ));
      }
      for (const warning of DATA.snapshot.warnings) {
        append(fragment, node("p", {class: "notice"}, warning));
      }
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
      append(recommendations, node("h2", {}, "Review what needs attention"), node("p", {}, "Recommendations content is planned for the next workspace increment."));
      const reports = node("a", {class: "card", href: "#reports"});
      append(reports, node("h2", {}, "Open reports"), node("p", {}, "Reports content is planned for a later workspace increment."));
      append(choices, explore, recommendations, reports);
      append(main, choices, node("h2", {}, "Collection at a glance"));
      const metrics = node("div", {class: "grid"});
      append(
        metrics,
        metric("Cataloged books", DATA.collection.catalog_item_count),
        metric("Physical holdings", DATA.collection.holding_count, sourceStatus("inventory")),
        metric("Acquisition records", DATA.collection.acquisition_count, sourceStatus("acquisitions")),
        metric("Items flagged for review", DATA.collection.recommendation_count)
      );
      append(main, metrics, node("h2", {}, "Evidence availability"), sourceMessages());
    }

    function sourceStatus(key) {
      const source = DATA.snapshot.sources.find(row => row.source_key === key);
      return source ? human(source.status) : "Unavailable";
    }
    function statusOptions(field) {
      const values = [...new Set(DATA.books.map(book => book[field]).filter(Boolean))].sort();
      return values;
    }
    function selectControl(id, labelText, values) {
      const label = node("label", {for: id}, labelText);
      const select = node("select", {id});
      append(select, node("option", {value: ""}, "All"));
      for (const value of values) append(select, node("option", {value}, human(value)));
      append(label, select);
      return label;
    }
    function bookMatches(book, state) {
      if (state.inventory && book.inventory_status !== state.inventory) return false;
      if (state.acquisition && book.acquisition_status !== state.acquisition) return false;
      if (state.market && book.market_evidence_status !== state.market) return false;
      if (state.review === "needs_review" && !book.recommendation_ids.length) return false;
      if (state.review === "no_review" && book.recommendation_ids.length) return false;
      if (!state.search) return true;
      const searchable = [
        book.catalog_item_id, book.isbn13, book.isbn10, book.title, book.author,
        book.publisher, ...book.holding_ids, ...book.acquisition_ids
      ].join(" ").toLocaleLowerCase();
      return searchable.includes(state.search);
    }
    function bookCompare(sortBy) {
      return (left, right) => {
        let leftKey;
        let rightKey;
        if (sortBy === "author") {
          leftKey = [left.author, left.title, left.catalog_item_id];
          rightKey = [right.author, right.title, right.catalog_item_id];
        } else if (sortBy === "publication_year") {
          leftKey = [left.publication_year || "99999", left.title, left.catalog_item_id];
          rightKey = [right.publication_year || "99999", right.title, right.catalog_item_id];
        } else if (sortBy === "catalog_item_id") {
          leftKey = [left.catalog_item_id];
          rightKey = [right.catalog_item_id];
        } else {
          leftKey = [left.title, left.author, left.catalog_item_id];
          rightKey = [right.title, right.author, right.catalog_item_id];
        }
        return leftKey.map(value => String(value).toLocaleLowerCase()).join("\u0000")
          .localeCompare(rightKey.map(value => String(value).toLocaleLowerCase()).join("\u0000"));
      };
    }
    function renderExplore() {
      clear();
      heading(
        "Explore the library",
        "Search cataloged books and inspect physical, acquisition, research, and market context."
      );
      append(main, sourceMessages());
      const controls = node("form", {class: "controls", role: "search"});
      const searchLabel = node("label", {for: "explore-search"}, "Search");
      const search = node("input", {
        id: "explore-search",
        type: "search",
        placeholder: "Title, creator, ISBN, publisher, or ID",
        autocomplete: "off"
      });
      append(searchLabel, search);
      const inventory = selectControl("inventory-filter", "Physical inventory", statusOptions("inventory_status"));
      const acquisition = selectControl("acquisition-filter", "Acquisition evidence", statusOptions("acquisition_status"));
      const market = selectControl("market-filter", "Market evidence", statusOptions("market_evidence_status"));
      const review = selectControl("review-filter", "Review state", ["needs_review", "no_review"]);
      const sort = selectControl("sort-order", "Sort by", ["title", "author", "publication_year", "catalog_item_id"]);
      sort.querySelector("select").value = "title";
      append(controls, searchLabel, inventory, acquisition, market, review, sort);
      const header = node("div", {class: "results-header"});
      const count = node("p", {id: "result-count", role: "status", "aria-live": "polite"});
      append(header, node("h2", {}, "Books"), count);
      const results = node("div", {class: "result-list", id: "explore-results"});
      append(main, controls, header, results);

      function update() {
        const state = {
          search: search.value.trim().toLocaleLowerCase(),
          inventory: controls.querySelector("#inventory-filter").value,
          acquisition: controls.querySelector("#acquisition-filter").value,
          market: controls.querySelector("#market-filter").value,
          review: controls.querySelector("#review-filter").value,
          sort: controls.querySelector("#sort-order").value
        };
        const books = DATA.books.filter(book => bookMatches(book, state)).sort(bookCompare(state.sort));
        results.replaceChildren();
        count.textContent = books.length > RESULT_LIMIT
          ? `${books.length} matches; showing the first ${RESULT_LIMIT}. Refine your search to narrow the list.`
          : `${books.length} ${books.length === 1 ? "book" : "books"}`;
        if (!books.length) {
          append(results, node("p", {class: "empty"}, "No books match these filters."));
          return;
        }
        for (const book of books.slice(0, RESULT_LIMIT)) append(results, bookResult(book));
      }
      controls.addEventListener("input", update);
      controls.addEventListener("change", update);
      controls.addEventListener("submit", event => event.preventDefault());
      update();
    }
    function bookResult(book) {
      const article = node("article", {class: "book-row"});
      const identity = node("div");
      append(
        identity,
        node("h3", {}, valueOrUnknown(book.title)),
        node("div", {class: "muted"}, valueOrUnknown(book.author))
      );
      const statuses = node("div", {class: "badges"});
      append(
        statuses,
        badge("Held", book.inventory_status),
        badge("Acquisition", book.acquisition_status),
        badge("Market", book.market_evidence_status)
      );
      append(article, identity, statuses, routeLink("View details", `book/${encodeURIComponent(book.catalog_item_id)}`, "button-link"));
      return article;
    }

    function renderBook(bookId) {
      const book = index.books.get(bookId);
      if (!book) return renderNotFound("book", bookId);
      clear();
      append(main, routeLink("← Back to Explore", "explore"));
      const title = node("div", {class: "detail-heading"});
      append(title, node("h1", {}, valueOrUnknown(book.title)), node("span", {class: "badge"}, book.catalog_item_id));
      append(main, title, node("p", {class: "lede"}, valueOrUnknown(book.author)));
      append(
        main,
        definitionList([
          ["Publisher", book.publisher],
          ["Publication year", book.publication_year],
          ["ISBN-13", book.isbn13],
          ["ISBN-10", book.isbn10],
          ["Physical holdings", String(book.holding_ids.length)]
        ])
      );
      const context = node("div");
      append(
        context,
        node("p", {}, "These statuses summarize available evidence; unavailable does not mean absent."),
        append(
          node("div", {class: "badges"}),
          badge("Physical inventory", book.inventory_status),
          badge("Acquisition evidence", book.acquisition_status),
          badge("Assessment", book.assessment_status),
          badge("Market evidence", book.market_evidence_status)
        )
      );
      if (book.recommendation_ids.length) {
        append(context, node("p", {class: "notice"}, `${book.recommendation_ids.length} existing review item(s) are associated with this book. Recommendation queues arrive in PR4.`));
      }
      append(main, detailSection("Steward context", context, true));

      const evidence = node("div");
      if (book.holding_ids.length) append(evidence, node("h3", {}, "Physical holdings"), linkList(book.holding_ids.map(id => [id, `holding/${encodeURIComponent(id)}`])));
      else append(evidence, node("p", {}, book.inventory_status === "unavailable" ? "Physical inventory evidence is unavailable." : "No physical holding is currently linked."));
      if (book.acquisition_ids.length) append(evidence, node("h3", {}, "Acquisitions"), linkList(book.acquisition_ids.map(id => [id, `acquisition/${encodeURIComponent(id)}`])));
      else append(evidence, node("p", {}, book.acquisition_status === "unavailable" ? "Acquisition evidence is unavailable." : "No acquisition record is linked."));
      if (book.assessment_id) append(evidence, node("h3", {}, "Research assessment"), linkList([["View assessment", `assessment/${encodeURIComponent(book.assessment_id)}`]]));
      if (book.market_evidence_id) append(evidence, node("h3", {}, "Market evidence"), linkList([["View market summary", `market/${encodeURIComponent(book.market_evidence_id)}`]]));
      if (book.steward_review_id) append(evidence, node("h3", {}, "Steward review"), linkList([["View steward review", `review/${encodeURIComponent(book.steward_review_id)}`]]));
      append(main, detailSection("Evidence", evidence));

      const provenance = node("div");
      append(
        provenance,
        definitionList([
          ["Catalog item ID", book.catalog_item_id],
          ["Workspace snapshot", DATA.snapshot.snapshot_id],
          ["Presentation model", DATA.snapshot.model_version]
        ])
      );
      append(main, detailSection("Technical provenance", provenance));
    }

    function renderHolding(holdingId) {
      const holding = index.holdings.get(holdingId);
      if (!holding) return renderNotFound("holding", holdingId);
      clear();
      const book = index.books.get(holding.catalog_item_id);
      append(main, routeLink("← Back to book", book ? `book/${encodeURIComponent(book.catalog_item_id)}` : "explore"));
      heading(book ? book.title : "Unresolved physical holding", `Physical holding ${holding.holding_id}`);
      append(main, definitionList([
        ["Inventory status", human(holding.inventory_status)],
        ["Copies represented", holding.copies],
        ["Holding type", human(holding.holding_state_type)],
        ["Current location", holding.current_location_id],
        ["Source collection", holding.source_collection_label],
        ["Last verified", holding.last_verified_at],
        ["Verification scope", holding.verification_scope],
        ["Verification completeness", human(holding.verification_completeness)]
      ]));
      const evidence = node("div");
      if (holding.observation_ids.length) append(evidence, node("h3", {}, "Inventory observations"), linkList(holding.observation_ids.map(id => [id, `observation/${encodeURIComponent(id)}`])));
      else append(evidence, node("p", {}, "No linked observation is available."));
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
    function renderPlaceholder(kind) {
      clear();
      const isRecommendations = kind === "recommendations";
      heading(
        human(kind),
        isRecommendations
          ? "This navigation destination is reserved for PR4."
          : "This navigation destination is reserved for PR5."
      );
      append(main, node(
        "p",
        {class: "empty"},
        isRecommendations
          ? `The shared model contains ${DATA.recommendations.length} advisory record(s), but this release increment does not yet present recommendation queues.`
          : `The shared model contains ${DATA.reports.length} registered report(s), but this release increment does not yet present the report catalog.`
      ));
    }
    function renderAbout() {
      clear();
      heading("About this data", "Technical context is available here without leading the Steward experience.");
      append(main, node("p", {class: "notice"}, "This workspace is read-only. It does not save filters, notes, recommendations, or decisions."));
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
      append(main, routeLink("Return to Explore", "explore", "button-link"));
    }
    function currentRoute() {
      const raw = location.hash.slice(1) || "home";
      const slash = raw.indexOf("/");
      if (slash === -1) return [raw, ""];
      return [raw.slice(0, slash), decodeURIComponent(raw.slice(slash + 1))];
    }
    function renderRoute() {
      const [route, id] = currentRoute();
      document.querySelectorAll("[data-nav]").forEach(link => {
        const active = link.dataset.nav === route
          || (["book", "holding", "acquisition", "assessment", "review", "market", "observation", "decision"].includes(route) && link.dataset.nav === "explore");
        if (active) link.setAttribute("aria-current", "page");
        else link.removeAttribute("aria-current");
      });
      if (route === "home") renderHome();
      else if (route === "explore") renderExplore();
      else if (route === "recommendations" || route === "reports") renderPlaceholder(route);
      else if (route === "about") renderAbout();
      else if (route === "book") renderBook(id);
      else if (route === "holding") renderHolding(id);
      else if (route === "acquisition") renderAcquisition(id);
      else if (route === "assessment") renderAssessment(id);
      else if (route === "review") renderReview(id);
      else if (route === "market") renderMarket(id);
      else if (route === "observation") renderObservation(id);
      else if (route === "decision") renderDecision(id);
      else renderNotFound("workspace route", route);
      document.title = `${main.querySelector("h1")?.textContent || "Steward Workspace"} — Library Valuation`;
      main.focus({preventScroll: true});
      window.scrollTo(0, 0);
    }
    window.addEventListener("hashchange", renderRoute);
    renderRoute();
  })();
  </script>
</body>
</html>
"""

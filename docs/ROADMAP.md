# Roadmap

This roadmap translates the project vision and architecture into incremental
implementation work. The intent is to grow from the current Amazon/Open Library
catalog pipeline into a reproducible valuation and decision-support system
without losing the source-of-truth discipline described in the architecture.

## Sprint 0: Completed Setup

Sprint 0 established the project foundation.

Completed outcomes:

- Repository created for the Library Valuation project.
- `README.md` documents the current Amazon catalog pipeline and Open Library
  enrichment cascade.
- `VISION.md` defines the mission, design philosophy, and long-term direction.
- `docs/ARCHITECTURE.md` documents the source-of-truth principle, current data
  flow, future architecture, generated artifact policy, and expected module
  boundaries.
- Current pipeline extracts likely physical-book purchases from Amazon exports.
- ISBN-10 values are validated and converted to ISBN-13.
- Privacy-sensitive Amazon fields are excluded from extracted book rows.
- Open Library enrichment and fallback resolution are available.
- CSV and XLSX outputs are generated for browsing and review.
- Tests cover the core ISBN, extraction, enrichment, output, and catalog-join
  behavior currently in place.

Exit condition:

- The project has a working catalog-generation baseline and enough written
  architecture to guide future changes.

## Sprint 1: Repository Structure and Valuation Foundation

Sprint 1 should prepare the codebase for valuation work while keeping behavior
stable.

Goals:

- Introduce a clearer repository structure without changing the public workflow.
- Establish durable boundaries between catalog facts, market observations,
  valuation estimates, and decisions.
- Add schema documentation for the normalized catalog and future valuation data.
- Keep generated workbooks as outputs, not canonical data.

Likely work:

- Split the current single-file pipeline only where the boundary is obvious and
  useful.
- Create modules for ISBN utilities, Amazon import, Open Library access, cache
  handling, catalog assembly, and artifact writing.
- Define initial data contracts for:
  - catalog records;
  - market observations;
  - valuation estimates;
  - decision recommendations.
- Add fixture-driven tests around any moved behavior.
- Document how new generated artifacts should be named, stored, and regenerated.

Exit condition:

- The codebase has clear module boundaries for catalog work, and valuation data
  can be added without mixing facts, estimates, and recommendations in one flat
  table.

## v0.2.0: Incremental Full-History Imports

Version 0.2.0 should make the monthly Amazon workflow incremental without using
generated workbooks as source data.

Goals:

- Treat each Amazon download as a full-history source file, not a delta.
- Introduce durable CSV state under `data/`.
- Use `catalog_item_id` as the permanent internal catalog identity.
- Preserve durable `catalog_item_id` values across runs by loading existing
  catalog state before assigning IDs.
- Never derive `catalog_item_id` values from Amazon row order, catalog sort
  order, output row order, or other run-local positions.
- Treat ISBN-13 and ISBN-10 as preferred matching attributes, not canonical
  identity.
- Keep catalog items and acquisitions clearly separated.
- Preserve existing Research Assessments for known catalog items.
- Assess only newly discovered catalog items by default.
- Keep Research Assessments separate from future market valuation.

Durable files:

- `data/import_manifest.csv`: import audit log with file hash, counts, pipeline
  version, schema version, and latest-file marker.
- `data/catalog_items.csv`: one row per distinct catalog item/book identity.
- `data/acquisitions.csv`: one row per purchase or acquisition event.
- `data/research_priority_assessments.csv`: durable assessments linked by
  `catalog_item_id`.

Cache layout:

- `cache/openlibrary/isbn.json`
- `cache/openlibrary/search.json`

Default command:

```bash
python3 library_pipeline.py update-library
```

Future re-evaluation options:

```text
--reevaluate new
--reevaluate stale
--reevaluate all
```

Exit condition:

- A monthly run from the latest full Amazon CSV or ZIP export rebuilds acquisitions, reconciles
  them to durable catalog items, evaluates only new catalog items by default,
  preserves prior assessments, records an import-manifest audit row, and
  regenerates output artifacts from `input/`, `data/`, `cache/`, and `config/`.

Implementation status:

- Done: directory conventions and centralized path handling.
- Done: durable `catalog_item_id` reuse from `data/catalog_items.csv`.
- Done: `catalog_item_id` values in generated metadata and catalog outputs.
- Done: `data/acquisitions.csv` rebuilt from the current full-history Amazon
  export and linked to durable catalog items.
- Done: `data/import_manifest.csv` append-only audit log.
- Done: persistent Research Assessments in
  `data/research_priority_assessments.csv`.
- Done: latest `.csv`/`.zip` discovery in `input/amazon`.
- Done: Amazon ZIP and compatible `Retail.OrderHistory.1` package support.
- Done: Open Library caches default to `cache/openlibrary/`.
- Done: release polish for friendly expected CLI errors and optional macOS
  completion/failure notification.
- Follow-up: because existing nonblank catalog fields are preserved, improved
  external metadata will need an explicit refresh, override, or staleness policy.
- Follow-up: acquisition IDs are deterministic hashes of available Amazon
  evidence until a richer source-item layer exposes true source line IDs.
- Not yet done: explicit `--reevaluate` modes.

## Sprint 2: Research Assessments

Sprint 2 should add Research Assessments that identify which books deserve
human research first. A Research Assessment aggregates deterministic Research
Signals into a priority score, band, and explanation. It is a prioritization
tool, not a valuation estimate.

Goals:

- Rank books by expected research value using available catalog evidence.
- Surface books likely to require manual attention.
- Keep the scoring logic transparent and adjustable.

Possible score inputs:

- Presence or absence of LCC, Dewey, LCCN, OCLC, and subjects.
- Subject area or classification signals associated with scholarly value.
- Publication age or edition ambiguity.
- Duplicate purchase or multi-volume signals.
- Title-search fallback confidence.
- Missing or weak bibliographic resolution.
- Product-name clues that indicate sets, rare editions, imports, or specialized
  academic works.

Likely durable assessment fields:

- A `research_priority_score`.
- A `research_priority_band`, such as high, medium, low, or manual review.
- Compact Research Signal codes and summaries.
- Human-readable Research Signal explanations.

Exit condition:

- The catalog can produce reproducible Research Candidates that direct human
  time toward books with the highest expected payoff or uncertainty.

Implementation status:

- Done: deterministic Research Signals.
- Done: generated Research Assessments in the preserved durable
  `data/research_priority_assessments.csv` path.
- Done: generated `output/research_candidates.csv` and `.xlsx` views that rank
  high, medium, and low Research Assessments for collector attention.
- Done: durable `data/collector_reviews.csv` state for collector-owned review
  workflow fields and notes.
- Not yet done: reviewed-item filtering or priority override behavior.

## v0.3.0: Collector Review State And Generated Workbook

Version 0.3.0 introduces collector-owned review state and a generated workbook
designed for research planning, without making the workbook the source of
truth.

Goals:

- Produce a professional Collector Workbook from normalized data.
- Separate catalog facts, Research Assessments, Collector Reviews, and generated
  outputs.
- Make review efficient for the highest-priority books.

Likely workbook sections:

- Catalog overview.
- Research Candidates sorted by priority.
- Current Acquisitions.
- Reviewed Items.
- Metadata Gaps.
- Collector Reviews.
- Summary dashboard metrics.

Policy:

- The workbook is generated.
- Manual workbook edits are not durable unless imported through a documented
  workflow.
- Any import workflow must preserve provenance and avoid overwriting catalog
  facts with opinions.

Exit condition:

- A user can regenerate a Collector Workbook from project data and use it to
  guide review without hand-editing the canonical catalog.

## Sprint 4: Top-25 Market Research Workflow

Sprint 4 should create a focused workflow for researching the highest-priority
books first.

Goals:

- Select the top 25 Research Candidates.
- Capture comparable market evidence in a structured way.
- Produce initial valuation estimates backed by observed data.
- Preserve source URLs, capture dates, condition notes, and confidence.

Market sources may include:

- AbeBooks.
- eBay completed sales.
- Bookfinder.
- Amazon Used.
- Other reputable secondary-market sources.

Likely work:

- Define the market-observation schema.
- Add a structured input path for manual market research.
- Add validation for required evidence fields.
- Generate a top-25 research workbook or worksheet.
- Produce first-pass retail and dealer-value estimates from captured evidence.
- Keep heuristic scoring separate from evidence-based valuation.

Exit condition:

- The project can guide focused research on the top 25 books and turn that
  research into transparent, evidence-backed valuation estimates.

## Later

Later work should build on the catalog, research, and valuation foundations
rather than replacing them.

Dealer prospectus:

- Generate professional summaries for dealers or specialist buyers.
- Group books by subject, collection, author, or classification range.
- Include evidence-backed highlights and clear condition caveats.
- Keep dealer-facing outputs generated from normalized project data.

Automated pricing:

- Add structured integrations or assisted workflows for market data collection.
- Track source, date, condition, listing type, and sale status.
- Distinguish asking prices from completed sales.
- Compute valuation estimates with confidence and rationale.
- Support recalculation when pricing strategy or market data changes.

Collection analytics:

- Analyze subject concentration by LCC, Dewey, author, publisher, or period.
- Identify collection-level sale opportunities.
- Highlight duplicate, incomplete, or multi-volume sets.
- Produce estate, donation, retention, and family-review reports.

Long-term exit condition:

- The system helps users make informed selling, donating, and retention
  decisions from reproducible data, transparent evidence, and generated
  decision-support artifacts.

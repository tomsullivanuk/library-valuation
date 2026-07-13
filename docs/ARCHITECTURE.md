# Architecture

## Project Purpose

Library Valuation is an open, reproducible system for cataloging, analyzing,
valuing, and supporting decisions about scholarly and personal libraries.

The current implementation focuses on building a privacy-conscious book catalog
from Amazon order-history exports and enriching those rows with bibliographic
metadata. The long-term project is broader: help identify which books deserve
individual research, which books may be sold individually or as collections,
which books are unlikely to justify resale effort, and which books should be
retained for historical or family reasons.

The project should preserve evidence and minimize manual effort. Human judgment
belongs in review and decision points, not in hand-editing generated outputs.

## Current Architecture

The current system is a compact Python command-line pipeline implemented in
`library_pipeline.py`, with tests in `tests/test_library_pipeline.py`.

The pipeline currently handles:

- Amazon order-history CSV ingestion.
- ASIN classification.
- ISBN-10 validation and ISBN-13 conversion.
- Extraction of likely physical-book purchases.
- Privacy filtering of Amazon export fields.
- Open Library lookup by ISBN.
- Open Library fallback resolution by ISBN-10 and title search.
- Local JSON caching of Open Library ISBN and search responses.
- Generation of CSV and XLSX artifacts.
- Basic enrichment coverage analysis.

At this stage, most responsibilities live in one file. That is acceptable for
the current scale, but the code already contains natural boundaries that should
be separated as the project grows.

## Current Data Flow

The current monthly workflow starts with a fresh Amazon order-history export.

```text
Amazon order-history CSV
        |
        v
ASIN classification and ISBN validation
        |
        v
Book purchase extraction
        |
        v
Unique ISBN grouping
        |
        v
Open Library enrichment
        |
        v
Fallback resolution for missing records
        |
        v
Normalized metadata and catalog outputs
        |
        v
CSV/XLSX artifacts for browsing and review
```

The main `update-library` command writes:

- `book_purchases.csv` and `book_purchases.xlsx`: one row per Amazon book line
  item.
- `book_metadata.csv` and `book_metadata.xlsx`: one row per unique ISBN-13.
- `library_catalog.csv` and `library_catalog.xlsx`: purchase rows joined to
  metadata for browsing.
- `research_candidates.csv` and `research_candidates.xlsx`: generated
  collector-facing candidate list.
- `collector_workbook.xlsx`: generated dashboard workbook with Summary,
  Research Candidates, Current Acquisitions, Reviewed Items, Metadata Gaps, and
  Collector Reviews sheets.

The workflow also reuses:

- `openlibrary_cache.json` for ISBN lookups.
- `openlibrary_search_cache.json` for title-search lookups.

These caches reduce repeated external requests and help preserve reproducible
results for a given run.

## v0.2.0 Incremental Workflow

Version 0.2.0 changes the monthly workflow from a generated-output-only
pipeline into an incremental, file-backed catalog workflow.

Default command:

```bash
python3 library_pipeline.py update-library
```

Default behavior:

- Load previous durable catalog state.
- Find the latest full Amazon `.csv` or `.zip` export in `input/amazon`.
- Rebuild current acquisitions from the latest full-history file.
- Reconcile acquisitions to `catalog_items` using ISBN-first matching.
- Update catalog metadata from source data and Open Library cache lookups.
- Load existing Research Assessments.
- Assess only newly discovered catalog items by default.
- Preserve prior assessments for known items.
- Record an import-manifest row.
- Regenerate output files from durable state.

Research Assessment re-evaluation remains future work and should be explicit:

```text
--reevaluate new       # default
--reevaluate stale
--reevaluate all
```

Version fields:

- `pipeline_version = 0.2.0`
- `schema_version = 1`

The pipeline version may change frequently. The schema version changes only
when durable CSV layouts become incompatible.

### Durable State Layout

`input/` contains user-provided source files. For v0.2.0, this means full Amazon
Order History CSV or ZIP downloads under `input/amazon/`.

`data/` contains durable project state:

- `import_manifest.csv`: audit log of processed imports.
- `catalog_items.csv`: one row per distinct catalog item/book identity.
- `acquisitions.csv`: one row per purchase or acquisition event.
- `research_priority_assessments.csv`: latest durable Research Assessment per
  catalog item.
- `collector_reviews.csv`: collector-owned workflow state and lightweight
  review notes, linked by `catalog_item_id`.

`cache/` contains provider-specific external lookup caches:

- `openlibrary/isbn.json`
- `openlibrary/search.json`

`config/` contains scoring and classification configuration.

`output/` contains generated artifacts only. Prior generated Excel or CSV files
must not be read as source data.

Current generated outputs include:

- `book_purchases.csv` / `.xlsx`: normalized book-like source rows from the
  latest Amazon export.
- `book_metadata.csv` / `.xlsx`: current import metadata and enrichment view.
- `library_catalog.csv` / `.xlsx`: catalog-facing acquisition view.
- `research_candidates.csv` / `.xlsx`: collector-facing Research Candidates
  generated from current catalog items, acquisitions, metadata, and Research
  Assessments.
- `collector_workbook.xlsx`: generated multi-sheet collector workbook over
  current durable state and generated Research Candidate rows. Its Summary
  sheet is a collector dashboard, and workbook edits are not imported.

### Identity And Matching

`catalog_item_id` is the permanent internal identity for catalog records. ISBNs
are matching attributes and useful human-readable columns, but they are not the
canonical identity.

Current durable behavior: `catalog_item_id` values are stable across runs when
an item can be matched to `data/catalog_items.csv`. The pipeline loads existing
IDs and assigns new IDs only after matching fails. IDs must not be regenerated
from Amazon row order, catalog sort order, output row order, or any other
run-local position.

Import matching should use the strongest available evidence in this order where
practical:

1. ISBN-13.
2. ISBN-10.
3. Source fingerprint.
4. Normalized title plus author fallback.

The current implementation supports ISBN-13, ISBN-10, and normalized title plus
author matching. `source_fingerprint` is reserved for the future
source-item/acquisition layer and is currently written blank.

Once a source record is matched, its acquisition row references the existing or
newly created `catalog_item_id`. Other durable files also reference
`catalog_item_id`.

`data/catalog_items.csv` represents the current catalog-level identity and
metadata for a book. `data/acquisitions.csv` represents source-linked purchase
or acquisition facts. Acquisition rows should avoid duplicating book metadata
except where needed for source provenance or reconciliation.

Current acquisition IDs are deterministic `AMZ-...` hashes derived from
available Amazon evidence: source, order ID, ASIN, order date, source title,
item price, and quantity. Because the current normalized Amazon row does not
carry a true Amazon line-item ID, truly identical same-order line items may
collide until a richer source-item layer exists.

### Metadata Changes

Open Library or another provider may later return better metadata for a known
item. The catalog may accept better derived metadata while preserving the same
`catalog_item_id`.

If scoring-relevant metadata changes, the existing Research Assessment
should be marked stale rather than silently replaced during the default monthly
run. The user can then choose `--reevaluate stale` or `--reevaluate all`.

## v0.4.0 Market Validation Architecture

Version 0.4.0 adds opt-in research workflows around the existing durable
catalog without changing the monthly import path:

```text
Durable catalog and Research Assessments
        |
        v
Stratified validation samples
        |
        v
AbeBooks market observations and diagnostics
        |
        v
Coverage, score-band, and signal analysis
        |
        v
Non-production calibration simulation and decision record
```

Market observations are external facts about listings and lookup attempts.
Analysis rows and simulated scores are derived generated artifacts. Neither is
a valuation estimate, recommendation, or durable Research Assessment.

All v0.4.0 experiment artifacts are written under `output/` and remain ignored.
The workflows do not modify `config/research_signals.yml`, production scoring,
persisted assessments, durable catalog or acquisition data, or
`update-library`. AbeBooks is an experimental first source; its asking prices do
not represent completed sales or complete market truth.

The v0.4.0 decision preserves the current single Research Score. Future model
design may separate market likelihood from research effort, but no new score or
schema is introduced in this release.

## Source-of-Truth Principle

The durable state under `data/`, together with user source files under
`input/`, provider caches under `cache/`, and configuration under `config/`, is
the source of truth.

Generated spreadsheets, reports, dashboards, and review workbooks are outputs.
They should not become the canonical data store, and the catalog should not be
reshaped just to make a report convenient. Edits made in generated workbooks
are not imported; durable collector-owned review state lives in
`data/collector_reviews.csv`.

If a downstream artifact needs a different layout, that layout should be created
by a transformation step. The underlying catalog should remain stable,
normalized, and reproducible from source data plus documented enrichment inputs.

## Data Separation

The system should keep distinct categories of information separate:

- Catalog data: bibliographic and acquisition facts such as ISBN, title,
  authors, publishers, classifications, purchase date, and source identifiers.
- Research Assessment: a generated planning assessment that answers whether a
  book should be researched.
- Research signals: deterministic, explainable evidence points that feed
  Research Assessments and Research Candidates.
- Research Candidates: generated collector-facing output rows that rank catalog
  items by Research Assessment band, score, signal count, age, title, and
  stable catalog identity.
- Collector Reviews: human-owned workflow state, disposition hints, priority
  overrides, and notes. Automated processing may read this state for generated
  views, but must not overwrite it.
- Market research: observed listings, completed sales, dealer notes, source
  URLs, capture dates, condition observations, and comparable-copy evidence.
- Valuation estimates: derived retail estimates, dealer-value estimates,
  confidence levels, and rationale.
- Decisions: recommendations such as sell individually, group by subject,
  donate, retain, research further, or ignore for resale.

This separation matters because each layer changes at a different pace.
Bibliographic facts should remain stable. Market observations can expire.
Valuation estimates may change as pricing strategy improves. Decisions may
depend on family goals, time constraints, and risk tolerance.

The Market Intelligence subsystem is the future boundary for collecting
external market observations. Its architecture is described in
[Market Intelligence](MARKET_INTELLIGENCE.md). It should gather evidence for
later valuation components without making appraisal claims or final
recommendations itself.

Research Assessment must not be mixed with future market valuation. Research
Assessment answers "Should this book be researched?" Market valuation answers
"What is this book likely worth?" A future durable file such as
`data/market_valuations.csv` should be separate from
`data/research_priority_assessments.csv`.

## Planned Future Architecture

The long-term architecture should evolve from a catalog generator into a
decision-support system.

```text
Book Sources
      |
      v
Normalized Library Catalog
      |
      v
Analysis Engine
      |
      v
Decision Engine
      |
      +-- Valuation Workbook
      +-- Research Candidates
      +-- Dealer Prospectus
      +-- Collection Analytics
      +-- Estate Reports
      +-- Family Retention Lists
```

Future book sources may include Amazon exports, manual intake sheets, barcode
scans, estate inventories, dealer-provided lists, or other catalog exports.

Future enrichment and valuation sources may include Open Library, Library of
Congress, OCLC/WorldCat, AbeBooks, eBay completed sales, Bookfinder, Amazon
Used, and other reputable secondary-market data. Each source should retain
provenance so that users can understand where facts and estimates came from.

## Expected Module Boundaries

The current single-file pipeline should eventually be split along responsibility
boundaries. Expected modules include:

- Source importers: read Amazon exports and future source formats.
- ISBN and identifier utilities: normalize, validate, classify, and convert
  identifiers.
- Catalog model: define normalized catalog records and schema-level behavior.
- Bibliographic enrichment clients: query Open Library, Library of Congress,
  OCLC/WorldCat, and other bibliographic sources.
- Cache and provenance handling: store raw responses, source timestamps, and
  reproducibility metadata.
- Resolution and matching: manage exact ISBN matches, title fallbacks, duplicate
  handling, confidence scores, and manual-review queues.
- Market research collectors: gather and normalize market observations.
- Valuation engine: turn market evidence and heuristics into estimates.
- Decision engine: generate recommendations from catalog facts, market
  evidence, valuation estimates, and user priorities.
- Artifact writers: produce CSV, XLSX, reports, dashboards, and workbooks.
- CLI orchestration: expose workflows without embedding business logic in
  command handlers.

Business logic should live in the relevant domain modules, not in output
formatting code or command-line glue.

## Generated Artifacts Policy

Generated artifacts are useful working products, not canonical project state.

CSV, XLSX, reports, dashboards, and review queues should be reproducible from
source inputs, caches, configuration, and code. Manual edits to generated Excel
files should not be treated as durable data unless they are imported back
through an explicit, documented workflow.

The project should distinguish between:

- Source inputs that represent original evidence.
- Caches that preserve external enrichment responses.
- Normalized catalog data that acts as the durable project dataset.
- Generated artifacts for browsing, analysis, review, and communication.

For v0.2.0, generated Excel and CSV files under `output/` must not be read as
source data. They must be reproducible from `input/`, `data/`, `cache/`,
`config/`, and code.

When generated files are committed, the reason should be clear: for example,
sample outputs, reproducibility checkpoints, or user-facing deliverables.

## Testing Expectations

Tests should protect the parts of the system that are most likely to corrupt
catalog data or user trust.

Current tests cover ISBN validation, ISBN conversion, ASIN classification,
privacy filtering, enrichment analysis, XLSX generation, title-query cleanup,
text similarity, metadata deduplication, and catalog joins.

As the system grows, tests should also cover:

- End-to-end workflow behavior for `update-library`.
- Cache reads, writes, and reuse.
- Batch lookup behavior.
- Matching thresholds and manual-review routing.
- Duplicate ISBN and edition ambiguity handling.
- Schema stability for catalog, market research, valuation, and decision data.
- Artifact generation from normalized data.
- Failure behavior when external services are unavailable or incomplete.

Network-dependent behavior should be isolated behind clients that can be tested
with fixtures or cached responses. Core catalog, matching, valuation, and
decision logic should be testable without live network access.

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

The post-v0.8.0 direction separates four concerns into staged releases: a
resumable full-library eBay baseline, Libib physical-inventory context, a shared
presentation model serving Library Explorer and Action Center, and incremental
monthly orchestration. Detailed listing artifacts can remain generated, but
safe resume and later refresh will require deliberately scoped collection state
and provenance. v0.9.0 defined only its minimum checkpoint state and did not
prematurely finalize the longer-term durable schema.

The v0.10.0 design treats Libib as physical-inventory evidence, not catalog
authority. `catalog_item_id` remains the intellectual/catalog key and
project-owned `holding_id` identifies one physical copy. Durable inventory
imports and source items preserve provenance and unmatched evidence; versioned
match records explain links to catalog items; holdings preserve current belief
and user-maintained audit/disposition state. Libib metadata cannot silently
overwrite canonical catalog fields, and absence in a later export cannot by
itself establish disposal. Strong, unambiguous Libib evidence may create a new
catalog item and holding without an acquisition; weak or conflicting evidence
requires review. Inventory imports own declared audit scope and completeness,
so partial, location-specific, filtered, and progressive audits cannot mark
unexamined catalog items missing or invalidate holdings confirmed in another
scope. Project-owned `location_id` values identify physical places; Libib
catalog/location labels remain source evidence until conservatively mapped.
Renaming a location or moving a holding does not change catalog or holding
identity. See `LIBIB_INVENTORY_DESIGN.md` for the tentative
PR1 contract; production schemas remain deferred to implementation PRs.

PR2 adds a pure Libib CSV parser in `valuation/libib.py`. It accepts an explicit
path, reads UTF-8 CSV into immutable in-memory records, preserves every source
field, and emits structured diagnostics alongside conservative normalized
ISBN, date, creator, publisher, collection-label, and copies values. It performs
no durable write, discovery, matching, catalog creation, holding creation,
location mapping, reconciliation, artifact generation, or CLI orchestration.
The observed export contains no stable Libib item/copy identifier, so row
position remains provenance only. The `collection` field remains source
location evidence and `added` remains Libib-addition evidence, not acquisition
date.

PR3 adds `valuation/libib_inventory.py` above the pure parser. It accepts an
explicit CSV or exactly one CSV directly inside one explicitly selected audit
area below `input/libib/`; it never traverses recursively. It writes three
strict, versioned durable repositories: `inventory_imports.csv`,
`inventory_import_folders.csv`, and `inventory_holdings.csv`. All proposed rows
are validated and staged before same-directory atomic file replacement, with
in-process rollback if publication fails.

The folder registry protects each relative audit-area path with its confirmed
exact collection label. It is operational metadata, not inventory, source
evidence, import identity, or physical-location identity. Folder/collection
mismatches return `collection_label_changed_or_misfiled` without durable
mutation and require manual confirmation. Import identity is the source byte
hash plus project-owned `inventory_import_id`, never filename, mtime, folder
name, or `folder_id`. Exact duplicate content returns the existing import and
does not update holdings or folder timestamps.

PR3 keeps four audit concepts separate. `folder_path` is operational filesystem
organization; `source_collection_label` is exact immutable Libib evidence;
`audit_scope` is normalized, nonblank caller-declared descriptive context; and
`audit_completeness` is only `complete_scope`, `partial_scope`, or `unknown`.
Both audit fields default to `unknown`, and neither is inferred from the export.

Because the profiled export has no stable copy key, first-pass holding identity
uses UUIDv5 over the stable folder registration ID and a fingerprint of
identity-bearing row evidence. The fingerprint excludes row position,
filename, timestamps, collection label, Libib `added`, and `copies`. This keeps
IDs stable across row reordering and operational renames while acknowledging
that material bibliographic edits cannot be automatically reconciled in PR3.
Indistinguishable duplicate rows are rejected for review rather than assigned
order-dependent identities. An explicit file outside the registered input tree
uses the import ID as its one-import identity scope. Catalog and location IDs
remain blank; quantities greater than one remain one unresolved holding row
with `copies > 1` rather than speculative copy expansion.

Holdings retain normalized title, creator, and ISBN comparison keys solely for
the PR3 changed-row guard. On a later import from the same registered folder, a
new fingerprint that shares an ISBN or normalized title-plus-creator with a
prior holding returns `holding_identity_changed_requires_reconciliation`.
Nothing from that import is published: the existing holding stays active and no
second holding is appended. This is ambiguity detection, not matching; full
reconciliation and immutable row-level observation history remain outside PR3.

The PR4 reconciliation design settles that missing boundary. A durable
Inventory Observation preserves each accepted row-level assertion immutably;
Inventory Holding remains the mutable current-belief snapshot; and an
append-preserving reconciliation decision explains every accepted or unresolved
observation-to-holding interpretation. Physical reconciliation precedes catalog
matching because copy continuity and bibliographic identity are independent.
Observations never receive authoritative mutable holding/catalog links, and
holdings are never regenerated from the newest export. See
`INVENTORY_RECONCILIATION_DESIGN.md` for the outcome vocabulary, lifecycle,
refresh rules, tentative repositories, and PR5 implementation boundary.

PR5 implements that boundary in `valuation/libib_inventory.py`. Accepted rows
now publish immutable schema-v1 `inventory_observations.csv` evidence and one
current append-only schema-v1 reconciliation decision per observation alongside
schema-v2 current holdings. Automatic holding mutation is limited to a unique
exact fingerprint in the same registered folder; automatic new holding creation
requires `copies = 1`, no credible existing candidate or conflict, and either a
valid normalized ISBN or normalized title plus creator. Changed identifiers,
multiple candidates, weak evidence, quantities other than one, and identical
duplicate rows persist as non-mutating decisions. All five inventory CSVs stage,
validate, and publish under the PR3 rollback boundary.

Real-state PR6 validation refined the PR5 weak-overlap guard. When both an
incoming observation and an existing holding carry valid, nonconflicting, and
different ISBN-13 identities, shared title-only or creator-only text is not a
physical-continuity candidate and does not block a distinct holding. Exact
fingerprint or ISBN continuity remains a candidate; same-ISBN multiplicity,
blank/inconclusive ISBN evidence, conflicting identifiers, quantities, grouped
records, and indistinguishable copies remain reviewable.

PR3 holding schema v1 is read compatibly and migrated only when every import row
balances to one persisted PR3 holding. Backfilled observations are explicitly
`pr3_backfill` / `legacy_derived`; unavailable raw values remain blank rather
than being invented. Holding IDs, blank catalog/location links, and current
state survive schema-v2 migration. Catalog matching and creation were deferred
to PR6.

PR6 implements catalog reconciliation in `valuation/libib_catalog.py` without
collapsing physical identity, catalog identity, or acquisition history. It reads
only explicit versioned observation columns, requires an accepted current
physical-reconciliation decision, and writes schema-v1 append-only
`inventory_catalog_reconciliation_decisions.csv`. A unique valid ISBN match may
link an eligible catalog item; title plus creator requires matching publisher
for automatic acceptance. Title-only, creator-only, conflicting, duplicate, or
ineligible candidates remain review outcomes. Strong no-candidate evidence may
initialize a catalog item only when a valid ISBN, title, creator, and one-copy
holding agree. Existing catalog metadata is never overwritten, and Libib-added
dates never become acquisition dates.

The existing fixed-header `catalog_items.csv` contract remains unchanged and
`inventory_holdings.csv` remains schema version 2. Catalog rows have no durable
status column today, so current rows default to active; callers may supply an
explicit closed status projection (`active`, `excluded`, `merged`, or `invalid`)
and every candidate status used is snapshotted in the decision. Catalog rows,
catalog decisions, and holding links validate and publish under one staged
rollback boundary. No acquisition repository participates in the write set.

The v0.9.0 checkpoint layer is an isolated filesystem boundary under an ignored
run directory. An immutable manifest identifies compatible work; a deterministic
per-item ledger records sanitized execution state; and atomic per-item JSON
parts contain canonical eBay observation rows. Same-directory temporary writes,
`fsync`, and atomic replacement prevent partial active state. This checkpoint is
minimum execution state, not durable market history, and no client or network
dependency enters the state module.

PR3 adds orchestration above that boundary without changing the client, adapter,
or targeted collector. The production-only command fingerprints and orders the
summary, initializes or validates checkpoint state, performs one item transition
at a time, and writes only canonical atomic parts. Authentication-class failures
stop globally; bounded transient failures may retry; sanitized unexpected
failures terminalize one item. Restart archives rather than deletes. Aggregate
progress and run summary remain generated and contain no listing details.

Long-run authentication is isolated in an injectable in-memory Browse session.
It stores token value/expiry only in process memory, uses monotonic refresh
timing, and permits one refresh/retry after bearer rejection. Structured safe
request errors preserve only operation, status, retry-after, and failure class.
Per-invocation retry budgets and capped backoff prevent retry storms while
leaving exhausted temporary items eligible for a later resume. Atomic summary
writes and disk-ledger reload on interruption complete the recovery boundary.

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
- `market_observations.csv` / `.xlsx`: source-specific generated listing and
  lookup-status observations.
- `targeted_ebay_observations.csv` / `.xlsx`: explicitly generated, bounded
  eBay active-listing and lookup-status observations for reviewer-priority
  candidates.
- `market_evidence_summary.csv` / `.xlsx`: source-neutral generated per-book
  evidence coverage, confidence, asking-price-derived range, and review guidance.

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

## v0.5.0 Market-Evidence-First Architecture

Version 0.5.0 adds an opt-in generated transformation after market collection:

```text
Source-specific market observations
        |
        v
Source-neutral Market Evidence Summary
        |
        +--> availability and coverage
        +--> market confidence and outlier sensitivity
        +--> cautious asking-price-derived range
        +--> review recommendation or fallback research priority
```

The summary is regenerated under `output/`; it is not a repository and is not
an input to `update-library`. Research Assessment score and band are copied only
as fallback review context when market evidence is unavailable. They do not
change asking-price statistics, confidence, or range calculations.

Source adapters remain separate from aggregation and interpretation. AbeBooks
collection stays in `valuation/abebooks.py`; source-neutral summary behavior
stays in `valuation/market_evidence_summary.py`.

The optional `build-abebooks-review-workbook` transformation reads the complete
Market Evidence Summary and joins `data/acquisitions.csv` by stable
`catalog_item_id`. It exposes a narrower review queue while retaining every
canonical summary field on an Evidence Detail tab. Possession confidence is
date-derived review context only and never changes market evidence or review
recommendation semantics.

The downstream `build-abebooks-review-report` transformation reuses that same
acquisition-context join and produces a portable, static HTML sharing view. It
projects only essential reviewer fields into tabbed, action-specific tables,
combines conservative references into one displayed AbeBooks range, and shows
only the latest acquisition year with a possession-verification prompt when
needed. Detailed confidence and outlier fields remain available in the workbook
and evidence artifacts. The report does not change or persist Market Evidence
Summary, catalog, or acquisition records.

When the input has multi-source fields, both reviewer transformations reuse the
same display helpers for evidence source, eBay listing count, eBay item-price
range, source-specific status, and price comparability. The HTML report adds
these compact fields conditionally, plus source counts and interpretation text;
legacy AbeBooks-only input keeps the original report columns. Neither projection
pools source prices or changes the summary's core range, confidence, or
recommendation. Seller identity is neither stored nor displayed.

Together, the full-library collector and these two review transformations are
the v0.6.0 Full AbeBooks Baseline & Review Artifacts workflow. A second-source
adapter and cross-source interpretation are deferred to v0.7.0 or later.

### Planned v0.7.0 eBay source boundary

The v0.7.0 plan adds eBay behind a source-specific client and adapter before it
touches source-neutral aggregation:

```text
Environment/local ignored credentials
  -> eBay Browse API client
  -> source-specific eBay observation/status rows
  -> targeted generated collection artifacts
  -> reviewed multi-source summary transformation
  -> reviewer workbook and static HTML projections
```

The client owns OAuth application-token acquisition, environment/marketplace
selection, pacing, bounded pagination, and sanitized failures. The adapter owns
field normalization and matching while preserving source provenance, item price,
shipping, currency, buying option, and active-listing status. Aggregation must
not branch on eBay response shapes or naively pool eBay and AbeBooks prices.
Credentials, tokens, eBay outputs, and combined outputs never become durable
catalog state or monthly-import inputs.

PR2 implements only the first client-boundary probe in
`valuation/ebay_access.py`. `ebay-access-check` reads four explicit environment
variables, obtains an application token, and performs one item-summary search
limited to at most three results. It writes no artifact and projects only safe
title/price/currency snippets. HTTP failures are converted to redacted
user-facing errors. The module is not an observation adapter and has no path to
Market Evidence Summary, workbook, report, or monthly-import code.

PR2 intentionally validates sandbox access first. Production access is
unverified because the production keyset is disabled pending eBay Marketplace
Account Deletion/Closure notification compliance. This is an operational access
gate, not a reason to hard-code sandbox behavior or remove production endpoint
support from the isolated client.

The first bounded sandbox run exposed a local Python trust-store gap: the
virtual environment reported no active default CA file. A local troubleshooting
retry set `SSL_CERT_FILE` to the installed certifi bundle, preserving certificate
validation and successfully reaching the token endpoint. After correcting an
incorrect local secret value, the sandbox client acquired an application token
and completed one item-summary search. The zero-result response validates the
request path but not production coverage or match quality. The CA override is
local environment troubleshooting, not a source-client requirement or reason
to weaken TLS verification.

PR3 adds `valuation/ebay_active_listings.py` as a source-specific normalization
layer over the PR2 access client. It accepts one direct query, obtains an
application token through the existing boundary, performs one bounded search,
and returns immutable in-memory result objects. The provisional fields retain
item identity, title, item price/currency, URL, condition, buying options,
item-location country, query, marketplace, and an
`ebay_active_listing` source label. Missing optional fields remain blank and raw
responses are not retained. Seller username is intentionally not normalized or
retained. This layer still has no repository, CSV/XLSX,
Market Evidence Summary, workbook, report, or monthly-import integration.

PR4 adds `valuation/ebay_observations.py`, a pure adapter from those immutable
client results to the existing 25-field market-observation row shape. It is
network-free and file-free. Observed rows use `ebay_active_listings` as the
source, preserve item price and currency without shipping or conversion, and
keep item ID, buying options, marketplace, and item-location country in
`raw_reference` or `match_notes`. Match confidence remains `unknown`.

The adapter also produces one `no_results`, `no_query`, or sanitized
`source_unavailable` status row when the caller supplies the corresponding
outcome. It adds no collection command or generated artifact and has no path to
Market Evidence Summary, workbook, report, monthly import, or durable catalog
state. Production access remains gated and unverified.

PR5 adds `valuation/ebay_targeted_collection.py` and the explicit
`collect-targeted-ebay-observations` command. The command requires a generated
Market Evidence Summary input, an output under `output/`, and a book limit. It
defaults to the possible-sale queue, deterministically orders selected
candidates, and constructs one query using ISBN-13, ISBN-10, title plus author,
or usable title. Limits are capped at 100 books and 10 results per book, with a
one-second default delay between requests.

The workflow writes only the existing 25-field observation schema as paired
CSV/XLSX generated artifacts. It stops after the first safe client error to
avoid repeated credential/token failures. It neither reads its own outputs nor
automatically connects them to downstream artifacts, monthly import, or durable
state. Production remains gated and unverified.

### v0.8.0 production validation boundary

v0.8.0 PR1 removes seller username from the normalized eBay client object and
leaves the shared observation `seller` field blank for eBay rows. Seller
identity is neither retained in the source-specific object nor written to
`match_notes`.

On 2026-07-18, PR2 ran the existing targeted collector against production for a
two-book, ISBN-13 cohort with at most three results per book and a one-second
delay. The run produced four `observed` rows in ignored paired CSV/XLSX files.
All rows used `ebay_active_listings`, retained item ID, URL, title, item price,
USD currency, condition, buying options, marketplace, item-location country,
query, and strategy, and kept match confidence `unknown`. All four `seller`
values were blank and seller identity was absent from `match_notes`.

This validates production OAuth, bounded Browse requests, normalization, the
privacy-hardened observation adapter, and generated artifact writing. It does
not add or authorize full-library collection, downstream workbook/report
integration, shipping-inclusive pricing, conversion, sold/completed evidence,
or new match-confidence rules.

PR3 raises the explicit targeted-book ceiling from 50 to 100 so the requested
representative cohort remains enforced at the CLI boundary; 101 books are still
rejected. Because the existing multi-queue selector preserves review-priority
ordering rather than applying quotas, validation used an ignored,
deterministically selected 34/33/33 cohort file as collector input. This avoids
changing review recommendation or selection semantics merely to balance a
validation sample.

The balanced production run yielded 229 listing rows and 13 `no_results` rows
for 100 unique books. A repeated-input multi-source summary added those eBay
facts to the 3,014-row AbeBooks baseline while leaving `likely_low`,
`likely_mid`, `likely_high`, `market_confidence`, and `review_recommendation`
unchanged for every catalog item. `market_range_source` remained `abebooks` for
all 3,014 rows. This validates the supplemental boundary: production eBay data
is separately auditable and does not silently replace established core-range
semantics.

PR6 extends the existing summary command to accept repeated observation inputs.
The aggregator still groups to one row per catalog item and adds a source-aware
projection for AbeBooks and eBay counts, statuses, currencies, price summaries,
source mix, comparability, and the source used for the core market range.

For mixed items, AbeBooks remains the primary basis for the pre-existing core
range, confidence, and recommendation fields. Supplemental eBay rows are not
pooled into those calculations, so eBay listings cannot automatically upgrade
confidence and eBay `no_results` cannot erase AbeBooks evidence. eBay-only rows
use the existing cautious core rules. Source currencies remain separate;
shipping and conversion are excluded. This generated prototype has no workbook,
HTML report, monthly-import, or durable-state integration.

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

The shared book-source architecture should use three principal families: Amazon
Import, Libib Import, and Manual Entry. Barcode scanning is an input mechanism
for Libib or Manual Entry, not a durable family. Estate inventories, donations,
inherited books, dealer purchases, and similar origins normally use Libib or
Manual Entry with explicit provenance. v0.10.0 does not migrate or alter the
implemented historical Amazon structures.

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

### v0.10.0 inventory audit presentation boundary

PR7 implements `valuation/inventory_audit.py` as a source-neutral, read-only
projection over the strict inventory, catalog, and acquisition repositories.
It resolves current physical decisions per observation and current catalog
decisions per holding exclusively through explicit append-only supersession
links. Missing predecessors, branches, cycles, cross-entity supersession, or
multiple current decisions fail closed; row order and timestamps never select
the current decision.

The projection produces `output/inventory_audit_summary.csv` and one generated
`output/inventory_review_workbook.xlsx` containing summary, physical review,
catalog review, audit coverage, location review, newly discovered, reconciled
holdings, import detail, and decision detail sheets. These artifacts do not
invoke import or matching code and never write beneath `data/`. Workbook edits
are not imported. PR8 may refine reviewer usability, definitions, and visual
acceptance, but must reuse this presentation model rather than introduce
parallel reconciliation semantics.

PR8 keeps that boundary while presenting collector-facing information first.
Review sheets lead with a generated suggested next step, title, author, and
human-readable issue context; stable IDs and technical provenance remain
visible to the right. These suggestions are display hints, not editable
workflow state. Empty queues show an explanatory message without adding a row
to the generated presentation model. All sheets remain visible, formula-free,
filterable, and reproducible; workbook package timestamps are fixed so identical
inputs produce byte-identical XLSX files across runs.

Only explicit allowlisted columns are projected. In particular,
`raw_evidence_json`, unknown source columns, and arbitrary raw-evidence keys are
excluded. Optional Research Assessment and generated market-summary inputs add
presence flags only; they do not recalculate either subsystem.

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

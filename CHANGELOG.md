# Changelog

## v0.8.0 - 2026-07-19

Release focus: Production eBay Validation & Reviewer Integration.

Added:

- Production OAuth/Browse validation and a bounded representative 100-book
  study covering possible-sale, manual-research, and edition/condition queues.
- Compact source-aware eBay evidence in the generated reviewer workbook and
  static HTML report, with source mix, listing counts, item-price ranges,
  source-specific statuses, and price-comparability context.
- Release-readiness and production-validation records for the ignored,
  non-durable workflow.

Changed:

- Seller username is removed from normalized eBay listing objects and is not
  written to observation seller fields, notes, workbooks, or HTML reports.
- The targeted collection ceiling is 100 books, with validation rejecting 101.
- Reviewer artifacts explain that eBay is supplemental active-listing evidence;
  AbeBooks remains the core range source for mixed-source rows.

Unchanged:

- AbeBooks collection, conservative range, confidence, and recommendation
  behavior; Research Assessments; monthly imports; and durable data.
- Source prices are not pooled, shipping is excluded, currency is not converted,
  and eBay match confidence remains unknown pending human review.

Known limitations:

- Active listings are not sold/completed evidence, appraisals, fair market
  value, realized prices, or expected proceeds.
- Full-library eBay collection, automated edition matching, improved match
  confidence, shipping-aware prices, and currency normalization remain deferred.

## v0.7.0 - 2026-07-18

Release focus: eBay Active Listings Integration.

Added:

- Isolated eBay credential, OAuth application-token, and Browse API access with
  sandbox/production endpoint separation and safe error redaction.
- Reusable in-memory active-listings client and pure adapter to the existing
  25-field market-observation schema.
- Explicit bounded `collect-targeted-ebay-observations` workflow with
  reviewer-priority filtering, conservative query construction, pacing, and
  ignored CSV/XLSX artifacts.
- Source-aware Market Evidence Summary fields for separate AbeBooks and eBay
  counts, statuses, currencies, price summaries, source mix, and comparability.

Changed:

- `summarize-market-evidence` accepts repeated `--observations` inputs.
- Mixed-source summaries preserve AbeBooks as the core range, confidence, and
  recommendation basis when AbeBooks evidence exists; eBay remains supplemental.
- Release documentation records verified sandbox OAuth/Browse requests and the
  3,014-row multi-source readiness check.

Unchanged:

- AbeBooks collection behavior and AbeBooks-only summary/recommendation rules.
- Research Assessment logic, monthly Amazon imports, and durable catalog or
  acquisition data.
- Existing AbeBooks workbook and HTML report projections.

Known limitations:

- eBay evidence is active-listing asking-price evidence, not sold/completed
  evidence, appraisal, fair market value, or expected proceeds.
- Production eBay access remains gated and unverified; sandbox returned no
  representative listing rows.
- Shipping is excluded, currency conversion is not performed, and eBay match
  confidence remains unknown.
- Workbook/HTML integration, representative production collection,
  sold/completed evidence, and any full-library eBay strategy remain deferred.

## v0.6.0 - 2026-07-16

Release focus: Full AbeBooks Baseline & Review Artifacts.

Added:

- Source-integration spike documenting candidate-source constraints and a
  staged path beyond AbeBooks.
- Conservatively paced full-library AbeBooks observation collection with
  bounded-run and output-path controls.
- Reviewer-facing AbeBooks Excel workbook with focused queues, complete
  evidence detail, run summary, field definitions, and acquisition context.
- Static, self-contained HTML report with tabbed review queues, acquisition-year
  prompts, combined AbeBooks ranges, queue guidance, sort-order documentation,
  report metadata, and caveats.

Changed:

- The AbeBooks experiment can now be run across the full assessed catalog and
  transformed into shareable review artifacts.
- Latest acquisition dates provide possession-verification context without
  suppressing market evidence or changing review recommendations.
- eBay active-listing integration is deferred to the v0.7.0 release theme.

Unchanged:

- Market Evidence Summary aggregation, confidence, range, and recommendation
  semantics.
- Research Assessment scoring, signals, weights, bands, and persisted records.
- Monthly Amazon import behavior and durable catalog/acquisition schemas.

Known limitations:

- AbeBooks seller asking prices are not appraisals, fair market value, realized
  sale prices, or expected sale proceeds.
- Edition, condition, dust jacket, signature, seller credibility, and physical
  possession may materially affect value.
- eBay and other independent market sources are not included in v0.6.0.

## v0.5.0 - 2026-07-14

Release focus: Market Evidence First.

Added:

- Generated source-neutral Market Evidence Summary CSV and XLSX artifacts.
- Deterministic aggregation of listing and status observations by catalog item.
- Market confidence and outlier-sensitivity classifications.
- A conservative asking-price-derived market range prototype.
- Review recommendations and fallback Research Assessment priority context.
- Versioned evidence notes, method provenance, and stable reason codes.

Changed:

- Market observations are now the primary evidence where usable.
- Research Signals are positioned as fallback, uncertainty, metadata-cleanup,
  and review-prioritization inputs rather than price evidence.
- Release documentation now distinguishes raw observations, evidence quality,
  descriptive ranges, and recommended human review.

Unchanged:

- Production Research Assessment scoring, signals, weights, and bands.
- Durable catalog, acquisition, assessment, and Collector Review records.
- Monthly `update-library` behavior and AbeBooks collection behavior.

Known limitations:

- Current price evidence consists of seller asking prices, not completed sales.
- Currency conversion is not performed; mixed currencies suppress range output.
- Edition and condition matching remain lightweight and may require review.
- Range and sale-review thresholds are initial deterministic heuristics, not
  statistically calibrated estimates of realizable proceeds.

## v0.4.0 - 2026-07-13

Release focus: Market Validation and Market Intelligence research infrastructure.

Added:

- Deterministic stratified Market Validation sample generation.
- Bounded ISBN-first AbeBooks observation collection with verified TLS, rate
  controls, diagnostics, and preserved lookup references.
- Market observation coverage, score-band analysis, and Research Signal
  effectiveness reporting.
- Expanded validation workflows covering 205 books and 596 AbeBooks observation
  rows in the completed experiment.
- Non-production Research Assessment calibration scenario simulation.
- Market Validation findings, calibration principles, proposal, and decision
  records.

Changed:

- Added opt-in CLI workflows for Market Validation data preparation, collection,
  analysis, and simulation.
- Documented the decision to preserve current production Research Assessment
  scoring in v0.4.0.

Unchanged:

- Production Research Assessment logic, signals, weights, and bands.
- Durable catalog, acquisition, assessment, and Collector Review data.
- Monthly `update-library` behavior.

Known limitations:

- AbeBooks asking prices are single-source observations, not completed sales or
  valuations.
- Edition matching and condition interpretation remain lightweight.
- The stratified evidence does not establish catalog-wide prevalence.
- Simulated calibration alternatives did not improve the practical top
  candidate set.

## v0.3.0 - 2026-07-09

Release focus: Research Candidates and Collector Review workflow.

Added:

- Deterministic Research Signals that explain why a catalog item may deserve
  collector attention.
- Generated Research Assessments that aggregate Research Signals into a score,
  band, and human-readable explanation.
- Generated Research Candidates in CSV and XLSX form, sorted for collector
  review.
- Durable Collector Review repository in `data/collector_reviews.csv` for
  collector-owned workflow state and notes.
- Generated Collector Workbook at `output/collector_workbook.xlsx` with Summary,
  Research Candidates, Current Acquisitions, Reviewed Items, Metadata Gaps, and
  Collector Reviews sheets.
- Metadata Gap categories and counts in the Collector Workbook.
- Release planning, domain model, and v0.3.0 architecture documentation.

Changed:

- Monthly updates now regenerate Research Candidates and the Collector Workbook
  alongside existing catalog outputs.
- Terminal summaries list the generated Research Candidate and Collector
  Workbook artifacts.
- Workbook Research Candidates use collector-facing Research Rationale instead
  of signal-code internals.
- Generated workbook edits are explicitly treated as non-imported output;
  durable collector-owned state remains in `data/collector_reviews.csv`.

Known limitations:

- Modern Amazon `B0...` ASIN physical-book detection is deferred.
- Research Assessment effectiveness still needs empirical validation against
  manual market research.
- Metadata Gap classification may evolve as richer metadata sources are added.
- Workbook edits are not imported.
- Collector Review editing workflow is not yet implemented.
- External valuation sources and market valuation are not included in this
  release.

## v0.2.0 - 2026-07-05

Release focus: durable monthly Amazon library updates.

Added:

- Durable catalog identities in `data/catalog_items.csv`.
- Durable acquisition records in `data/acquisitions.csv`.
- Durable research-priority assessments in
  `data/research_priority_assessments.csv`.
- Append-only import audit log in `data/import_manifest.csv`.
- Automatic monthly Amazon export discovery under `input/amazon/`.
- Amazon ZIP package support, including compatible `Retail.OrderHistory.1`
  exports.
- Open Library caches under `cache/openlibrary/`.
- Console summary for monthly updates.
- Friendly expected CLI errors for common Amazon input problems.
- Optional macOS success/failure notifications for interactive monthly updates.

Changed:

- Generated reports under `output/` are treated as disposable outputs, not source
  data.
- ISBN remains matching evidence, while `catalog_item_id` is the durable catalog
  identity.

Known follow-up:

- Add explicit research-priority re-evaluation modes.
- Add metadata refresh, override, and staleness policy.
- Consider a one-time migration helper for older Open Library caches that still
  live under `output/`.

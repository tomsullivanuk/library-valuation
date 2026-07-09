# Changelog

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

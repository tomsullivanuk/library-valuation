# Changelog

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

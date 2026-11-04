# Workspace review — November 4, 2026

The agreed everyday workflow centers on the completed physical Libib inventory.
Historical records and all-record views belong in Reports; preserve every purchase
and all raw inventory/reconciliation evidence.

## Agreed revisions

- Show physical-book and distinct recorded-title counts. Count titles from current
  inventory observations using Unicode normalization, case folding and whitespace
  normalization; do not equate Libib records or catalog editions with titles.
- Move identification questions out of Library and into Action Items.
- Remove the Acquired filter while retaining acquisition data and date sorting.
- Use the Libib collection for Location, omit the leading “Box”, naturally sort
  locations and list each location for multiple copies. Preserve grouped labels:
  `1, 3 and 3A, 8`.
- Add rounded unit cost to Acquired. For multiple purchase records, display the
  latest purchase's unit price, not their sum or the latest order subtotal.
  Preserve exact unit prices/subtotals and currency in acquisition history.
- Put ISBN below publisher/year on the left of each card. Prefer ISBN-13 and
  otherwise use ISBN-10; omit the line when neither is known.
- Show copy, acquisition, research and market information directly in book details.
  Remove redundant status labels and generic attention banners. Link specific
  related tasks, and keep technical provenance under About this data/record.
- Add a saved disposition selector. Initial choices: unassigned, Keep, Sell,
  Donate, Gift, Recycle and Undecided. A disposition is an intention, not evidence
  that disposal has occurred; assigning it must not alter physical presence.
- Combine outstanding book checks and meaningful current recommendations in
  Action Items. Separate optional research from book checks, default to open book
  checks, and support Complete, Defer until a date, Dismiss and Reopen with notes.
  A completed check records the task status/answer; it does not silently rewrite
  ISBNs or reconcile inventory. Those evidence changes still require review.

## Delivery and persistence

Use `python -m valuation.workspace_service` and open `http://127.0.0.1:8765`.
The service listens only on this computer. Dispositions are saved in
`data/collector_reviews.csv`; action states, answers and decision events are saved
in `data/workspace_actions.json`. Generated HTML is a read-only fallback and must
not imply it can save without the service. Decisions survive reloads, process
restarts and regeneration. Changed task content reopens the task while retaining
its previous events. Stale simultaneous edits are rejected rather than replacing
another saved decision.

Internal location-ID assignments are unnecessary tasks when a Libib collection is
already present. “No action needed”, sufficient-market-evidence labels and the fact
that a book was newly inventoried are not themselves tasks. Retain their underlying
evidence, but do not clutter Action Items with them.

Source records, personal purchase data and generated reports stay local under the
existing ignore rules. Maintain application code, tests and these decisions in
GitHub. Unrelated files in `outputs/family-thank-you` are outside this change.

Double-click `Open Library.command` to start the local service and open the Library.
Keep its window open while browsing; closing it stops the service without removing
saved decisions. If the service is already running, the launcher opens it.

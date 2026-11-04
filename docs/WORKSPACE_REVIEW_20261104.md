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
  Gift / Donate, Recycle and Undecided. A disposition is an intention, not evidence
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
The service runs in the background, so the launcher window can be closed. If the
service is already running, the launcher reuses it. Reopen it after restarting the
computer; saved decisions remain in place.

## Further header and search review

Remove the upper-right tagline. Align the brand with the Library tab text and the
main desktop content with Import; retain a compact gutter on small screens. Make
Clear an intrinsically sized, shorter button rather than a stretched grid column.
Search also covers the description displayed in book details. Remove the vague ID
prompt; internal catalog, holding and acquisition IDs remain searchable for lookup.

## Detail and disposition follow-up

Match Clear to the actual rendered dropdown height, including Safari's native
controls. Match the book-detail title's smaller size and green color to Library
cards. Combine Gift and Donate into one Gift / Donate option. Display older gift
and donate decisions under that combined choice without rewriting their records;
explicit saves retain the prior value in decision history.

Future work: add selection of multiple Library records and a bulk disposition
update. Keep individual-record editing. Bulk editing is recorded as a future
capability, not part of this revision.

The detail disposition editor uses one visible section heading, a compact dropdown
and an adjacent Save disposition button. Retain the accessible field name and put
save feedback below the controls; allow wrapping on narrow screens.

Shorten the individual disposition button to Save and match the dropdown’s rendered
width and height. Acquisition history capitalizes Amazon and formats recorded
currencies with symbols (USD 35 becomes $35; fractional cents remain visible).
Omit the redundant subtotal for quantity one; retain it for multiple/unknown copies.
Exact amounts remain unchanged in the acquisition records.

Research priority is an additive attention score, not a percentage, price, or rarity
rating. Display plain-English reasons with their recorded point contributions in
book details and assessment views; retain raw codes and the original assessment.
The display must not recalculate old scores using newer configuration weights.

Market research Confidence, Evidence status and Notes use plain-English explanations
in book details and the market detail view. Translate every part of combined notes
and retain the source codes, asking-price limitations and original research dates.
Do not change estimates or rerun market queries as part of a wording change.

## Market-aware next steps (supersedes the earlier score display)

Remove Research priority from the ordinary book view. Books with usable market
estimates need no generic score-based research task. Keep historical assessments
for technical/reporting use. A usable estimate has recorded prices and currency,
current applicable evidence and high/moderate market confidence. Thin or ambiguous
asking-price ranges remain visible as evidence but still need specific review.

For books without a usable estimate, Action Items explains the evidence gap and
gives executable instructions with AbeBooks/eBay search links. Select the task
from the actual gap: no lookup, too few listings, uncertain edition, unusual prices,
mixed currencies, missing prices or an unavailable source. Older books can be
researched by title/author/publisher without requiring an ISBN or OCLC identifier.
A missing OCLC number or repeat purchase history alone is not a task.

Reuse an existing physical book check when it addresses the blocker, adding guidance
for the subsequent market comparison instead of a duplicate task. Guidance alone
does not reopen an unchanged answered book check. Retain all saved action history,
market evidence and original assessments. Research links open manual searches;
record findings in the task note. Completing a task does not automatically change
an estimate or catalog identity.

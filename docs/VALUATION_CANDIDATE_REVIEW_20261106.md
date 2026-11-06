# Existing-record review of the 26 live pilot comparisons

Completed November 6, 2026. All 26 books with candidate prices were reviewed against
the existing acquisition records, current Libib observations, catalog identities,
prior reconciliation decisions, earlier source-page transcriptions and saved live
listing details. No new marketplace requests were made. Estimates, canonical
records and existing Action Item statuses remain unchanged; this is a separate
review receipt and checklist, not publication or automatic task completion.

## Outcomes

| Outcome | Count |
| --- | ---: |
| Candidate book comparisons reviewed | 26 |
| Catalog-level ISBN identities supported by purchase and scanned inventory records | 25 |
| Book needing a focused physical edition check | 1 |
| Previously inferred linked copy needing confirmation when handled | 1 |
| Books retaining used-copy price context after working holds | 12 |
| Books with at least three retained used offers, possibly across condition grades | 8 |
| Books with at least three offers within one condition grade | 4 |
| Books without retained ordinary-used evidence | 14 |
| Published changes / new source requests | 0 / 0 |

The 14 books without retained used context include the one unresolved edition;
the other 13 need more suitable market evidence, not an owner edition investigation.
Four of the 12 with retained used context have fewer than three used offers and
also remain thin. All used-price contexts are conditional comparisons, not approved
replacement estimates or claims about the condition of the owner's copies.

## What existing records resolved

Matching acquisition and scanned Libib ISBNs support 25 catalog identities. Short
catalog titles, source publisher wording and printing-year differences were not
allowed to create unnecessary physical edition checks when those identifiers
agree. Multiple purchases remain purchase history; they do not independently prove
that the currently inventoried copies are different editions.

The inventory already supplies the correct Cambridge University Press wording
for a record whose catalog publisher has an unrelated ESOL label. The corrected
wording is used as review context; the canonical publisher field has not been
changed. This preserves the boundary between record-review conclusions and
publishing metadata changes.

Prior notes for the ISBN-less Crown *Relativity* already record Robert W. Lawson's
authorised translation and copyright 1961 by the Estate of Albert Einstein. This
resolves part of its identity and excludes a listing claimed to be a 1931 first
edition. Copyright is explicitly not treated as the printing/publication year.
The remaining physical question concerns actual binding and printing, then jacket
and condition; it is not a request to identify the book from scratch.

An ISBN-less physical observation already linked to *The Principle of Relativity*
by reviewed title/creator/publisher evidence retains its medium-confidence link.
The two barcode-bearing observations and matching acquisitions support the catalog
ISBN, but do not physically verify the third copy's edition. Its earlier decision
is preserved; confirmation is deferred until a copy-specific estimate or sale.

## Listing decisions

| Decision on saved listing evidence | Rows |
| --- | ---: |
| Retained working candidates, including separate new-copy context | 124 |
| Held for title-versus-structured-format/condition contradictions | 2 |
| Held used prices above multiple new-copy item-price offers | 9 |
| Held high price outside a tight same-format/grade cluster | 1 |
| Held pending the target book's remaining edition details | 3 |
| Excluded different publisher editions for the ISBN-less book | 5 |
| Excluded publication claim earlier than the recorded copyright | 1 |
| Already outside the preliminary candidate set; unchanged | 8 |

Held rows remain in the saved evidence. A hold is not a finding that a seller's
listing is false. New and used asking prices are separated, with used grades kept
separate. Nine used offers exceed at least two compatible-ISBN new-copy item prices
and are over 25% above the lowest such offer. They are held as weak working evidence
pending market/delivered-cost review. Shipping was not collected, so this is not a
claim that their total delivered prices are necessarily uncompetitive.

The high-outlier hold is supported by three same-format/grade offers whose prices
are within a 1.5 ratio and a fourth price over three times the lower cluster's
median. It is omitted from the working context but preserved for inspection. These
are transparent diagnostic heuristics, not accepted valuation or sale-pricing rules.

One listing calls itself hardcover in its title but paperback in structured data;
another calls itself Very Good in its title but Good in its structured condition.
Both are held rather than choosing a preferred field or asking the owner to
inspect their own book to resolve a seller's contradictory metadata.

## What needs the owner

The owner approved clearly labelled used-condition scenarios for the pilot, with
physical grading deferred until the copies are handled. No default grade is
assigned and publication remains disabled. The updated report replaces the policy
question with its applied status.

The focused edition check is *Relativity: The Special and the General Theory*,
location 74: confirm hardcover/paperback and the printing statement, plus any ISBN,
jacket and condition. Existing notes already establish the Crown/Lawson/1961
copyright context. The inferred *Principle of Relativity* copy is a separate,
conditional check in location 83 and 83a when handled; its accepted link is not reopened or rewritten.

Condition remains unrecorded for all 26 books. A deferred checklist groups these
checks separately from the priority edition question. Inspect copies when retrieved
or before copy-specific pricing/sale, rather than treating all 26 as urgent
bibliographic investigations. The checklist retains locations, questions and
priorities. Further seller/price research is explicitly agent work, not reassigned
to the owner as a physical task.

## Implementation, artifacts and validation

`valuation/candidate_record_review.py` creates private, reproducible record-review
receipts, per-listing decisions, an HTML review and a physical-check CSV. It checks
cohort coverage, target ISBN compatibility and observation fingerprints; refuses
to overwrite prior reviews or write into a canonical data directory; and does not
alter its inputs. Binding inferred from consistent returned listing metadata is
labelled as an inference, never as physical verification. Current condition remains
unknown. Original pilot evidence and earlier review outputs are retained.

Private results are on the Mini and copied to the laptop under
`output/valuation_review_20261106/live_ebay_pilot_v1/reviewed_candidates_v3/`:

- `review.html`: all 26 authored conclusions, used/new/grade contexts, held rows,
  the owner policy question and focused physical checks;
- `physical_checks.csv`: one priority edition check, one deferred inferred-copy
  check and 26 deferred condition checks;
- `review.json`: authored notes, acquisition/observation references, prior-note
  facts, per-listing decisions, retained contexts and input hashes;
- `protected_state_verification.json`: unchanged canonical and active-summary
  hashes on the authoritative Mini.

Individual book lists, source packets, source-page notes and receipts remain
private and ignored by Git. The public repository contains only the generic tool,
synthetic regression tests and aggregate findings. Ten new tests cover supported
versus mismatched identities, non-invention of physical facts, contradictory listing
metadata, used/new separation, outliers, condition/currency distinctions, earlier
copyright evidence, preserved inferred-copy links, complete cohort requirements,
changed source evidence, private outputs and unchanged inputs.

Full-suite validation: **667 tests passed on laptop and Mini**; the final copy-location
refinement also passed the 10 focused record-review tests. The private HTML report
was checked in a browser, including its 26 book sections, policy question, recorded
1961 copyright context and publisher-resolution note. The temporary server was
stopped afterward.

## Approved condition scenarios applied

The pilot-only policy is recorded privately with the exact 26-record cohort.
The latest report is under
`output/valuation_review_20261106/live_ebay_pilot_v1/used_condition_scenarios_v1/`.
Earlier reports remain available as review history.

- 25 separate grade/currency scenarios are displayed across the 12 books with
  retained used offers, phrased “If your copy is [grade]”. These are seller asking-
  price contexts, not condition assignments or approved Library estimates.
- Every scenario shows its listing count. Fewer than three offers are explicitly
  labelled limited evidence; three or more do not establish physical comparability.
- No used scenario is invented for the other 14 books or derived from new prices.
  New-copy prices remain separate context. No combined mixed-grade band is promoted
  as the owner's default condition scenario.
- All 26 condition checks are marked `deferred_until_handled` in the private
  checklist. Edition and inferred-copy checks remain intact.
- `condition_scenarios.csv` adds a structured download; physical-check CSV rows now
  include status. The HTML report links both files.
- Actual condition remains ungraded and publication false. The policy refuses a
  default-grade assignment, an expanded cohort, or publication authorization.
- Canonical records and active estimates on the Mini matched their pre-application
  hashes. There were no new source requests or changes to live Action Item states.

Nine additional regression cases cover applying the owner decision, preserving
source values and real-condition uncertainty, deferred grading, retained edition
checks, no invented new-only scenarios, and rejecting invalid, incomplete,
publication-enabled, grade-assigning or wrong-cohort policies. The latest browser
check confirmed 26 book sections, 25 conditional labels, the applied policy and
absence of the old pending question. Full validation: **676 tests passed on both
laptop and Mini**.

## Used-only follow-up and review

A separate bounded follow-up targets the 25 ISBN-identified books in the existing
26-comparison cohort, including all 12 books with prior retained used evidence.
The ISBN-less Crown edition remains deferred rather than borrowing a seller's
ISBN. Searches use the ISBN keyword with fixed-price and used-condition filters,
up to ten detail responses per book, a 300-request ceiling, and no broad title
fallback. The mode is pinned in the resumable checkpoint. The original mixed
new/used collector behavior and checkpoint format remain compatible.

The condition filter uses the broader USED category; returned listing details
still determine the specific grade and independently returned ISBN. See
[eBay's field-filter documentation](https://developer.ebay.com/api-docs/buy/static/ref-buy-browse-filters.html).
New-copy evidence from the first run remains separate context.

`valuation.pilot_followup.merge_observations` combines immutable saved runs,
retaining the newest snapshot per book/source/listing. Repeat fetches do not add
comparables; conflicting records at an identical timestamp stop the merge for
review. Input fingerprints and a private merge receipt preserve reproducibility.
The combined evidence is passed through a fresh preliminary review before the
record review, retaining the original observation fingerprint safeguards.

Grade scenarios now explicitly flag a high/low asking-price ratio of at least
three. Three offers alone do not make a wide or contradictory comparison usable.
No default grade, physical condition, approved estimate, or sale proceeds are
inferred. Physical grading remains deferred; edition questions remain intact.

The follow-up completed all 25 books with **175 requests**, below its 300-request
cap. It returned 149 listing details; merging with the earlier run removed 57
repeat fetches, leaving 248 distinct observed listings across the original pilot.
No listing was counted twice to inflate evidence.

The final record review retains used-copy context for **22 of 26 books**, up from
12. Six of the original twelve gained retained offers; six remained unchanged.
The other ten newly supported books previously had no retained used comparison.
There are now 58 grade/currency scenarios; 14 have at least three offers and a
high/low ratio below three, across 11 books. These remain review contexts, not
approved copy-specific values. Thin groups and one three-offer wide-spread group
remain explicitly labelled. Four books still have no retained used comparison:
two have only above-new used evidence held, one has no returned used evidence,
and the ISBN-less edition still needs its physical edition check.

Fresh authored notes address each of the original twelve individually. The final
private report is `used_followup_v1/review_final/review.html`; the comparison CSV,
merged evidence, source checkpoints, inputs and prior reports are preserved beside
it. Canonical records and the active estimate summary matched their pre-run
hashes. All 26 physical grading checks remain deferred, with the edition and
inferred-copy checks preserved. No Action Item state or estimate was changed.

Validation: **681 tests passed on laptop and Mini**. Five new cases cover
used-only filtering without search broadening, checkpoint mode consistency,
newest-snapshot deduplication, conflicting snapshots, and wide-spread scenarios.

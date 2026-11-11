# Additional 100-book valuation test

The owner authorized a 100-book scale test with interruption/recovery checks,
unchanged estimates, deferred physical grading and work retained in PR #2.
This is separate from the original 30-book pilot and does not authorize a
whole-library live collection or estimate publication.

## Frozen scope and budget

The authoritative Mini supplies the completed physical inventory and saved
estimates. The new cohort excludes all 30 original pilot records. Deterministic
selection uses a recorded seed and disjoint coverage groups:

| Coverage group | Records |
| --- | ---: |
| No valid catalog ISBN | 10 |
| Multiple physical copies | 15 |
| Existing edition flags | 15 |
| Uncertain historical prices | 10 |
| Usable lower-price estimates | 10 |
| Usable middle-price estimates | 10 |
| Usable higher-price estimates | 5 |
| Missing or weak estimates | 25 |
| Total | 100 |

This deliberately exercises edge cases; it is not a random population sample.
Groups are interleaved across four 25-book batches. Each batch retains the
collector's existing 30-book safety ceiling and has a 400-request cap, including
OAuth, retries and requests interrupted in flight. Total maximum: 1,600 requests.
The eBay Analytics API reported 4,620 Browse requests remaining out of 5,000 in
the current daily window before collection. Official schema documentation:
[application rate limits](https://developer.ebay.com/api-docs/master/developer/analytics/openapi/3/developer_analytics_v1_beta_oas3.json).

Queries use ISBN keywords with used/fixed-price filters. Missing-ISBN records use
title/author queries under the same filters, but their uncertain physical editions
remain held. Every book is limited to ten detail results. No new-copy ceiling is
inferred from this used-only search, no seller independence is inferred from
listing counts, and no AbeBooks requests are made.

## Recovery and report safeguards

A live subprocess is terminated with SIGTERM while a book is partially collected,
after an earlier book has completed. A second worker is first refused the existing
collection lock. Recovery uses the durable checkpoint and sanitized request
journal. Saved details and searches must not be requested again, persisted rows
must remain identical, and a completed rerun must make zero additional requests.
An in-flight response not yet persisted may need to be requested again; its first
attempt remains charged to the request budget.

The report validates complete batch scope, frozen metadata, request budgets and
materialized observations against durable checkpoints. It merges listing snapshots
without inflating counts, includes all 100 books even when no results exist, and
records input and review-code fingerprints. Previous pilot artifacts remain intact.

The scale test surfaced and addresses three interpretation gaps:

- Matching inventory scans can support ISBN identity without purchase history.
  Purchases corroborate where available; absence of a purchase is not an edition
  defect. Unscanned or inferred physical-copy links remain flagged.
- Scenarios separate binding, condition grade and currency. Unknown bindings stay
  explicitly flagged rather than being pooled with paperbacks or hardcovers.
- Explicit conflicting volume numbers are excluded, including Roman/Arabic
  equivalents and ranges. Exclusion reasons and existing source-page notes are
  visible in the detailed record report, not just in the preliminary report.

Existing source-page notes are carried forward for 28 books. Physical grading is
not assigned from those notes or sellers' condition labels. The model and record
review versions advance to v2; saved earlier reports retain their original results.

## Completed results

All four batches completed on November 6. Collector request counts were 193,
175, 213 and 164: **745 total**, including OAuth, retries and the interrupted
attempt. The two quota checks each used an OAuth and Analytics request outside
that collector count. The post-run Analytics response reported 3,920 Browse calls
remaining; the test relies on its conservative persisted counter rather than
assuming Analytics usage is updated synchronously.

| Result | Count |
| --- | ---: |
| Additional records completed | 100 |
| Listing detail observations | 639 |
| Books returning listings | 91 |
| Books with preliminary plausible candidates | 86 |
| Catalog ISBN identities supported by inventory scans | 87 |
| Books retaining used-copy evidence after review | 79 |
| Books without retained used evidence | 21 |
| Binding/condition/currency scenarios | 253 |
| Scenarios with 3+ listings, known binding and spread below 3× | 56 |
| Books represented by those stronger scenarios | 39 |
| Scenarios with fewer than three listings | 184 |
| Physical grading checks deferred | 100 |
| Edition checks retained | 13 |
| Additional inferred-copy checks retained | 3 |
| Estimates changed | 0 |

The grading, edition and inferred-copy counts describe different checks and may
overlap for a book. Scenario counts are not proposed-estimate counts. Real copy
grades remain unknown, so there are **zero verified replacement proposals**.
Missing prices are not filled using arbitrary condition discounts or new prices.

The actual interruption occurred after one completed book, with nine detail rows
already persisted across that book and the partial next book. SIGTERM returned
-15. Resume preserved those rows, repeated zero saved searches/details, and
finished the batch. A completed rerun made zero additional requests. The competing
worker was rejected before making a source request. Other API/auth/rate-limit
failure behavior remains covered by synthetic tests; this rehearsal does not
claim a Mini power-loss or operating-system crash test.

Twenty-seven targeted listing checks examined accepted and rejected results,
including six additional checks from batches 2–4. These are explicit review cases,
not an estimated precision rate. They covered matching ISBNs with abbreviated
names/titles, purchase-free inventory records, unknown bindings, a journal whose
remaining blank pages must be checked when handled, wide-price context, inferred
physical editions, contradictory condition labels, wrong authors/ISBNs/volumes,
and a compacted-author-name false negative kept as research-only.

A final check found a placeholder title with matching structured ISBN. The
network-free replay now holds such offers pending clearer listing evidence. It
preserves genuinely named titles containing “Unknown”. This removed one retained
scenario without additional live collection. The pre-refinement report is kept;
the final report lives in the private `refined_review_v2/` subdirectory.

Both pre-run and final checks found the canonical data files and active market
summary byte-identical, including no new decision/override files. Existing Action
Item statuses were not updated. Protected-state receipts, separate condition policy,
source-note enrichment, request journals and input/code fingerprints remain private
on the Mini and in the laptop copy under:

`output/valuation_review_20261106/scale_test_100_v1/refined_review_v2/`

The entry point is `index.html`; it links the 100-book report, scenario/physical-check
CSV downloads and saved-versus-collected comparison. Prior pilot reports remain
unchanged. No credentials or individual-book details are committed to GitHub.

## Validation and next gate

**697 tests passed on laptop and Mini.** Sixteen new cases cover deterministic
selection and exclusion of the earlier pilot, missing-ISBN used queries, actual
subprocess termination, recovery verification, all-100/no-result reporting,
checkpoint/evidence integrity, purchase-free scan identity, binding separation,
visible exclusions/source notes, explicit volumes and ranges, and placeholder
listing titles. Final artifact checks confirm 100 book sections, 253 unpublishable
scenarios, deferred grading, valid downloads, and matching input/code fingerprints.
Compilation and whitespace checks pass.

Operationally, the test supports a staged wider read-only run. It does not establish
an acceptable precision rate for all remaining books or authorize publication.
Continue with frozen cohorts, persisted budgets/progress, quota checks between
batches, and separate review outputs. Carry unresolved identity, missing/weak
evidence and wide spreads forward as exceptions. Keep all current estimates and
manual decisions protected until the owner reviews a publication proposal. Any
publication path needs separate preview/conflict/rollback testing before use.

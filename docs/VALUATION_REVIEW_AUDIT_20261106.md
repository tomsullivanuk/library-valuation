# Whole-library valuation review: audit and pilot readiness

Audited November 6, 2026 against the authoritative Mac Mini. Scope: code paths,
existing evidence, destination configuration presence, source-access documentation,
network-free rule reproductions, and a proposed 30-record pilot. No live listing
collection, credential transfer, estimate publication or catalog edits occurred.
Canonical CSV/JSON file hashes were identical before and after the audit.

## Current physical-library coverage

| Measure | Catalog records |
| --- | ---: |
| Physically inventoried, linked catalog records | 2,565 |
| Currently usable estimates | 1,443 |
| Without a usable estimate | 1,122 |
| With ISBN | 2,458 |
| Without ISBN | 107 |
| With any linked market summary | 1,944 |
| Without a linked market summary | 621 |
| Manually reviewed estimate overrides | 0 |

These count catalog records, not 2,727 physical copies or 2,521 distinct recorded
titles. Four unresolved physical identifications remain outside the linked-record
cohort and must remain explicit exceptions, not silently omitted from reporting.

Current active-record confidence: 1,443 moderate, 249 uncertain/outlier-sensitive,
117 thin, 62 ambiguous edition matches, 48 no market evidence, 25 source
unavailable, and 621 not researched. Of the linked summaries, 1,847 were generated
July 19 and 97 October 20. Summary generation time must not be mistaken for the
underlying listing observation date. The main raw AbeBooks baseline was observed
July 15 and eBay July 19. The workspace's “current” evidence status establishes
catalog compatibility, not that prices were checked recently.

## Reusable foundations

- Separate source observations, status rows, derived ranges, and manual reviews.
- eBay token refresh, bounded retry/backoff, crash recovery, per-book checkpoint
  parts, input fingerprints and deterministic materialization.
- Finite nonnegative price validation and refusal to combine mixed currencies.
- Explicit no-query, no-results and source-unavailable outcomes.
- Preserved source history, private outputs, and guarded local publication.
- Manual estimate identity protection and append-only history.

117 relevant existing collector/summary/checkpoint tests pass. That establishes
current behavior, not readiness of a new refresh policy or live API access.

## Findings and required changes before a live pilot

### 1. Select the completed inventory explicitly

The AbeBooks full-library path reads generated `library_catalog.csv` and requires
old research assessments; it does not derive its cohort from completed physical
inventory. The eBay path accepts every ID in its input summary. Applying a limit
takes the beginning of those cohorts; it is not a stratified pilot.

The combined saved summary contains 1,167 rows outside the active cohort. The
main raw baselines contain 3,154 AbeBooks and 3,201 eBay observation rows outside
it. These are valid historical records, not automatically duplicate or bad data.
Build a frozen cohort from authoritative inventory, retain catalog/holding identity
and input fingerprints, and report unresolved/unlinked holdings separately.

### 2. Establish source access on the Mini

All four required eBay environment variables are absent in the inspected remote
shell; `.env` is absent. The laptop credential file contains the required key names
(values were not displayed). Securely transfer only necessary credentials, load
them explicitly for the collector, then perform one bounded authentication/search
probe. Do not place credentials in the service plist, Git, reports or backups.
Their presence on the laptop is not proof that the credentials still work.

The AbeBooks collector fetches and parses search-page HTML; it is not an AbeBooks
API client. Its current website terms exclude automated data gathering and price
collection from the ordinary site license. Establish written permission or a
suitable licensed interface before reusing it for a new batch. The documented
Search Web Services have separate access/use conditions; availability and fit for
this project have not been established. Historical evidence can be replayed
without making new requests. See [AbeBooks terms](https://www.abebooks.com/docs/legal/termsandconditions.shtml)
and [Search Web Services terms](https://www.abebooks.com/docs/affiliateprogram/webservices/terms-printable.shtml).

The official eBay Browse API requires an application access token and supports
structured search. Confirm the application's current production entitlement,
marketplace and actual quota rather than assuming earlier access or a generic
published limit. See [Browse API](https://developer.ebay.com/develop/api/buy/browse_api)
and [call limits](https://www.developer.ebay.com/develop/api/buy/api_call_limits).
No live listing requests were sent during this audit.

### 3. Improve edition matching before confidence aggregation

AbeBooks assigns high match confidence based on having used an ISBN query; it
has not independently verified the returned listing's edition, binding or ISBN.
Title/author matching uses token overlap. The normalized row does not contain
sufficient structured edition facts to establish every match.

All 5,163 observed active-cohort rows in the main eBay baseline are deliberately
`unknown` match confidence. The client searches with keyword `q`, even for ISBNs;
it does not currently use structured GTIN search or retrieve edition-specific
item details. Buying options are recorded but not used by the summary. Completed
sales, shipping-inclusive comparisons and realized-sale values are not collected.

Add versioned match evidence and explicit acceptance/rejection reasons. Distinguish
query strategy from verified identity. Exclude incompatible formats, sets/lots,
signed/special copies, and unsuitable condition before calculating a range. Flag
unknown condition rather than inventing a discount. Do not silently promote the
existing eBay unknown-confidence rows to reliable comparisons.

### 4. Filter and deduplicate before calculating confidence

Synthetic, network-free reproductions confirmed:

| Input | Existing result | Required refresh behavior |
| --- | --- | --- |
| Same high-confidence listing repeated three times | Moderate confidence, $10–$10 | One distinct comparable; thin evidence |
| One high match at $10 and two low matches at $20/$25 | Moderate confidence, $10–$25 | Low matches excluded from the accepted range |
| Unavailable AbeBooks status plus three strong synthetic eBay matches | AbeBooks chosen, no range | Assess source eligibility separately; do not let an unavailable source suppress another usable source |
| Three observations dated 2020, summary generated in 2026 | Moderate confidence, $10–$12 | Apply explicit observation-age/run policy; retain old data as history |

No duplicate per-book/source/listing keys were found in either historical main
baseline. The repeated-listing result is an exposed aggregation weakness relevant
to merging refreshes, not a claim that the saved baseline is already duplicated.

The existing “trimmed” endpoints equal raw minimum/maximum; no actual trimming is
performed. Outlier detection uses price-spread ratios. Defaults collect only three
listings per book, while high-confidence classification requires at least five
listings and three high matches. More rows alone must not substitute for better
identity evidence or listing independence.

### 5. Separate source choice, freshness and publication

Any AbeBooks row, including an unavailable status row, takes precedence over eBay
in primary calculations. eBay is otherwise supplemental and cannot refine the
range. Changing this is a valuation-model change, not just rerunning collection.

Define a versioned accepted-comparable policy, per-source summaries and explicit
source-disagreement handling. Keep currencies separate and distinguish asking
ranges from expected proceeds. Preserve previous ranges when a refresh fails,
show their age, and create an exception rather than writing zero. Protect any
manual review added after this audit by fingerprinting and rechecking at publish.

AbeBooks currently collects in memory and publishes at the end, without the
per-book resume support available for eBay. Retain dated run directories, dedupe
by source/listing identity, distinguish observation times from summary times, and
exercise restart on both sources before scaling.

The service reads a fixed evidence path under `libib_inventory_20261020`. A new
run directory will not automatically become visible in the Library. Design a
validated active-evidence pointer or equivalent publication contract, plus a
rollback that preserves newer user decisions. Do not overwrite the historical
file in place as the refresh mechanism.

## Prepared pilot

A private `output/valuation_review_20261106/pilot_candidates.csv` contains exactly
30 distinct active catalog records, selected deterministically and exclusively:

| Stratum | Records |
| --- | ---: |
| Existing usable estimates: upper USD endpoint below $20 | 4 |
| Existing usable estimates: upper USD endpoint $20 to below $75 | 3 |
| Existing usable estimates: upper USD endpoint at least $75 | 3 |
| Missing/weak estimates with an ISBN | 8 |
| Existing edition/physical-format check or ambiguous match | 6 |
| Uncertain/outlier-sensitive evidence | 4 |
| Missing ISBN | 2 |

The outlier group includes *Time, creation and the continuum*. Edition/set/binding
flags are candidates for examination, not assertions that an edition or set is
confirmed. The pilot is deliberately diagnostic, not statistically representative
of the entire library. Do not extrapolate pilot price changes into a total value.

## Recommended sequence and acceptance

1. Replay saved evidence for the 30 records, adding adversarial duplicate, stale,
   weak-match, currency and source-outage fixtures. Agree expected outcomes before
   changing aggregation. Keep the old model results side by side.
2. Implement accepted-comparable matching, source selection, freshness and
   resumable run contracts, with explicit proposed/accepted/rejected status.
3. Verify credentials/access. Prefer an eBay-first live pilot if approved AbeBooks
   access is not available; use old AbeBooks evidence only as dated context.
4. Collect a bounded pilot (target up to 10 candidates per record, accepting fewer
   if justified). Set explicit search/detail request and retry budgets after the
   adapter design; check actual quota. No full-library collection or publication.
5. Inspect all 30 outcomes. Require no known wrong-edition/lot inclusions, evidence
   for each endpoint, separate currencies/sources, explanations for missing values,
   and flags for large changes (proposed trigger: over 50% or $25 at either endpoint;
   policy subject to pilot calibration, not a silent default).
6. On disposable copies, interrupt/resume; verify deterministic replay without
   duplicated evidence; inject publish failure and rollback; simulate a newer
   manual estimate between preview and save. Confirm original inputs, purchase and
   inventory history remain unchanged. Review the comparison before publishing.
7. Scale only after those gates pass. Report all 2,565 linked records plus unresolved
   physical holdings, successful estimates, retained old estimates, failures and
   physical checks explicitly; do not hide unsuccessful lookups from coverage.

## Private audit artifacts

The Mini retains `audit.json`, the pilot CSV, and input hashes under the private
output directory. A read-only reproduction script and copies of the results are
also retained in the laptop's ignored output directory. No individual-book pilot
list, credentials or full library data are included in this GitHub document.

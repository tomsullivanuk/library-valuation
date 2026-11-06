# Live 30-book valuation pilot

Completed November 6, 2026 on the authoritative Mac Mini. Source: eBay US Browse
API, active fixed-price listings. This was collection and review only: all
canonical CSV/JSON records and the Library's active market summary matched their
pre-run hashes. No estimates, manual decisions, purchase history or inventory
records were changed. No publication mechanism was added.

## Results

| Measure | Result |
| --- | ---: |
| Pilot books completed | 30 / 30 |
| Batch requests, including OAuth and fallbacks | 203 / 400 budget |
| Books with returned listing details | 29 |
| Successfully retrieved fixed-price detail records | 156 |
| Detail records with independently returned normalized ISBN | 143 |
| Detail records with recognized binding | 93 |
| Detail records with recognized condition grade | 149 |
| Books with plausible fresh candidate asking-price ranges | 26 |
| Verified replacement proposals | 0 |
| Published estimate changes | 0 |

The private observation file contains 158 rows: 156 detail observations, one
explicit no-results outcome, and one item-detail HTTP 404 outcome. The item that
became unavailable is retained as a status, not converted to a zero-valued book.
Six additional requests were used for the bounded authentication/search and
single-detail preflights before the main batch. The main batch completed without
a rate-limit or access interruption.

The 26 candidate ranges are diagnostic comparisons, grouped in the report by
seller-reported binding, condition and currency. They are not approved replacement
estimates. Target binding and physical condition are not supplied in the frozen
pilot manifest and have not been inferred from listings; the strict verified-range
policy therefore correctly leaves zero supported replacement proposals. Existing
Library estimates remain available unchanged while the candidate evidence is
reviewed. Missing or conflicting listing facts remain explicit.

## Source access and collection

Required eBay credentials were transferred securely to a private account-local
configuration outside the application tree, source control and backup archive
roots. Values, tokens, request headers and raw response payloads are not printed
or stored in pilot outputs. There is no need to copy the entire laptop `.env` or
place credentials in a startup plist.

The official [Browse API specification](https://developer.ebay.com/api-docs/master/buy/browse/openapi/3/buy_browse_v1_oas3.json)
was checked for GTIN search, fixed-price filtering, item details, product GTINs,
localized aspects, condition and product aspect groups. The live preflight
successfully returned ISBN, paperback binding, condition, author and publisher.

The collector uses structured GTIN search for valid ISBNs, with at most one ISBN
keyword fallback if no GTIN-indexed results are returned. Books without ISBNs use
title/author queries. At most 10 distinct valid item IDs per book are followed by
item-detail requests. Requests are paced; a persisted 400-request budget includes
OAuth, retries and fallbacks. This budget is a pilot cap, not a claim about the
application's quota. API access/rate failures pause the run rather than expanding
scope. AbeBooks was not queried; its access requirements remain unresolved.

## Normalized detail evidence

Allowlisted fields include listing reference/link and title, actual observation
time, asking price/currency, independently returned ISBNs, original and normalized
format, condition label/grade, bounded condition notes, author, publisher, year,
edition and buying options where returned. No ISBN, format or condition is invented
from the query or silently defaulted. ISBN-10 is normalized to equivalent ISBN-13;
conflicting identifiers or formats remain review exceptions. Generic “Used” is not
assigned a specific condition grade. Seller identity, account information, photos,
arbitrary descriptions and raw API payloads are omitted. Contact addresses/links
and long phone-like numbers are removed from retained condition notes.

The preview model now explicitly excludes conflicting detail metadata and examines
condition notes/edition labels for special-copy flags. The live workspace and its
existing market-summary calculation are not wired to this experimental model.

## Resume and review behavior

`valuation/live_valuation_pilot.py` stores atomic, private per-book search and
normalized detail checkpoints. A resumed run must match the pilot hash, ordered
identities, marketplace, environment and limits. Completed details are not queried
again. Concurrent workers are excluded by a file lock. Item response identities
are checked against requested IDs. Detail outcomes, source errors and no-results
cases remain distinct. Authentication gets one controlled refresh retry; limited
transient retry is budgeted. Unauthorized/rate-limited access pauses the run, with
only safe error type/status retained. No new paid service or permission was added.

`valuation/live_pilot_report.py` produces a separate HTML review, comparison CSV,
JSON decisions and summary. It checks the collected cohort hash, refuses to
replace an existing report, and cannot write to a canonical data directory. HTML
escapes source text, permits only eBay HTTPS listing links and separates missing
facts from returned facts. The comparison CSV escapes formula-like text cells.

## Verification

- **657 tests pass on laptop and Mini.** New coverage includes detail normalization,
  missing/conflicting identifiers and formats, generic/recognized condition,
  privacy allowlisting, fixed-price restrictions, API request accounting,
  authentication retry, GTIN fallback, bounded resume, response identity errors,
  no-results outcomes, unchanged inputs, report cohort checks and safe rendering.
- The 30-book run finished within its request budget, retaining all outcomes.
- Protected canonical data and active market-summary hashes matched after the run.
- The private report was checked in a browser: 30 book sections and 158 listing/
  outcome table rows, saved ranges, returned identifiers and grouped comparisons.
  The temporary local review server was stopped afterward.

Private artifacts are retained on the Mini and copied to the laptop under
`output/valuation_review_20261106/live_ebay_pilot_v1/`:

- `checkpoint.json` and `observations.csv` retain normalized source evidence;
- `protected_state_verification.json` records unchanged-state hashes;
- `review/review.html` provides the book-by-book comparison;
- `review/comparison.csv`, `review/review.json` and `review/summary.json` support
  inspection and reproducibility.

These files and the individual-book cohort remain ignored, outside GitHub.

## Remaining review before expansion or publication

Review the 26 candidate comparisons and the four books without sufficiently
matched candidate prices. Establish target binding/condition from authoritative
records where available and retain unknowns. Decide whether any explicitly stated
condition scenarios are acceptable for advisory ranges before relaxing the strict
verification policy; do not tune thresholds merely to increase coverage.

Calibrate the comparison/source rules against reviewed cases, resolve missing or
conflicting evidence, and confirm expected outcomes before expanding to the whole
library. Publishing still requires a separate validated preview/acceptance design,
manual-review conflict checks and rollback tests on disposable state. No whole-
library batch, estimate publication, or AbeBooks refresh has been performed.

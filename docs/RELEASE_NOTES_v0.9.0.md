# v0.9.0 — Full-Library eBay Baseline

Library Valuation v0.9.0 makes production eBay collection practical for the
whole assessed library. A long-running collection can now be interrupted,
checked, and resumed without repeating completed books or treating a partial
run as complete.

## What is new

- A production-guarded full-library eBay workflow with safe pacing, bounded
  retries, progress reporting, and explicit resume and restart controls.
- Crash-safe checkpoints with a versioned run manifest, per-book status ledger,
  and immutable observation parts.
- Network-free regeneration of eBay observation CSV/XLSX files from a validated
  checkpoint.
- Full multi-source summary, reviewer workbook, and HTML report generation with
  AbeBooks and eBay evidence kept distinct and clearly labeled.

## Production validation

The release was validated across all 3,014 assessed books. The run completed
3,014 ISBN-13 searches in about 82 minutes and produced 8,293 unique active
listings for 2,881 books, plus 133 no-results rows. It required no retries,
rate-limit recovery, or token refreshes.

The resulting 8,426 eBay rows were combined with 8,311 AbeBooks rows. The final
3,014-book summary, seven-tab reviewer workbook, and five-queue HTML report all
reconciled to their source evidence. AbeBooks ranges, confidence, and review
recommendations were unchanged.

## Privacy and safe operation

Seller identity is suppressed throughout the eBay client, checkpoint,
observations, notes, summaries, workbook, and report. Every production eBay
seller field was blank. Credentials, OAuth tokens, headers, expiration data,
and raw API responses are not written to checkpoints or generated evidence.

The checkpoint and generated CSV, XLSX, workbook, and HTML files remain ignored
local artifacts. They are not durable market history and must not be committed.

## Operational workflow

The release supports five steps:

1. Collect or resume with `collect-full-library-ebay-observations`.
2. Validate and export with `materialize-full-library-ebay-observations`.
3. Combine sources with `summarize-market-evidence`.
4. Build the source-aware workbook with `build-abebooks-review-workbook`.
5. Build the source-aware HTML report with `build-abebooks-review-report`.

Production collection requires configured eBay credentials and explicit
confirmation. Resume compatibility is checked before work begins; restart is
explicit and does not silently discard the only checkpoint.

## Interpretation and limitations

eBay remains supplemental active-listing asking-price evidence. AbeBooks
remains the authoritative source for core market ranges, confidence, and review
recommendations. Prices from the two sources are not pooled.

This release is not an appraisal and does not estimate fair market value,
realized sale price, or expected proceeds. It does not include sold/completed
listings, shipping-inclusive prices, currency conversion, or automated edition
matching. eBay match confidence remains `unknown`; lower-overlap, edition,
condition, and price-extreme evidence still requires human review.

## What comes next

- v0.10.0: Libib physical-inventory integration.
- v0.11.0: Library Explorer and Action Center.
- v0.12.0: automated monthly refresh with reviewed freshness and provenance
  rules.

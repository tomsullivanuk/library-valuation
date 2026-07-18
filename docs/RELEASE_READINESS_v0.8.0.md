# Library Valuation v0.8.0 Production eBay Readiness

## Status

**The bounded production targeted-collection path is validated after seller
suppression. Broader production collection remains deferred.**

This record covers v0.8.0 PR1 and PR2 only. It does not approve full-library
collection or change valuation, review, workbook, report, or monthly-import
behavior.

## Baseline

- Released baseline: `v0.7.0` at
  `a4a8f315339feafd0e1472c5b45ce5bab10e906a`.
- Privacy baseline: PR1 at
  `1829c214ede7cde3ca5bb3073fecd75713c80346`.
- PR1 removes `seller_username` from normalized eBay listing objects, ignores
  seller data in item summaries, leaves eBay observation `seller` blank, and
  excludes seller identity from `match_notes`.

## Production Access Check

On 2026-07-18, production `EBAY_US` acquired an OAuth application token and
completed one bounded Browse search. The query returned four results; the three
displayed prices were 379.49, 333.10, and 438.10 USD.

An earlier `invalid_client` response was caused by a typo in the local
Production Client ID. It was not a code, TLS, eBay compliance, Production Cert
ID, or authorization-header defect. Credentials and token responses remained
local and were not written to repository artifacts.

## Targeted Smoke Configuration

The existing `collect-targeted-ebay-observations` workflow ran with:

- production environment and `EBAY_US`;
- generated `output/full_abebooks_market_evidence_summary.csv` input;
- the default `review_for_possible_sale` queue;
- two deterministically selected books;
- ISBN-13 query strategy for both books;
- at most three results per book;
- a one-second inter-request delay; and
- ignored `output/production_smoke_ebay_observations.csv/.xlsx` outputs.

No full-library request, summary integration, workbook/report generation, or
monthly-import operation was run.

## Safe Results

The collection completed without a client or source error and produced four
observation rows:

- 4 `observed` and 0 status rows;
- 4 rows from `ebay_active_listings`;
- 4 USD item prices: 389.30, 333.10, 379.49, and 326.23;
- 4 item IDs, listing URLs, titles, conditions, and buying-option contexts;
- marketplace and item-location country retained in source-specific notes;
- query and `isbn13` strategy retained;
- match confidence `unknown` for every row;
- blank shared `seller` field for every row; and
- no seller identity or seller label in any `match_notes` value.

The CSV and XLSX each contained the canonical 25 fields and four data rows.
Generated files remain ignored and are not release evidence to commit.

## Privacy and Artifact Checks

- Seller username is absent from the normalized eBay client object.
- Seller data returned by eBay is ignored during normalization.
- eBay observation `seller` is blank.
- Seller identity is absent from eBay `match_notes`.
- No raw live API response was retained.
- No credentials, tokens, or authorization headers were written.
- `.env` and generated production CSV/XLSX files remain ignored.

## Interpretation and Remaining Gates

This smoke run validates production OAuth, bounded Browse requests,
source-specific normalization, observation adaptation, seller suppression, and
paired generated-file writing. It establishes that the privacy-hardened path can
produce usable active-listing observation rows.

It does not establish representative eBay coverage, price quality, edition
matching, shipping-inclusive cost, currency conversion, sold/completed prices,
or reviewed match confidence. Active listings remain seller asking-price
evidence, not appraisals, fair market value, realized prices, or expected
proceeds. Broader or full-library production collection requires a separate
review and explicit approval.

# Library Valuation v0.8.0 Production eBay Readiness

## Status

**Ready for the v0.8.0 tag and GitHub Release after PR6 is committed.**

The privacy-hardened bounded production path, representative evidence, reviewer
workbook, and static HTML report are validated. This release does not approve
full-library collection or change AbeBooks range, confidence, recommendation,
Research Assessment, durable-data, or monthly-import behavior.

## PR Checklist

- [x] PR1 — remove seller username from normalized eBay evidence.
- [x] PR2 — validate and document the bounded production targeted smoke run.
- [x] PR3 — complete representative 100-book production validation.
- [x] PR4 — add and validate source-aware reviewer workbook fields.
- [x] PR5 — add and validate source-aware static HTML report fields.
- [x] PR6 — finalize changelog, release notes, roadmap, and readiness records.

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

## PR3 Representative Production Validation

PR3 used an ignored deterministic 100-book cohort spanning three reviewer
queues: 34 possible-sale, 33 manual-research, and 33 edition/condition books.
The existing targeted-book ceiling was raised from 50 to 100 solely to permit
this bounded validation; 101 remains invalid.

The production collector completed 100 ISBN-13 searches with a maximum of three
results per book and a one-second delay. It wrote ignored paired observation
files containing 242 rows: 229 `observed` listings across 87 books and 13
`no_results` rows. There were no `no_query` or `source_unavailable` outcomes.

All observed rows included USD item price, item ID, listing URL, title, and
condition. Prices ranged from 4.43 to 475.87 USD with a median of 57.87. These
exclude shipping and are distribution diagnostics, not valuation conclusions.
All 242 seller fields were blank, no notes mentioned seller identity, and all
match confidence remained `unknown`.

Title-token review found at least 50% catalog-title overlap in 224 of 229 listing
rows. The five lower-overlap titles were mostly explainable by truncation,
translation, or format variation, while a bundle-like listing confirms that
human match review remains necessary.

The ignored multi-source summary contained 3,014 rows, including 100 mixed
AbeBooks/eBay books. It recorded 229 eBay listings and 13 eBay statuses without
changing any catalog item's AbeBooks core range, confidence, or recommendation.
`market_range_source` remained `abebooks` throughout.

This representative evidence is useful enough to support a future, explicitly
scoped reviewer-facing source-context design. It does not authorize automatic
matching, price pooling, workbook/report changes, broader production cadence,
or full-library collection. Detailed metrics and interpretation are recorded in
[`PRODUCTION_EBAY_VALIDATION_v0.8.0.md`](PRODUCTION_EBAY_VALIDATION_v0.8.0.md).

## PR4 Source-Aware Reviewer Workbook

PR4 extends the existing generated reviewer workbook when its input contains
multi-source summary fields. The four queue sheets add five compact columns:
Evidence Sources, eBay Listings, eBay Price Range, eBay Status, and Source Price
Comparability. Existing AbeBooks range, confidence, and recommendation columns
remain unchanged.

Evidence Detail retains the raw source-mix, core-range-source, comparability,
and AbeBooks/eBay count, currency, and price fields. Run Summary adds source-mix,
eBay listing/status, rows-with-eBay, core-range-source, and comparability counts.
Field Definitions explains the supplemental active-listing boundary, excluded
shipping, absent conversion, unknown eBay match confidence, human review need,
non-appraisal caveat, and seller-identity suppression.

Legacy AbeBooks-only summaries remain valid inputs and render their existing
tabs with conservative source defaults. No workbook output is durable or read
by monthly import.

## PR5 Source-Aware HTML Report

PR5 aligns the static HTML reviewer artifact with the workbook. For source-aware
input, every reviewer queue adds Evidence Sources, eBay Listings, eBay Price
Range, eBay Status, and Source Price Comparability, using the same compact
display helpers as the workbook. The report also adds source-aware counts and
interpretation/caveat text. AbeBooks stays the core range source for mixed rows;
eBay is supplemental active-listing item-price evidence with shipping excluded,
no conversion or pooling, unknown match confidence, and required human review.
Seller identity is not stored or displayed. Legacy AbeBooks-only input retains
the existing report layout. Generated HTML remains ignored and non-durable.

## Reviewer Artifact Validation

The representative workbook was generated from the 3,014-row multi-source
summary. All four reviewer tabs contained the source-aware columns; all 87 books
with observed eBay listings had matching compact ranges, all 13 status-only
books displayed `No listings`, and no AbeBooks/core range changed. Run Summary
reported 100 mixed-source books, 229 listings, and 13 statuses.

The representative HTML report exposed the same five fields in all five review
sections. It displayed eBay ranges for the same 87 books and status-specific
no-listings text for the same 13 books, with zero eBay range mismatches, zero
blank ranges for observed books, and zero AbeBooks/core range mismatches.

Legacy AbeBooks-only workbook and HTML inputs remain supported. No reviewer
artifact changes canonical evidence, recommendations, or durable state.

## Seller Privacy Validation

- Seller username is absent from normalized client objects.
- All 242 representative observation seller fields were blank.
- No representative `match_notes` value contained seller identity.
- Workbook and HTML scans found no seller identity.
- No raw API responses, credentials, tokens, or authorization headers were
  retained or committed.

## Generated-Artifact Policy

Production cohorts, observations, multi-source summaries, reviewer workbooks,
HTML reports, and smoke outputs remain ignored under `output/`. They are
generated, replaceable, non-durable artifacts and do not feed the monthly Amazon
import. `.env` remains ignored; raw API responses are not retained.

## Known Limitations and Deferred Work

- eBay active listings are asking-price evidence, not sold/completed evidence.
- Shipping is excluded; currency conversion and source-price pooling are absent.
- eBay match confidence remains `unknown`; human edition/title review is needed.
- The 100-book production study does not establish a full-library cadence.
- Sold/completed evidence, production full-library collection, improved matching
  heuristics, automated edition matching, shipping-aware prices, currency
  normalization, additional sources, and richer reviewer workflow are deferred.
- Outputs are not appraisals, fair-market-value estimates, realized-sale
  estimates, expected proceeds, or pricing guarantees.

## Release Validation Checklist

- [x] Production `EBAY_US` OAuth token and bounded Browse request succeeded.
- [x] Representative 100-book production validation completed.
- [x] Seller suppression verified from client normalization through artifacts.
- [x] Workbook and HTML source-aware projections reconciled to the summary.
- [x] AbeBooks-only backward compatibility covered by regression tests.
- [x] Full automated test suite passed.
- [x] Python compilation and `git diff --check` passed.
- [x] Five release CLI help paths inspected.
- [x] Credential/token/header audit found no committed sensitive material.
- [x] `.env` and generated production artifacts confirmed ignored.

## Tagging Checklist

- [ ] Commit PR6 with only stable release documentation.
- [ ] Confirm a clean working tree at the release commit.
- [ ] Create annotated tag `v0.8.0` at the PR6 commit.
- [ ] Verify the tag target and release title
  `v0.8.0 — Production eBay Validation & Reviewer Integration`.
- [ ] Push the release commit and tag after explicit approval.

## GitHub Release Checklist

- [ ] Create the GitHub Release from tag `v0.8.0`.
- [ ] Use [`RELEASE_NOTES_v0.8.0.md`](RELEASE_NOTES_v0.8.0.md) as the release
  description or source text.
- [ ] Confirm the non-appraisal notice and deferred boundaries are visible.
- [ ] Do not attach `.env`, credentials, tokens, raw responses, or ignored
  production/generated artifacts.
- [ ] Verify links and published tag target before marking the release final.

# Library Valuation v0.8.0 Release Notes

## v0.8.0 — Production eBay Validation & Reviewer Integration

Version 0.8.0 moves the eBay active-listing integration from experimental
infrastructure to privacy-hardened, production-validated reviewer tooling. It
preserves the conservative valuation behavior released in v0.7.0: AbeBooks is
the primary evidence source and remains the core range source whenever it is
present; eBay is supplemental asking-price context only.

## Highlights

- Validated production eBay OAuth and Browse access for `EBAY_US`.
- Completed a bounded, representative 100-book production study.
- Removed seller username from normalized eBay results and generated evidence.
- Added compact source-aware evidence to the reviewer workbook and HTML report.
- Preserved AbeBooks ranges, confidence, recommendations, Research Assessments,
  monthly imports, and durable catalog/acquisition data.

## Production Validation

The access check acquired a production application token and completed a Browse
search after a typo in the local Production Client ID was corrected. The earlier
`invalid_client` response was local configuration, not a code, TLS, compliance,
Production Cert ID, or authorization-header defect.

The representative cohort contained 34 possible-sale, 33 manual-research, and
33 edition/condition books. One hundred ISBN-13 searches, capped at three
results and paced one second apart, produced:

- 242 observation rows;
- 229 observed listings across 87 books;
- 13 source-specific `no_results` rows;
- 229 unique item IDs and listing URLs; and
- USD item prices from 4.43 to 475.87, with median 57.87.

All match confidence remained `unknown`. Title-token review found at least 50%
catalog-title overlap in 224 of 229 listings; the five lower-overlap results
reinforce the need for human title and edition review.

The 3,014-row representative multi-source summary contained 100 mixed-source
and 2,914 AbeBooks-only books. All core ranges used AbeBooks, and comparison
with the AbeBooks baseline found no changes to ranges, confidence, or review
recommendations.

## Reviewer Workbook Enhancements

For source-aware summaries, Review Queue, Possible Sale, Manual Research, and
Edition Condition Review add:

- Evidence Sources;
- eBay Listings;
- eBay Price Range;
- eBay Status; and
- Source Price Comparability.

Evidence Detail retains source-specific audit fields. Run Summary reports source
mix, listing/status totals, coverage, core range source, and comparability. Field
Definitions explains the active-listing, privacy, shipping, currency, matching,
and non-appraisal boundaries. Legacy AbeBooks-only summaries remain supported.

## HTML Report Enhancements

All five HTML reviewer sections conditionally show the same compact source-aware
columns. The report adds source counts, field guidance, privacy language, and
pricing caveats. Representative verification found 87 populated eBay ranges,
13 source-specific no-listings statuses, zero eBay-range mismatches, zero blank
ranges for observed books, and zero AbeBooks/core-range mismatches. Legacy
AbeBooks-only input retains the original report layout.

## Privacy Improvements

- Seller username is absent from normalized eBay listing objects.
- Seller data returned in item summaries is ignored.
- Every eBay observation `seller` field is blank.
- Seller identity is absent from `match_notes`, workbooks, and HTML reports.
- Credentials, tokens, authorization headers, and raw API responses are not
  retained in generated artifacts or committed to the repository.

## Operational Workflow

Production work remains explicit and bounded:

1. Load production credentials from ignored local configuration.
2. Optionally verify one bounded request with `ebay-access-check`.
3. Collect no more than 100 targeted reviewer-priority books.
4. Combine explicit AbeBooks and eBay observation inputs into a generated
   multi-source summary.
5. Build source-aware workbook and HTML reviewer projections.
6. Review listing identity manually before relying on eBay evidence.

This workflow does not authorize automatic or full-library eBay collection.

## Commands

```bash
.venv/bin/python library_pipeline.py ebay-access-check \
  --query "Springer Handbook of Spacetime" \
  --limit 3

.venv/bin/python library_pipeline.py collect-targeted-ebay-observations \
  --summary output/full_abebooks_market_evidence_summary.csv \
  --output output/targeted_ebay_observations.csv \
  --limit-books 100 \
  --max-results-per-book 3 \
  --delay 1

.venv/bin/python library_pipeline.py summarize-market-evidence \
  --observations output/full_abebooks_market_observations.csv \
  --observations output/targeted_ebay_observations.csv \
  --output-csv output/multisource_market_evidence_summary.csv \
  --output-xlsx output/multisource_market_evidence_summary.xlsx

.venv/bin/python library_pipeline.py build-abebooks-review-workbook \
  --summary output/multisource_market_evidence_summary.csv \
  --output-xlsx output/source_aware_review_workbook.xlsx \
  --data-dir data

.venv/bin/python library_pipeline.py build-abebooks-review-report \
  --summary output/multisource_market_evidence_summary.csv \
  --output-html output/source_aware_review_report.html \
  --data-dir data
```

The eBay commands require the existing `EBAY_CLIENT_ID`,
`EBAY_CLIENT_SECRET`, `EBAY_MARKETPLACE_ID`, and `EBAY_ENVIRONMENT` variables.
Never commit their values.

## Generated Artifacts

Observation CSV/XLSX files, multi-source summaries, reviewer workbooks, HTML
reports, production cohorts, and smoke artifacts remain ignored under
`output/`. They are generated, replaceable, non-durable views and are not inputs
to the monthly Amazon import. Raw eBay responses are not retained.

## Validation

Release validation covers the complete automated test suite, Python bytecode
compilation, whitespace checks, all five relevant CLI help paths, intended-file
review, credential-pattern scanning, seller-identity scanning, and confirmation
that `.env` and production artifacts remain ignored.

## Known Limitations

- eBay evidence consists of active item asking prices, not completed sales.
- Shipping is excluded.
- Currency conversion is not performed and source prices are not pooled.
- eBay match confidence remains `unknown`.
- ISBN searches can return a different edition, format, translation, or bundle.
- Human identity, edition, format, and condition review remains required.
- The production study is representative and bounded, not full-library.

## Deferred Work

- Sold/completed eBay evidence.
- Production full-library eBay collection and operating cadence.
- Improved match-confidence heuristics and automated edition matching.
- Shipping-aware pricing and currency normalization.
- Additional market-evidence sources.
- Richer reviewer workflow and durable reviewer decisions.

## Non-Appraisal Notice

All marketplace prices are observed asking-price evidence. Outputs are not
appraisals, fair-market-value estimates, realized-sale estimates, expected
proceeds, pricing guarantees, or investment advice. AbeBooks remains primary;
eBay evidence is supplemental and requires human review.

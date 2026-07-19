# Full-Library Multi-Source Reconciliation — v0.9.0

## Purpose

PR7 deterministically materialized the completed production eBay checkpoint,
combined it with the existing full-library AbeBooks observations, regenerated
the source-aware summary, workbook, and HTML report, and reconciled every
generated artifact. No eBay network collection was performed.

AbeBooks remains the core range source. eBay remains supplemental active-
listing item-price evidence with excluded shipping, no currency conversion,
blank sellers, and `unknown` match confidence. No matching, valuation,
confidence, recommendation, or outlier-removal rule changed.

## Commands and Generated Artifacts

```bash
.venv/bin/python library_pipeline.py \
  materialize-full-library-ebay-observations \
  --checkpoint output/full_library_ebay_baseline_v0_9_0 \
  --output output/full_ebay_market_observations.csv

.venv/bin/python library_pipeline.py summarize-market-evidence \
  --observations output/full_abebooks_market_observations.csv \
  --observations output/full_ebay_market_observations.csv \
  --output-csv output/full_multisource_market_evidence_summary.csv \
  --output-xlsx output/full_multisource_market_evidence_summary.xlsx

.venv/bin/python library_pipeline.py build-abebooks-review-workbook \
  --summary output/full_multisource_market_evidence_summary.csv \
  --output-xlsx output/full_multisource_review_workbook.xlsx \
  --data-dir data

.venv/bin/python library_pipeline.py build-abebooks-review-report \
  --summary output/full_multisource_market_evidence_summary.csv \
  --output-html output/full_multisource_review_report.html \
  --data-dir data
```

The materializer validates manifest, ledger, and part integrity; requires one
valid part per ledger item; reads parts in ordinal order; preserves canonical
rows and observation IDs; and rejects catalog mismatches, duplicate observation
IDs, and duplicate observed listing URLs. It has no network dependency.
Repeated runs produced byte-identical CSV files and XLSX archives with identical
member names and content; only ZIP container timestamps varied.

Generated and ignored files are:

- `output/full_ebay_market_observations.csv`
- `output/full_ebay_market_observations.xlsx`
- `output/full_multisource_market_evidence_summary.csv`
- `output/full_multisource_market_evidence_summary.xlsx`
- `output/full_multisource_review_workbook.xlsx`
- `output/full_multisource_review_report.html`

## eBay Materialization Reconciliation

| Metric | Result |
| --- | ---: |
| Checkpoint candidates / parts | 3,014 / 3,014 |
| Total canonical rows | 8,426 |
| Observed listing rows | 8,293 |
| No-results rows | 133 |
| Distinct books | 3,014 |
| Observed books | 2,881 |
| No-results books | 133 |
| Unique observation IDs | 8,426 |
| Duplicate observation IDs | 0 |
| Unique observed listing URLs | 8,293 |
| Duplicate listing URLs | 0 |
| Currency | 8,293 USD listings |
| Nonblank sellers | 0 |

No part was missing, malformed, orphaned, or duplicated. All status rows were
preserved and excluded from listing-price calculations.

## Combined Evidence Reconciliation

The combined input contains 16,737 observation rows: 8,311 AbeBooks rows and
8,426 eBay rows. AbeBooks contains 8,193 observed listings, 77 no-results rows,
and 41 source-unavailable rows; eBay contains 8,293 observed listings and 133
no-results rows.

| Observed-source coverage | Books |
| --- | ---: |
| AbeBooks observed | 2,896 |
| eBay observed | 2,881 |
| Both observed | 2,769 |
| AbeBooks-only observed | 127 |
| eBay-only observed | 112 |
| Neither source observed | 6 |

The summary contains exactly 3,014 unique catalog IDs. All rows record both
sources as checked and `market_range_source=abebooks`. Source-price
comparability is 2,769 same-currency separate summaries, 239 single-source
currency, and 6 no-priced-listing rows. All 133 eBay no-results cases have a
source status and no eBay price range; all 2,881 eBay-observed books have a
complete minimum/median/maximum range.

Market confidence distribution:

- `moderate_confidence_market_evidence`: 2,189
- `unknown_market_confidence`: 376
- `thin_market_evidence`: 211
- `ambiguous_edition_match`: 120
- `no_market_evidence`: 77
- `source_unavailable`: 41

Review recommendation distribution:

- `market_evidence_sufficient`: 2,012
- `manual_market_research_needed`: 587
- `review_for_possible_sale`: 177
- `review_edition_or_condition`: 115
- `no_action_needed`: 58
- `fallback_research_priority`: 57
- `metadata_cleanup_needed`: 8

Every AbeBooks listing count, currency, core minimum/median/maximum, confidence,
likely range, recommendation, reason, and outlier-sensitivity value matches the
pre-eBay full-library summary. There are zero core-semantic differences.

## Reviewer Artifact Reconciliation

The workbook contains 3,014 unique book rows in both `Review Queue` and
`Evidence Detail`, with zero missing or duplicate catalog IDs. Queue tabs
contain 177 Possible Sale rows, 652 Manual Research/fallback/metadata rows, and
115 Edition Condition rows. All five source-aware display fields match the
summary exactly, as do core range, confidence, listing-count, and recommendation
fields. All seven workbook tabs rendered successfully and no formula-error
strings were found.

The HTML report intentionally presents the five actionable queues rather than
all sufficient/no-action books. It contains exactly 944 unique actionable books
across five tables: 177 possible-sale, 587 manual-research, 115 edition-review,
57 fallback, and 8 metadata-cleanup rows. There are zero missing, extra, or
duplicate actionable IDs and zero source-label, eBay count/range/status, or
comparability discrepancies against the workbook/summary. Non-appraisal,
non-fair-market-value, non-realized-sale, and seller-suppression language is
present.

## Lower-Title-Overlap Review

The existing broad diagnostic identified 249 of 8,293 listings below half
catalog-title-token overlap. A bounded sample included low and high prices,
source disagreements, shortened titles, and questionable results:

- `E=mc[super 2]` versus `E=mc2: A Biography...` is largely a markup/tokenization
  artifact and appears bibliographically plausible.
- `Total German...Michel Thomas Method` and `Spanish Grammar Beginner...
  Advanced Levels` use shortened marketplace titles; format/edition still needs
  review.
- `Calculus Vol-2...` versus `Calculus Volume 2 by Apostol` is an abbreviation
  case but requires edition confirmation.
- `An Aristotelian Realist Philosophy Of Mathematics...` is truncated in the
  marketplace title and has a large eBay/AbeBooks disagreement; it should be
  reviewed, not automatically rejected.
- `Statistical evidence` returned a series-only title for one listing, making
  that result genuinely questionable.
- the Hilbert lectures result refers to foundations of geometry and a different
  year span than the catalog title, suggesting a potentially different volume.
- `The Second World War (Six Volume Boxed Set)` returned shortened titles that
  may not establish the boxed-set format.

The diagnostic remains descriptive. No listing was removed or relabeled, and
match confidence remains `unknown`.

## Price-Extreme and Source-Disagreement Review

The $1.09 minimum (`Behind the Beautiful Forevers`) has a strongly aligned
title but is an asking-price extreme. The $999.51 maximum (`Sapiens`) also has a
strongly aligned title but is an obvious asking-price outlier. `Parts of
classes` has an exact-title $500 eBay listing against a $5.50 AbeBooks median,
while `How science works` has a $5.78 eBay median against a $125.15 AbeBooks
median and a wide internal eBay range. These cases show why sources remain
separate and why item prices are not valuation anchors.

No extreme or disagreement changed AbeBooks core ranges, confidence, or review
recommendations. Reviewer artifacts expose separate source counts, eBay ranges,
statuses, and comparability for human review; no automatic outlier exclusion was
introduced.

## Privacy and Interpretation Boundaries

All 8,426 eBay seller fields are blank and no notes contain seller identity.
Generated files and checkpoint state contain no configured Client ID or secret,
OAuth token, authorization or response header, expiration metadata, or raw API
response. Outputs remain asking-price research evidence, not appraisals, fair
market value, realized-sale evidence, or expected proceeds.

All generated artifacts remain ignored, untracked, local, and non-durable.

## Remaining v0.9.0 Work

The remaining release PR should finalize release notes/readiness, commands,
known limitations, privacy and artifact audits, tag/release checklists, and the
final confirmation that generated outputs remain outside version control.

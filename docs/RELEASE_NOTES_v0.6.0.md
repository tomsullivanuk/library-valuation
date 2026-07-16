# Library Valuation v0.6.0 Release Notes

## Overview

Library Valuation v0.6.0 delivers the **Full AbeBooks Baseline & Review
Artifacts** workflow. It extends the existing market-evidence summary from
bounded validation samples to the full assessed catalog and adds reviewer-facing
Excel and static HTML artifacts.

The release remains AbeBooks-only. The source-integration spike evaluated paths
beyond AbeBooks and recommended that eBay active listings be handled as the
v0.7.0 theme rather than rushed into this release.

## What Changed

- Added conservatively paced full-library AbeBooks observation collection with
  `--limit`, delay, result-count, data-directory, and output-path controls.
- Added distinct full-library observation and Market Evidence Summary outputs.
- Added an AbeBooks review workbook with Review Queue, Possible Sale, Manual
  Research, Edition / Condition Review, Evidence Detail, Run Summary, and Field
  Definitions sheets.
- Added latest-acquisition possession context to generated review artifacts.
- Added a static, self-contained HTML report with tabbed queues, queue-specific
  guidance, acquisition-year prompts, combined AbeBooks ranges, a Field Guide,
  documented sort order, report metadata, and caveats.

## Full-Library Workflow

```bash
.venv/bin/python library_pipeline.py collect-full-library-abebooks-observations \
  --output-dir output \
  --data-dir data \
  --delay 2 \
  --max-results-per-book 3

.venv/bin/python library_pipeline.py summarize-market-evidence \
  --observations output/full_abebooks_market_observations.csv \
  --output-csv output/full_abebooks_market_evidence_summary.csv \
  --output-xlsx output/full_abebooks_market_evidence_summary.xlsx

.venv/bin/python library_pipeline.py build-abebooks-review-workbook \
  --summary output/full_abebooks_market_evidence_summary.csv \
  --output-xlsx output/full_abebooks_review_workbook.xlsx \
  --data-dir data

.venv/bin/python library_pipeline.py build-abebooks-review-report \
  --summary output/full_abebooks_market_evidence_summary.csv \
  --output-html output/full_abebooks_review_report.html \
  --data-dir data
```

All files under `output/` are generated, ignored/untracked artifacts. They are
not canonical catalog, acquisition, assessment, or review state.

## What Did Not Change

- Market Evidence Summary aggregation, market confidence, outlier sensitivity,
  conservative ranges, or review recommendations.
- AbeBooks lookup and parsing behavior used by existing collection workflows.
- Research Assessment scoring, signals, weights, bands, or persisted records.
- Monthly Amazon import behavior or durable data schemas.

## Important Interpretation Limits

AbeBooks asking prices are not appraisals, fair market value, realized sale
prices, or expected sale proceeds. Edition, condition, dust jacket, signature,
seller credibility, and physical possession can materially affect value. The
review artifacts prioritize human attention; they do not make sale decisions.

eBay and other independent market sources are not included in v0.6.0.

## Validation

Release readiness includes the complete automated test suite, Python
compilation, whitespace checks, CLI help verification, full-baseline artifact
generation, review-artifact checks, and generated/durable boundary review. See
`docs/RELEASE_READINESS_v0.6.0.md` for the acceptance record.

## Next Direction

The recommended v0.7.0 theme is **eBay Active Listings Integration**: confirm
credentials and production access, add an isolated opt-in adapter, and preserve
source and evidence-type distinctions before adding cross-source comparisons.

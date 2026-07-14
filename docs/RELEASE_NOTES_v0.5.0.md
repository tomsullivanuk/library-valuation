# Library Valuation v0.5.0 Release Notes

## Overview

Library Valuation v0.5.0 introduces a market-evidence-first generated workflow.
It transforms source-specific market observations into a source-neutral,
per-book summary of evidence coverage, confidence, asking-price-derived range,
and recommended human review.

Market observations are primary evidence when usable. Existing Research Signals
remain fallback, uncertainty, metadata-cleanup, and review-prioritization
context; they are not treated as market prices.

## What Changed

- Added the versioned Market Evidence Summary schema and CSV/XLSX artifacts.
- Added deterministic aggregation of listing and status observations.
- Added market confidence and outlier-sensitivity classifications.
- Added a cautious, single-currency asking-price-derived range prototype.
- Added review recommendations and fallback Research Assessment priority.
- Added stable reason codes and generated provenance fields.

## New Workflow

After generating `output/market_observations.csv`, run:

```bash
python3 library_pipeline.py summarize-market-evidence \
  --observations output/market_observations.csv \
  --output-csv output/market_evidence_summary.csv \
  --output-xlsx output/market_evidence_summary.xlsx
```

`market_observations` contains source-specific listing and status rows.
`market_evidence_summary` contains source-neutral per-book coverage,
classification, range, and review guidance. Both remain generated output.

## What Did Not Change

- Research Assessment scoring, signals, weights, or bands.
- Persisted Research Assessments, catalog data, acquisitions, or Collector
  Reviews.
- Monthly `update-library` behavior.
- AbeBooks collection behavior.
- The existing Collector Workbook generator.

## Important Interpretation Limits

The prototype uses seller asking prices. Its ranges are not appraisals, fair
market value, realized sale prices, definitive valuations, or guarantees of
sale proceeds. Mixed currencies are not converted or combined. Edition and
condition matching remain lightweight, and uncertain evidence is routed to
human review instead of receiving false precision.

## Validation

Release readiness includes the complete automated test suite, Python
compilation, whitespace checks, CLI option verification, Markdown-link checks,
and generated-artifact boundary review. See
`docs/RELEASE_READINESS_v0.5.0.md` for the acceptance record.

## Next Direction

Add independent market sources and completed-sale evidence, improve edition and
condition comparison, and calibrate the initial deterministic thresholds on a
broader evidence base before treating the prototype as mature.

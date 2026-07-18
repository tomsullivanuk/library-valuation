# Library Valuation v0.7.0 — eBay Active Listings Integration

## Summary

Library Valuation v0.7.0 adds a cautious, bounded eBay active-listing path next
to the existing AbeBooks baseline. It validates sandbox OAuth and Browse API
access, normalizes active listings into the existing observation schema, creates
targeted generated observation artifacts, and adds source-aware multi-source
summary fields.

eBay remains supplemental asking-price evidence. The release does not claim
production access, sold-price evidence, appraisal capability, or representative
sandbox listing quality.

## What Changed

- Added environment-based eBay credentials with sandbox/production endpoint
  separation and redacted errors.
- Added an immutable in-memory active-listings client that retains permitted
  item-summary fields without raw API payloads.
- Added a pure eBay observation adapter using the existing 25-field schema and
  `observed`, `no_results`, `no_query`, and sanitized `source_unavailable` rows.
- Added bounded reviewer-priority collection with required summary, output, and
  book-limit inputs; deterministic ISBN/title query fallback; pacing; and
  ignored paired CSV/XLSX output.
- Extended Market Evidence Summary with repeated observation inputs and
  source-specific counts, statuses, currencies, price summaries, source mix,
  range source, and comparability.
- Preserved AbeBooks as the core price, confidence, range, and recommendation
  basis whenever AbeBooks evidence exists.

## Commands

Optional bounded access check:

```bash
.venv/bin/python library_pipeline.py ebay-access-check \
  --query "Springer Handbook of Spacetime" \
  --limit 3
```

Targeted observation collection:

```bash
.venv/bin/python library_pipeline.py collect-targeted-ebay-observations \
  --summary output/full_abebooks_market_evidence_summary.csv \
  --output output/targeted_ebay_observations.csv \
  --limit-books 10 \
  --max-results-per-book 3 \
  --delay 1
```

Repeated-input multi-source summary:

```bash
.venv/bin/python library_pipeline.py summarize-market-evidence \
  --observations output/full_abebooks_market_observations.csv \
  --observations output/targeted_ebay_observations.csv \
  --output-csv output/multisource_market_evidence_summary.csv \
  --output-xlsx output/multisource_market_evidence_summary.xlsx
```

Credentials must be configured locally through environment variables or an
ignored `.env` sourced into the current shell. They must never be printed,
staged, or committed.

## Operational Workflow

1. Configure and source ignored local eBay credentials.
2. Optionally verify sandbox access with one bounded `ebay-access-check`.
3. Collect a small explicit reviewer-priority cohort.
4. Summarize AbeBooks and eBay observations with repeated `--observations`.
5. Interpret eBay as supplemental active-listing asking-price evidence.
6. Keep all generated artifacts ignored under `output/`.

## Generated Artifacts

- `output/targeted_ebay_observations.csv/.xlsx`
- `output/multisource_market_evidence_summary.csv/.xlsx`

These are generated, ignored, non-durable artifacts. They are not monthly-import
inputs or canonical catalog, acquisition, Research Assessment, or review data.

## Validation

- Sandbox `EBAY_US` OAuth token acquisition succeeded through verified TLS.
- Two bounded Browse item-summary requests completed and produced two
  source-specific `no_results` rows.
- The readiness summary combined the full AbeBooks artifact with those two rows
  and produced 3,014 summaries: 3,012 AbeBooks-only and 2 mixed-source.
- All 246 automated tests passed during final release-readiness review.
- Python compilation, CLI help, whitespace, credential, and ignored-artifact
  checks passed.

## Known Limitations

- Production eBay access is disabled and unverified pending Marketplace Account
  Deletion/Closure notification compliance.
- Sandbox returned no representative listing rows, prices, or currencies.
- eBay match confidence remains `unknown` and is not used to upgrade AbeBooks
  confidence or recommendations.
- eBay `no_results` is source-specific and does not mean global market absence.
- Item price excludes shipping; total landed cost is not inferred.
- Currency conversion is not performed and cross-source prices are not pooled.
- Active listings are not sold/completed evidence.
- Existing workbook and HTML report projections remain AbeBooks-only.

## Deferred Work

- Production access validation and a representative bounded production run.
- Reviewer-approved eBay match-confidence rules.
- Shipping and total-cost treatment.
- Workbook and HTML report source-context integration.
- Sold/completed listing evidence, subject to separate access and product review.
- Any full-library eBay strategy, only after production behavior, quality, and
  rate limits are understood.

## Interpretation Caveat

AbeBooks and eBay active-listing prices are seller asking prices. They are not
appraisals, fair market value estimates, realized sale prices, expected proceeds,
or pricing guarantees. Edition, condition, dust jacket, signature, seller
credibility, and physical possession may materially affect value.

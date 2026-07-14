# Library Valuation v0.5.0 Release Readiness Review

## Status

**Ready for release after PR7 is reviewed and committed.**

Tagging and GitHub Release publication remain explicit post-commit operations.

## Release Summary

v0.5.0 delivers a generated market-evidence-first workflow:

```text
Raw market observations
  -> source-neutral Market Evidence Summary
  -> evidence availability and coverage
  -> market confidence and outlier sensitivity
  -> cautious asking-price-derived range
  -> review recommendation or fallback research priority
```

The summary model is versioned `0.5.0-pr6`. It remains generated output and does
not become durable project state.

## Production Behavior Confirmation

The release does not change Research Assessment scoring, signals, weights,
bands, or persisted assessments. It does not change durable catalog,
acquisition, import-manifest, or Collector Review data. The standard monthly
`update-library` workflow and AbeBooks collection behavior remain unchanged.

## Command and Artifacts

```bash
.venv/bin/python library_pipeline.py summarize-market-evidence \
  --observations output/market_observations.csv \
  --output-csv output/market_evidence_summary.csv \
  --output-xlsx output/market_evidence_summary.xlsx
```

- `market_observations.csv/.xlsx` contain source-specific listing and status
  rows.
- `market_evidence_summary.csv/.xlsx` contain source-neutral per-book evidence,
  confidence, range, and review guidance.

All four are generated artifacts under `output/` and are not canonical data.

## Acceptance Evidence

The release review verifies:

- exact schema field order and model version;
- deterministic grouping, counts, confidence ordering, and medians;
- status-row exclusion from asking-price calculations;
- conservative mixed-currency handling without conversion;
- availability, confidence, and outlier classifications;
- supported and suppressed range behavior;
- stable review recommendations and fallback priorities;
- Research Signals used only as missing-evidence fallback context;
- complete automated tests, compilation, and whitespace checks; and
- documented CLI options and generated-artifact boundaries.

## Known Limitations

- Current price evidence is seller asking-price evidence, not completed sales.
- AbeBooks remains one experimental source, not complete market truth.
- Edition and condition matching are lightweight.
- Currency conversion is intentionally absent.
- Range and sale-review thresholds are initial deterministic heuristics rather
  than statistically calibrated estimates of realizable proceeds.
- The existing Collector Workbook is not joined to generated market summaries
  in v0.5.0; review guidance is exposed in the Market Evidence Summary.

## Remaining Release Steps

1. Review and commit PR7.
2. Confirm the post-commit working tree is clean.
3. Create the annotated `v0.5.0` tag.
4. Publish the GitHub Release using `docs/RELEASE_NOTES_v0.5.0.md`.
5. Run the documented post-release smoke checks.

This PR does not create the tag or publish the release.

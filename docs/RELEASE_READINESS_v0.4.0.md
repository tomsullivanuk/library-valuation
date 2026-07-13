# Library Valuation v0.4.0 Release Readiness Review

## Status

**Ready for release after PR16 is reviewed and committed.**

No production behavior, data migration, generated-artifact, or test blocker was
identified. Tagging and GitHub Release publication remain explicit post-commit
release operations.

## Release Summary

v0.4.0 is a validation and Market Intelligence release. It delivers:

- a documented Market Intelligence architecture that separates observations,
  estimates, and recommendations;
- deterministic, stratified Market Validation sample generation;
- bounded, ISBN-first AbeBooks observation collection with respectful rate
  control and source-access diagnostics;
- coverage reporting and preserved lookup references;
- descriptive score-band and Research Signal analysis;
- an expanded evidence base of 205 books and 596 AbeBooks observation rows;
- signal-effectiveness and candidate-case review;
- calibration principles and a calibration proposal;
- non-production before/after calibration simulation; and
- an evidence-based decision not to change production Research Assessment
  scoring in v0.4.0.

The release adds research infrastructure. It does not add automated valuation,
appraisal claims, value buckets, or sale recommendations.

## Production Behavior Confirmation

The review confirms that v0.4.0 does not change:

- production Research Assessment scoring logic;
- `config/research_signals.yml`;
- Research Signal definitions or weights;
- production Research Assessment bands;
- persisted Research Assessments;
- durable catalog, acquisition, import-manifest, or Collector Review data;
- the `update-library` monthly import workflow; or
- existing catalog identity and reconciliation semantics.

User-visible behavior changes are limited to new opt-in Market Validation,
AbeBooks observation, diagnostics, analysis, and simulation commands. Those
commands read durable project data and generated experiment inputs where
appropriate, then write generated artifacts under `output/`. They do not run as
part of `update-library`.

The AbeBooks collector uses verified TLS, bounded request counts, configurable
delay, diagnostic failure rows, and generated lookup references. It remains an
experimental source adapter, not a production valuation integration.

## New Commands and Workflows

The implemented v0.4.0 command sequence is:

```bash
.venv/bin/python library_pipeline.py generate-market-validation-sample \
  --output-dir output \
  --sample-size-per-band 20 \
  --seed 42

.venv/bin/python library_pipeline.py collect-abebooks-observations \
  --output-dir output \
  --limit 30 \
  --delay 1.0 \
  --max-results-per-book 3

.venv/bin/python library_pipeline.py report-market-observation-coverage \
  --output-dir output

.venv/bin/python library_pipeline.py analyze-market-validation \
  --output-dir output

.venv/bin/python library_pipeline.py review-research-signal-effectiveness \
  --output-dir output

.venv/bin/python library_pipeline.py generate-expanded-market-validation-sample \
  --output-dir output \
  --additional-candidate-target 140 \
  --seed 42

.venv/bin/python library_pipeline.py collect-expanded-abebooks-observations \
  --output-dir output \
  --limit 140 \
  --delay 1.0 \
  --max-results-per-book 3

.venv/bin/python library_pipeline.py analyze-expanded-market-validation \
  --output-dir output

.venv/bin/python library_pipeline.py simulate-research-assessment-calibration \
  --output-dir output \
  --top-n 50
```

The base collector defaults to 30 books rather than the analysis-scale limit of
100 used in the original experiment. Limits can be supplied explicitly without
making collection unbounded.

## Generated Artifacts Review

Each name below is generated as both CSV and XLSX under `output/`:

- `market_validation_sample`
- `market_validation_sample_metadata`
- `market_observations`
- `market_observation_coverage_report`
- `market_validation_analysis`
- `research_signal_effectiveness_review`
- `expanded_market_validation_sample`
- `expanded_market_validation_sample_metadata`
- `expanded_market_observations`
- `expanded_market_observation_coverage_report`
- `expanded_market_validation_analysis`
- `expanded_research_signal_effectiveness_review`
- `calibration_simulation`
- `calibration_simulation_summary`
- `calibration_simulation_candidate_movements`

`output/.gitignore` ignores generated contents while preserving the ignore file
itself. The release review confirmed that no generated output is tracked. These
artifacts are reproducible experiment products, not canonical source data.

## Documentation Coherence

The v0.4.0 documentation consistently records that:

- the release validates and analyzes possible market signal;
- AbeBooks asking prices are observations, not valuations or completed-sale
  evidence;
- AbeBooks is the first experimental market source, not complete market truth;
- production scoring remains unchanged; and
- future model work may separate market likelihood from research effort.

The release notes, changelog, roadmap, backlog, architecture, README, and
release checklist have been aligned with the final PR15 decision.

## Evidence and Decision

The expanded experiment contains 205 sampled books and 596 AbeBooks observation
rows, with at least one observation for every expanded-sample book in that run.
The strongest score band led on median and average observed asking price, but
score-band medians remained non-monotonic and populated bands remained
outlier-sensitive.

PR14's conservative and market-likelihood scenarios changed scores and band
assignments but did not change top-50 membership, top-50 asking-price metrics,
false-positive representation, false-negative surfacing, or outlier exposure.
PR15 therefore records the release decision: preserve current production
scoring and defer model redesign.

## Known Limitations

- Evidence comes from one source and one collection period.
- Asking prices do not establish completed-sale value or realizable proceeds.
- AbeBooks markup and access behavior may change.
- Listing condition is not normalized deeply enough for valuation use.
- Edition matching is lightweight and title/author fallback is lower confidence.
- The stratified sample is not a prevalence estimate for the full catalog.
- No simulated scoring alternative demonstrated a better practical candidate
  set.
- Modern Amazon `B0...` ASIN physical-book detection remains unresolved.

## Remaining Release Steps

No implementation blocker remains. Before publication:

1. Review and commit PR16.
2. Confirm the post-commit working tree is clean.
3. Create the annotated `v0.4.0` tag.
4. Publish the GitHub Release using `docs/RELEASE_NOTES_v0.4.0.md`.
5. Run the documented post-release smoke checks.

This PR does not create the tag or publish the release.

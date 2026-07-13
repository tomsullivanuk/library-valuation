# Library Valuation v0.4.0 Release Notes

## Overview

Library Valuation v0.4.0 adds a Market Validation and Market Intelligence
research workflow. It tests whether existing Research Assessments contain
useful information about external market interest before the project invests in
automated valuation or production scoring changes.

The release concludes that the current model contains useful directional
signal, but does not behave as a clean market-likelihood gradient. Production
Research Assessment scoring remains unchanged.

## What Changed

- Added deterministic stratified Market Validation sampling.
- Added bounded, ISBN-first AbeBooks observation collection.
- Added source-access diagnostics, coverage reporting, and preserved lookup
  references.
- Expanded the validation evidence to 205 books and 596 AbeBooks observation
  rows in the completed experiment.
- Added score-band, signal-effectiveness, candidate-case, and outlier analysis.
- Added non-production calibration scenario simulation.
- Recorded calibration principles and the decision not to ship unsupported
  scoring changes.

## New Workflows

The release adds opt-in commands for sample generation, AbeBooks observation
collection, coverage reporting, validation analysis, signal review, expanded
analysis, and calibration simulation. See `README.md` and
`docs/RELEASE_READINESS_v0.4.0.md` for the complete command sequence.

All generated CSV and XLSX files are written under `output/` and remain
ignored. They are research artifacts, not durable repositories.

## What Did Not Change

- Production Research Assessment logic, signals, weights, and bands.
- `config/research_signals.yml`.
- Persisted Research Assessments and durable catalog data.
- Monthly `update-library` behavior.
- Catalog identity or acquisition semantics.

The release does not create valuations, appraisal claims, value buckets, or
sale recommendations.

## Validation

The release-readiness review ran the complete automated test suite, Python
compilation, whitespace validation, command-surface inspection, Markdown-link
validation, and generated-artifact tracking checks.

## Known Limitations

- AbeBooks is one experimental source, not complete market truth.
- Asking prices are observations, not completed sales or valuations.
- Listing condition and edition matching remain lightweight.
- The validation sample is intentionally stratified and does not estimate
  catalog-wide prevalence.
- Calibration simulations did not improve the practical top candidate set.

## Next Direction

Future design should investigate separating market likelihood from research
effort. Additional source and sold-price evidence should precede any production
calibration proposal.

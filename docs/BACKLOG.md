# Product Backlog

This document captures product ideas that are not yet scheduled for implementation.
Items move from this backlog into the Roadmap when they are selected for a release.

---

## v0.5.0 Market-Evidence-First Work

- [x] Define the generated Market Evidence Summary schema and version.
- [x] Aggregate source-specific market observations per catalog item.
- [x] Classify market confidence and outlier sensitivity deterministically.
- [x] Produce a cautious asking-price-derived range prototype.
- [x] Generate review recommendations and fallback research priority.
- [x] Document the generated/non-durable boundary and non-appraisal terminology.
- [ ] Add another independent market source or completed-sale evidence.
- [ ] Calibrate range and review thresholds against broader evidence.
- [ ] Decide whether a future durable observation repository is justified.

## v0.6.0 Full AbeBooks Baseline & Review Artifacts

- [x] Define the multi-source release plan.
- [x] Complete the source integration spike.
- [x] Run a bounded test and full-library AbeBooks baseline.
- [x] Analyze baseline review recommendations, confidence, evidence status, and
  outlier sensitivity.
- [x] Add the AbeBooks baseline review workbook.
- [x] Add the static, shareable AbeBooks review report.

## v0.7.0 eBay Active Listings Integration

- [x] Define the v0.7.0 release plan and staged architecture.
- [ ] Confirm developer keysets, OAuth scope, token flow, sandbox behavior,
  production access, marketplace selection, and call limits.
- [x] Add an isolated Browse API client with redaction, bounded results, and
  fixture-backed failure handling.
- [x] Normalize active listings into source-specific eBay observation/status
  rows while preserving item price, currency, buying option, match, and source
  provenance while excluding shipping.
- [x] Add an explicit bounded reviewer-priority collection workflow with
  generated CSV/XLSX outputs and conservative pacing.
- [ ] Run a 5–10 book smoke test and a bounded reviewer-priority cohort before
  deciding whether broader collection is justified.
- [x] Add source-specific summary measures and explicit agreement, conflict, or
  non-comparability without naively pooling prices.
- [ ] Update workbook and HTML review artifacts with concise source context and
  active-listing caveats.
- [ ] Complete v0.7.0 documentation and release readiness.
- [ ] Keep sold/completed eBay evidence and automatic full-library collection
  deferred unless separate access and product decisions are approved.

---

## v0.4.0 Validation Work

### Valuation
- [x] Market Intelligence architecture using `docs/MARKET_INTELLIGENCE.md`
- [x] Market Validation Spike using `docs/MARKET_VALIDATION_SPIKE.md`
- [x] Generate a stratified Research Score sample with `generate-market-validation-sample`
- [x] Collect bounded AbeBooks observations for the validation sample
- [x] Report observation coverage with `report-market-observation-coverage`
- [x] Analyze AbeBooks observation quality and coverage from bounded ISBN-first runs
- [x] Generate PR8 Research Score market validation analysis with `analyze-market-validation`
- [x] Review individual Research Signal effectiveness with `review-research-signal-effectiveness`
- [x] Prepare PR11 Research Assessment Calibration Proposal using
  `docs/MARKET_VALIDATION_FINDINGS_v0.4.0.md`
- [x] Generate the PR12 expanded validation sample and collect bounded AbeBooks
  observations for newly selected books
- [x] Refresh PR13 expanded coverage, score-band, signal, and candidate analysis
  using `analyze-expanded-market-validation`
- [x] Run PR14 before/after calibration simulation without changing production
  Research Assessment configuration
- [x] Review PR14 scenario assumptions and stop v0.4.0 calibration before
  production scoring changes
- [x] Complete the v0.4.0 release-readiness review with production Research
  Assessment scoring unchanged
- [x] Create a generated per-book market evidence summary for observed books
- [ ] Review false-positive and false-negative candidates from PR8
- [ ] Persistent valuation repository
- [x] First experimental external asking-price source (AbeBooks)
- [x] Generated review recommendation and fallback-priority fields
- [x] Static, shareable AbeBooks review report with acquisition/possession context
- [ ] eBay access spike and isolated integration (v0.7.0)
- [ ] Incremental valuation (only value new books)

### Workflow
- [ ] Manual review workflow
- [ ] Re-evaluate stale valuations
- [ ] Archive processed Amazon exports

---

## Future Functional Enhancements

### Catalog
- [ ] Multiple acquisition sources
- [ ] Improve physical book detection for modern Amazon ASINs
- [ ] Duplicate / edition review
- [ ] Signed / inscribed copy support
- [ ] Condition tracking

### Reporting
- [ ] Collection statistics dashboard
- [ ] Improve Metadata Gap classification
- [ ] Export seller worksheets
- [ ] Insurance inventory report

---

## Technical Debt / Engineering

- [ ] Split `library_pipeline.py`
- [ ] GitHub Actions CI
- [ ] Improve CLI progress display
- [ ] Better logging
- [ ] Performance profiling
- [ ] Acceptance test fixtures

---

## Research / Open Questions

- Design a future separation between market likelihood and research effort.
- Evaluate another market source, including the feasibility of sold-price
  evidence, before revisiting production calibration.
- Refine calibration scenarios only after independent evidence or a revised
  model design is available.
- Revisit score bands after clarifying the purpose of each future score.
- Validate Research Assessment behavior against future monthly imports.
- Improve physical book detection for modern Amazon ASINs:
  - Investigate Amazon `B0...` ASINs that may represent physical books.
  - June 2026 data included at least one likely book, `B0GTQMJ53N`, that was
    excluded by current ISBN-like ASIN heuristics.
  - Evaluate title/category/export-field heuristics or lookup fallbacks.
- Empirically validate Research Assessment effectiveness:
  - Use `docs/MARKET_INTELLIGENCE.md` to separate market observations from
    valuation estimates and recommendations.
  - Follow the plan in `docs/MARKET_VALIDATION_SPIKE.md`.
  - Sample books across Research Score bands.
  - Collect bounded AbeBooks lookup observations without estimating value.
  - Use AbeBooks feasibility results as evidence, not as a production source
    commitment.
  - Compare Research Score against externally observed market value.
  - Review signal-level coverage, asking-price distributions, combinations, and
    candidate misses before proposing model changes.
  - Use results to decide whether valuation workflow, automated valuation, or
    model refinement should come next.
- Improve Metadata Gap classification:
  - Classify metadata gaps by type/severity.
  - Distinguish critical bibliographic gaps from research-enhancement gaps such
    as missing LCC/OCLC.
  - Make the Metadata Gaps workbook sheet more actionable.
- How should valuations age over time?
- Which valuation providers should be authoritative?
- How should sets and multi-volume works be represented?
- How should manual overrides interact with automatic valuations?
- How should condition affect valuation?

# Product Backlog

This document captures product ideas that are not yet scheduled for implementation.
Items move from this backlog into the Roadmap when they are selected for a release.

---

## Next Release Candidates (v0.4.0)

### Valuation
- [ ] Market Intelligence architecture using `docs/MARKET_INTELLIGENCE.md`
- [ ] Market Validation Spike using `docs/MARKET_VALIDATION_SPIKE.md`
- [ ] Generate a stratified Research Score sample with `generate-market-validation-sample`
- [ ] Create a temporary valuation workbook for sampled books
- [ ] Analyze Research Score association with observed market value
- [ ] Persistent valuation repository
- [ ] First external valuation source (AbeBooks or eBay)
- [ ] "Books Worth Investigating" report
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
  - Compare Research Score against externally observed market value.
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

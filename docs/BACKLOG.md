# Product Backlog

This document captures product ideas that are not yet scheduled for implementation.
Items move from this backlog into the Roadmap when they are selected for a release.

---

## Next Release Candidates (v0.3.x)

### Valuation
- [ ] Research Assessment v1
- [ ] Empirically validate Research Assessment effectiveness
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
  - Sample books across High, Medium, Low, and None bands.
  - Perform manual market research.
  - Compare Research Assessment scores/bands against actual collector value,
    scarcity, dealer interest, and research usefulness.
  - Use results to tune future signal weights before adding automated
    valuation.
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

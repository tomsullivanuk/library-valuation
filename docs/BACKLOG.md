# Product Backlog

This document captures product ideas that are not yet scheduled for implementation.
Items move from this backlog into the Roadmap when they are selected for a release.

---

## Next Release Candidates (v0.3.x)

### Valuation
- [ ] Research Assessment v1
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
- [ ] Duplicate / edition review
- [ ] Signed / inscribed copy support
- [ ] Condition tracking

### Reporting
- [ ] Collection statistics dashboard
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

- How should valuations age over time?
- Which valuation providers should be authoritative?
- How should sets and multi-volume works be represented?
- How should manual overrides interact with automatic valuations?
- How should condition affect valuation?

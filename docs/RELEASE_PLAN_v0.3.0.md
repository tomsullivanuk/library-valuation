# Library Valuation v0.3.0 Release Plan

## Release Theme

**Research Candidates & Collector Review Workflow**

---

## Mission

Help book collectors identify which books are worth researching, keeping, insuring, or selling.

Version 0.3.0 shifts the project's emphasis from building infrastructure to delivering actionable value to the collector. The ingestion pipeline, durable catalog, incremental updates, and metadata infrastructure introduced in v0.2.0 are considered stable unless a compelling architectural reason requires change.

---

# Objectives

## Primary

- Deliver actionable Research Candidates for collectors.
- Introduce durable collector review data.
- Produce user-focused reports rather than infrastructure artifacts.
- Preserve reproducibility and deterministic pipeline behavior.

## Secondary

- Continue improving documentation and test coverage.
- Maintain backward compatibility with existing catalogs whenever practical.

---

# Architectural Decisions

The following decisions apply throughout the v0.3.0 release.

### Research Priority is not Market Value

The pipeline identifies books that deserve human attention.

It does **not** estimate market price or resale value in this release.

### Human Decisions are Durable

Collector decisions are user-owned data.

Monthly imports must never overwrite or discard user review decisions.

### Reports are Derived Artifacts

Reports, spreadsheets, and summaries are generated outputs.

The authoritative data remains the durable catalog and associated state.

### Explainability Over Black Boxes

Priority assessments should be explainable.

Every research recommendation should include one or more reason codes describing why the book was surfaced.

### Preserve Incremental Processing

Monthly imports should continue to process only new acquisitions while preserving existing catalog state whenever possible.

---

# Planned Pull Requests

## PR1 — Research Signal Model

**Status:** Done

### Goal

Introduce deterministic Research Signals as the explainable building blocks for
later Research Assessments and Research Candidates.

### Deliverables

- Research Signal representation
- Configurable signal weights and thresholds where practical
- Initial deterministic signal generation from current catalog, metadata, and
  acquisition evidence
- Tests

### Acceptance Criteria

- Each signal includes a code, label, point value, evidence reference, and
  human-readable explanation.
- Signal generation is deterministic for identical input and configuration.
- Existing monthly pipeline outputs are unchanged.

---

## PR2 — Explainable Research Assessment

**Status:** Done

### Goal

Aggregate Research Signals into transparent and reproducible Research
Assessments.

### Deliverables

- Reason-code framework
- Priority scoring improvements
- Tests

### Acceptance Criteria

- Every recommended book includes one or more explainable reason codes.
- Priority ordering is deterministic.

## PR3 — Research Candidates

**Status:** In progress

### Goal

Generate a prioritized list of Research Candidates requiring collector
attention.

### Deliverables

- Ranked Research Candidates
- CSV and XLSX generated outputs
- Acquisition and metadata context for each candidate
- Deterministic sorting by band, score, signal count, publication year, title,
  and catalog identity

### Acceptance Criteria

- Newly acquired books appear appropriately.
- Rows with no Research Signals are excluded by default.
- Candidate generation is deterministic.
- Collector review state, reviewed-item filtering, and priority overrides remain
  deferred to PR4.

---

## PR4 — Durable Collector Review State

**Status:** In progress

### Goal

Introduce durable collector-owned review information that persists across monthly imports.

### Deliverables

- Collector review data model
- Persistent review state
- Durable `data/collector_reviews.csv`
- Read-only review context in generated Research Candidates
- Tests

### Acceptance Criteria

- Review information survives repeated monthly imports.
- Existing pipeline behavior remains unchanged.
- No user-entered review data is overwritten.
- Reviewed-item filtering and priority override behavior remain deferred until
  they can be designed as explicit workflow rules.

---

## PR5 — Collector Workbook

**Status:** In progress

### Goal

Produce an Excel workbook designed for collector workflow.

### Proposed Worksheets

- Research Candidates
- Current Acquisitions
- Reviewed Items
- Metadata Gaps
- Summary
- Collector Reviews

### Acceptance Criteria

- Workbook is understandable without reading project documentation.
- Information is organized around collector decisions rather than internal implementation.
- Workbook is generated output only; edits are not imported.
- Durable review state remains in `data/collector_reviews.csv`.

---

## PR6 — Pipeline Integration

**Status:** Planned

### Goal

Integrate the new workflow into the existing update process.

### Deliverables

- CLI updates
- Pipeline integration
- End-to-end tests

### Acceptance Criteria

- A single monthly pipeline execution refreshes all outputs.
- No additional manual workflow is required.

---

## PR7 — Documentation & Release

**Status:** Planned

### Deliverables

- README updates
- Architecture updates
- CHANGELOG
- Release checklist
- Acceptance testing

### Acceptance Criteria

- Documentation accurately reflects the released behavior.
- All regression and acceptance tests pass.
- Repository is ready for release.

---

# Deferred Beyond v0.3.0

The following ideas remain valuable but are intentionally deferred to keep v0.3.0 focused.

- External market valuation (eBay, AbeBooks, Biblio, etc.)
- Insurance value estimation
- Condition grading
- Edition identification using OCR or image analysis
- Automated sell recommendations
- Web application / GUI
- Database migration

These features depend on a stronger research and review foundation and will be revisited in future releases.

---

# Release Success Criteria

Version 0.3.0 will be considered successful if a collector can:

1. Import a monthly Amazon Order History export.
2. Preserve all previous catalog and review information.
3. Receive prioritized, explainable Research Candidates.
4. Record review decisions that persist across future imports.
5. Use the generated workbook to guide research and collection decisions.

---

# Notes

This document is intended to evolve throughout the release. Planned pull requests, architectural decisions, and acceptance criteria should be updated as implementation progresses. Deferred items should be reconsidered only after the current release objectives are complete.

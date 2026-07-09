# Library Valuation v0.3.0 Release Notes

## Overview

Library Valuation v0.3.0 turns the durable Amazon ingestion pipeline introduced
in v0.2.0 into a collector-facing research workflow. The release helps answer:

- Which books should I look at first?
- Why did each book surface?
- What has already been reviewed?
- Where are the metadata gaps?

The release does not add market valuation or pricing. It builds the research
and review foundation needed before valuation evidence is introduced.

## Major Features

- **Research Signals**: deterministic, explainable signals such as older
  publication year, university or specialist publisher, missing identifiers,
  scholarly classifications, multiple acquisitions, and low metadata confidence.
- **Research Assessments**: generated system-owned assessments that aggregate
  Research Signals into score, band, and explanation fields.
- **Research Candidates**: generated CSV/XLSX outputs that rank high, medium,
  and low Research Assessments for collector attention.
- **Collector Review repository**: durable collector-owned review state in
  `data/collector_reviews.csv`.
- **Collector Workbook**: generated `output/collector_workbook.xlsx` with
  Summary, Research Candidates, Current Acquisitions, Reviewed Items, Metadata
  Gaps, and Collector Reviews sheets.
- **Workflow polish**: terminal summaries and workbook Summary sheets now
  surface the key counts needed during monthly review.

## Architecture Highlights

- Generated system data and collector-owned data remain separate.
- Research Assessments are system-owned and reproducible.
- Collector Reviews are human-owned and must not be overwritten by monthly
  automation.
- Research Candidates and the Collector Workbook are generated outputs, not
  source data.
- The durable Research Assessment file path remains
  `data/research_priority_assessments.csv` for continuity, while the conceptual
  object is now a Research Assessment.

## Upgrade Notes

- Existing v0.2.0 durable catalog and acquisition state can be reused.
- Run the normal monthly command:

  ```bash
  python3 library_pipeline.py update-library
  ```

- The pipeline will create `data/collector_reviews.csv` if it does not already
  exist.
- Generated outputs under `output/` can be deleted and regenerated.
- Workbook edits are not imported. Durable Collector Review data should be
  maintained in `data/collector_reviews.csv`.

## Acceptance Notes

The v0.3.0 acceptance run used a real June 2026 Amazon Order History export and
confirmed:

- incremental monthly import completed successfully;
- no new catalog items were created when the full-history export contained only
  already-known books;
- existing Research Assessments were reused rather than unnecessarily
  regenerated;
- Research Candidates were generated;
- `output/collector_workbook.xlsx` was generated;
- generated outputs remained separate from durable source data.

## Known Limitations

- Modern Amazon `B0...` ASINs that may represent physical books need additional
  investigation.
- Research Assessment effectiveness has not yet been empirically validated
  against collector value, scarcity, dealer interest, or manual market research.
- Metadata Gap classification may evolve.
- Workbook edits are not imported.
- Collector Review editing workflow is not yet implemented.
- No external valuation sources are included.
- No market valuation, pricing, sell/keep/insure recommendation, condition,
  signature, or photo workflow is included.

## Roadmap Preview

Future releases should focus on:

- empirical validation and tuning of Research Assessment weights;
- improved physical book detection for modern Amazon ASINs;
- more actionable Metadata Gap classification;
- explicit Collector Review editing workflow;
- structured market evidence capture;
- external valuation-source integration only after evidence and provenance
  models are established.

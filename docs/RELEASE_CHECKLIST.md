# Release Checklist

## v0.3.0

Pre-release checks:

- [x] Confirm the working tree contains only intentional source and
  documentation changes.
- [x] Run `.venv/bin/python -m compileall library_pipeline.py valuation tests`.
- [x] Run `.venv/bin/pytest`.
- [x] Run a monthly update against a real June 2026 Amazon Order History export.
- [x] Confirm incremental monthly import completes without creating duplicate
  catalog items.
- [x] Confirm known catalog items reuse existing Research Assessments rather
  than generating unnecessary replacements.
- [x] Confirm `output/research_candidates.csv` and
  `output/research_candidates.xlsx` are regenerated.
- [x] Confirm `output/collector_workbook.xlsx` is regenerated.
- [x] Confirm workbook edits are not imported and durable Collector Review state
  remains in `data/collector_reviews.csv`.
- [x] Confirm generated outputs remain ignored and are not staged.

Release hygiene:

- [x] Confirm `CHANGELOG.md` includes v0.3.0.
- [x] Confirm `docs/RELEASE_NOTES_v0.3.0.md` is ready for the GitHub Release.
- [x] Confirm README monthly workflow instructions match the released CLI.
- [x] Confirm architecture and data-model docs describe generated outputs versus
  durable repositories.
- [ ] Tag the release only after final review succeeds.
- [ ] Create the GitHub Release using `docs/RELEASE_NOTES_v0.3.0.md`.

Known post-release follow-up:

- Investigate modern Amazon `B0...` ASIN physical-book detection.
- Empirically validate Research Assessment effectiveness.
- Improve Metadata Gap classification.
- Add a Collector Review editing workflow.
- Add market evidence and valuation only after the research workflow has been
  validated.

## v0.2.0

Pre-release checks:

- Confirm the working tree contains only intentional source and documentation
  changes.
- Run `python3 -m compileall library_pipeline.py valuation tests`.
- Run `.venv/bin/python -m pytest`.
- Run `.venv/bin/python -m pytest --cov`.
- Run a clean monthly update against a representative Amazon export package.
- Run the same export a second time and confirm no new catalog items or research
  assessments are created.
- Run a newer full-history export and confirm only newly discovered catalog items
  receive new research-priority assessments.
- Delete generated files under `output/`, rerun, and confirm reports regenerate
  from `input/`, `data/`, `cache/`, and `config/`.

Release hygiene:

- Confirm `data/*.csv`, `cache/openlibrary/*.json`, and `output/*` are not
  staged unless intentionally providing sample fixtures.
- Confirm `CHANGELOG.md` has the release summary.
- Confirm README monthly workflow instructions match the released CLI.
- Tag the release only after acceptance testing succeeds.

Post-release follow-up:

- Plan explicit `--reevaluate` modes.
- Plan metadata refresh, override, and staleness policy.
- Decide whether to add a documented one-time migration command for legacy
  `output/openlibrary_cache.json` files.

# Release Checklist

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

# Contributing

## Purpose

`CONTRIBUTING.md` describes the engineering practices expected of all
contributors to Library Valuation. The project's architectural intent is
documented in `VISION.md`, `docs/ARCHITECTURE.md`, `docs/DATA_MODEL.md`, and
`docs/ROADMAP.md`. Use this guide as the operating manual for making changes
without drifting from those documents.

## Development Environment

Use the project virtual environment:

```bash
python3 -m venv .venv
source .venv/bin/activate
```

Install dependencies from `requirements.txt`:

```bash
pip install -r requirements.txt
```

Run tests before committing. Verify compile checks before committing:

```bash
python -m compileall .
pytest
```

## Repository Philosophy

The repository is the canonical source of truth for code, configuration,
documentation, and data-shape decisions. Generated Excel workbooks are outputs,
not source data. CSV files, configuration files, and code are the reproducible
source of truth for current workflows.

Prefer reproducibility over manual editing. Preserve backward compatibility
where practical, especially for existing command behavior, output field names,
and documented workflows. Favor incremental, reviewable changes. See
`VISION.md` for the broader mission and design philosophy.

## Coding Principles

Prefer small, reviewable commits. Show diffs before committing unless
explicitly instructed otherwise.

Favor clear architecture over short-term convenience. The architecture docs
separate catalog facts, market observations, valuation estimates, and decisions;
keep that separation visible in code and data shapes.

Keep business logic centralized. Avoid duplicating business rules. Prefer
composition over copying similar workflows or transformations into multiple
places.

Keep business rules in configuration whenever they are likely to evolve. Reserve
Python code for algorithms, workflows, and orchestration. Keep configuration
outside Python whenever practical, especially for scoring weights, publisher
tiers, subject signals, thresholds, and future valuation rules.

Current code may still be compact while the project is small. When extracting
modules, follow the boundaries described in `docs/ARCHITECTURE.md` rather than
inventing a new structure.

## Documentation

Update documentation whenever architecture, workflows, data contracts, generated
artifacts, or contributor expectations change. Avoid repeating architecture
inside this guide; cross-reference the architecture documents instead.

Architectural changes should be reflected in the relevant source document:

- `VISION.md`
- `docs/ARCHITECTURE.md`
- `docs/DATA_MODEL.md`
- `docs/ROADMAP.md`

Cross-reference existing docs instead of duplicating long explanations. If a
change affects the source-of-truth principle, generated artifact policy, data
separation, or roadmap sequencing, update the relevant document in the same
change.

## Testing

Run compile checks:

```bash
python -m compileall .
```

Run pytest:

```bash
pytest
```

Add tests for new public APIs. Preserve existing behavior unless intentionally
changing it, and make intentional behavior changes visible through focused
tests. Network-dependent behavior should be isolated so core catalog, matching,
valuation, and decision logic can be tested without live network access.

## Git Workflow

Review diffs before committing. Keep commits focused on one coherent change.
Use descriptive commit messages that explain the repository-level outcome, not
only the files touched. When working interactively, commit only after approval.

Do not mix generated-output churn with code or architecture changes unless the
generated artifact is intentionally part of the review. When generated files are
committed, the reason should be clear.

## AI Collaboration

Repository documentation defines the architecture. Contributors, including AI
agents, should use the docs as the working contract.

ChatGPT is used for product direction, architecture, design reviews, and
implementation specifications.

Codex is used for implementation, validation, documentation updates, and
repository maintenance.

When architecture is uncertain, explain the tradeoffs before implementing. Do
not introduce new architecture silently in code. Prefer a small documented step
that moves the project along the existing roadmap.

## Reading Order

Before making substantive changes, read the project documentation in this order:

1. `README.md`
2. `VISION.md`
3. `docs/ARCHITECTURE.md`
4. `docs/DATA_MODEL.md`
5. `docs/ROADMAP.md`

This order starts with current usage, then moves through mission, architecture,
data contracts, and planned implementation sequence.

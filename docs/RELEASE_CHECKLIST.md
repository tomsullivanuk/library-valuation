# Release Checklist

## v0.10.0

Pre-release checks:

- [x] Confirm 20 workflow, 160 combined inventory, and 462 full-suite tests pass.
- [x] Run `.venv/bin/python -m compileall -q library_pipeline.py valuation tests`.
- [x] Run `git diff --check` and Markdown-link validation.
- [x] Confirm preview is the default and publication requires `--publish`.
- [x] Confirm injected failures restore every affected durable repository.
- [x] Confirm exact repeats create no duplicate durable identities or acquisitions.
- [x] Confirm the untouched 30-row preview produces 30 holdings, 22 existing
  links, 5 proposed identities, 3 unresolved cases, and 0 acquisitions.
- [x] Confirm two fresh previews produce identical completion JSON, temporary
  repository rows, summary CSV, and nine-sheet workbook.
- [x] Confirm real durable repository hashes are unchanged by preview validation.

Privacy and artifact checks:

- [x] Confirm the real Libib export remains ignored and untracked.
- [x] Confirm committed fixtures are synthetic, reduced, and privacy-safe.
- [x] Confirm reviewer artifacts expose only allowlisted fields.
- [x] Confirm no generated artifact, temporary repository, or real
  `data/`, `input/`, or `output/` file is staged.

Release hygiene:

- [x] Confirm the changelog, release notes, and release-readiness record exist.
- [x] Confirm current documentation agrees on behavior and deferred scope.
- [ ] Confirm the working tree is clean after the final release commit.
- [ ] Create annotated tag `v0.10.0` at the final release commit.
- [ ] Push `main` and the tag.
- [ ] Publish the GitHub Release from `docs/RELEASE_NOTES_v0.10.0.md`.
- [ ] Verify the release is not a draft/prerelease and is marked latest.

Known follow-up:

- v0.11.0 adds Library Explorer and Action Center.
- v0.12.0 adds reviewed monthly refresh and freshness orchestration.
- Durable location mapping, manual reconciliation editing, condition, and
  disposition workflows remain deferred.

## v0.9.0

Pre-release checks:

- [x] Run `.venv/bin/python -m pytest` and confirm all 302 tests pass.
- [x] Run `python3 -m compileall valuation library_pipeline.py tests`.
- [x] Run `git diff --check`.
- [x] Confirm CLI help for full-library collection, checkpoint materialization,
  multi-source summarization, reviewer workbook, and reviewer report.
- [x] Confirm the bounded interruption/resume validation and full 3,014-book
  production baseline completed and are documented.
- [x] Confirm checkpoint integrity and deterministic multi-source,
  workbook, and HTML reconciliation.
- [x] Confirm AbeBooks remains the authoritative core-range source and eBay
  remains supplemental active-listing evidence.
- [x] Confirm valuation, recommendation, confidence, Research Assessment, and
  monthly-import semantics are unchanged.
- [x] Confirm non-appraisal language and known evidence limitations are clear.
- [x] Confirm internal documentation links resolve.

Privacy and artifact checks:

- [x] Confirm all eBay seller fields are blank and notes contain no seller
  identity.
- [x] Confirm no credentials, OAuth tokens, authorization/response headers, or
  raw API payloads are tracked or staged.
- [x] Confirm `.env`, checkpoints, observation parts, and generated CSV, XLSX,
  workbook, and HTML artifacts remain ignored and untracked.

Release hygiene:

- [x] Confirm `CHANGELOG.md` includes v0.9.0.
- [x] Confirm `docs/RELEASE_NOTES_v0.9.0.md` is ready for the GitHub Release.
- [x] Confirm `docs/RELEASE_READINESS_v0.9.0.md` records final scope, evidence,
  privacy controls, limitations, and the release gate.
- [x] Confirm README, architecture, roadmap, backlog, Market Intelligence,
  baseline, reconciliation, and release plan are consistent.
- [ ] Confirm the working tree is clean after the final release commit.
- [ ] Create annotated tag `v0.9.0` at the final release commit.
- [ ] Push `main` and the tag.
- [ ] Publish the GitHub Release from `docs/RELEASE_NOTES_v0.9.0.md`.
- [ ] Verify the published release is not a draft or prerelease and is marked
  latest.

Known follow-up:

- v0.10.0 adds Libib physical-inventory integration.
- v0.11.0 adds the Library Explorer and Action Center.
- v0.12.0 adds automated monthly refresh orchestration and a reviewed durable
  freshness model.
- Sold/completed evidence, shipping-inclusive prices, currency conversion, and
  automated eBay match confidence remain deferred.

## v0.6.0

Pre-release checks:

- [x] Run `.venv/bin/python -m pytest`.
- [x] Run `python3 -m compileall valuation library_pipeline.py tests`.
- [x] Run `git diff --check`.
- [x] Confirm CLI help for full-library collection, the review workbook, and
  the static review report matches documented options.
- [x] Confirm the full AbeBooks baseline and Market Evidence Summary can be
  generated.
- [x] Confirm the review workbook and static HTML report can be generated.
- [x] Confirm the static HTML report was visually inspected during PR5.
- [x] Confirm Market Evidence Summary and Research Assessment semantics are
  unchanged.
- [x] Confirm monthly import and durable data behavior are unchanged.
- [x] Confirm generated artifacts remain ignored/untracked.
- [x] Confirm non-appraisal caveats cover asking prices, condition, edition,
  seller credibility, and physical possession.

Release hygiene:

- [x] Confirm `CHANGELOG.md` includes v0.6.0.
- [x] Confirm `docs/RELEASE_NOTES_v0.6.0.md` is ready for the GitHub Release.
- [x] Confirm `docs/RELEASE_READINESS_v0.6.0.md` records final scope,
  acceptance evidence, and limitations.
- [x] Confirm README, architecture, roadmap, backlog, Market Intelligence, and
  release plan describe Full AbeBooks Baseline & Review Artifacts.
- [x] Confirm eBay active listings are deferred to v0.7.0.
- [ ] Confirm the working tree is clean after the documentation PR commit.
- [ ] Create the annotated tag with `git tag -a v0.6.0 -m "Release v0.6.0"`.
- [ ] Push the commit and tag.
- [ ] Create the GitHub Release using `docs/RELEASE_NOTES_v0.6.0.md`.

Post-release smoke checks:

- [ ] Confirm `library_pipeline.py --help` lists all v0.6.0 commands.
- [ ] Generate the workbook and HTML report from preserved full-baseline
  summary output.
- [ ] Open the generated HTML in a browser and inspect all review tabs.
- [ ] Confirm the GitHub Release links to the correct tag and release notes.

Known post-release follow-up:

- Begin v0.7.0 eBay credential/access validation and isolated adapter design.
- Add cross-source comparison only after provenance and evidence types remain
  auditable.
- Continue improving edition, condition, and physical-possession review.

## v0.5.0

Pre-release checks:

- [x] Run `.venv/bin/python -m pytest`.
- [x] Run `python3 -m compileall valuation library_pipeline.py tests`.
- [x] Run `git diff --check`.
- [x] Confirm `summarize-market-evidence --help` matches documented options.
- [x] Confirm focused Market Evidence Summary tests cover aggregation,
  confidence, outlier sensitivity, range, and review recommendations.
- [x] Confirm production Research Assessment scoring, signals, weights, and
  bands are unchanged.
- [x] Confirm monthly `update-library` and durable data behavior are unchanged.
- [x] Confirm Market Evidence Summary artifacts remain generated and untracked.
- [x] Confirm mixed currencies are not converted or combined.
- [x] Confirm asking-price-derived ranges use non-appraisal terminology.
- [x] Confirm internal Markdown links resolve.

Release hygiene:

- [x] Confirm `CHANGELOG.md` includes v0.5.0.
- [x] Confirm `docs/RELEASE_NOTES_v0.5.0.md` is ready for the GitHub Release.
- [x] Confirm `docs/RELEASE_READINESS_v0.5.0.md` records final scope,
  acceptance evidence, and limitations.
- [x] Confirm README, architecture, data model, roadmap, backlog, Market
  Intelligence, and release plan describe the same generated workflow.
- [ ] Confirm the working tree is clean after the PR7 commit.
- [ ] Create the annotated tag with `git tag -a v0.5.0 -m "Release v0.5.0"`.
- [ ] Push the commit and tag.
- [ ] Create the GitHub Release using `docs/RELEASE_NOTES_v0.5.0.md`.

Post-release smoke checks:

- [ ] Confirm `library_pipeline.py --help` lists `summarize-market-evidence`.
- [ ] Run the summary command against preserved generated observations.
- [ ] Inspect the CSV/XLSX field order and a mixed-currency caution row.
- [ ] Confirm the GitHub Release links to the correct tag and release notes.

Known post-release follow-up:

- Add independent sources and completed-sale evidence.
- Calibrate initial range and sale-review thresholds beyond the v0.4.0 sample.
- Improve edition and condition matching.
- Decide whether market observation history should become durable.

## v0.4.0

Pre-release checks:

- [x] Run `.venv/bin/python -m pytest`.
- [x] Run `.venv/bin/python -m compileall .`.
- [x] Run `git diff --check`.
- [x] Confirm all v0.4.0 commands and documented options match the CLI.
- [x] Confirm the expanded evidence artifacts represent 205 books and 596
  AbeBooks observation rows from the completed experiment.
- [x] Confirm production Research Assessment scoring, signals, weights, and
  bands are unchanged.
- [x] Confirm monthly `update-library` behavior and durable data are unchanged.
- [x] Confirm generated Market Validation and simulation artifacts remain
  ignored and untracked.
- [x] Confirm internal Markdown links resolve.

Release hygiene:

- [x] Confirm `CHANGELOG.md` includes v0.4.0.
- [x] Confirm `docs/RELEASE_NOTES_v0.4.0.md` is ready for the GitHub Release.
- [x] Confirm `docs/RELEASE_READINESS_v0.4.0.md` records the final scope and
  known limitations.
- [x] Confirm README, architecture, roadmap, backlog, and decision documents
  agree that production scoring is unchanged.
- [ ] Confirm the working tree is clean after the PR16 commit.
- [ ] Create the annotated tag with `git tag -a v0.4.0 -m "Release v0.4.0"`.
- [ ] Push the commit and tag.
- [ ] Create the GitHub Release using `docs/RELEASE_NOTES_v0.4.0.md`.

Post-release smoke checks:

- [ ] Confirm `library_pipeline.py --help` lists all v0.4.0 commands.
- [ ] Run one non-network generated-analysis command against preserved local
  artifacts.
- [ ] Confirm the GitHub Release links to the correct tag and release notes.

Known post-release follow-up:

- Design a possible market-likelihood and research-effort split.
- Evaluate another market source and completed-sale evidence.
- Improve candidate review tooling.
- Validate model behavior against future monthly imports.

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

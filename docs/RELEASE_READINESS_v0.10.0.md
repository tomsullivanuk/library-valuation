# Library Valuation v0.10.0 Release Readiness

## Release decision

Library Valuation v0.10.0 is ready for its final release commit, annotated tag,
push, and GitHub Release. The release adds Libib physical-inventory support and
does not alter Amazon acquisition history, market-evidence semantics, Research
Assessments, or valuation behavior.

## Final acceptance evidence

- Untouched Libib source rows: 30.
- Accepted physical holdings: 30.
- Existing catalog links: 22.
- Proposed Libib-created catalog identities: 5.
- Unresolved catalog cases: 3.
- Acquisitions created: 0.
- Duplicate catalog identities created: 0.
- Two fresh previews produced identical completion JSON and preview IDs.
- Summary CSV SHA-256:
  `5d1c6b5314825e92e75a2f257e41945ec8964c33930f3ccaad6ecdda174ba98c`.
- Review workbook SHA-256:
  `979ca9c7adb69904dec537fd40110567534de31e5365493da2fabcbe24939a6d`.
- Real durable repository hashes were unchanged before and after validation.

The workbook contains the expected nine visible, formula-free sheets: Summary,
Physical Review, Catalog Review, Newly Discovered, Location Review, Audit
Coverage, Reconciled Holdings, Import Detail, and Decision Detail.

## Safety and recovery gate

Preview is non-publishing by default. Durable publication requires `--publish`.
The workflow retains byte-for-byte rollback across catalog items, inventory
imports, folder registrations, observations, physical decisions, holdings, and
catalog decisions. Injected import, catalog, artifact-generation, and artifact-
publication failures are covered by automated rollback tests. Exact repeats are
idempotent. Libib creates no acquisition row.

## Privacy and artifact gate

The authoritative Libib export remains ignored and untracked. Synthetic reduced
fixtures contain no private library data. Privacy allowlists exclude arbitrary
raw-evidence keys from reviewer artifacts. No raw export, temporary preview
repository, generated CSV/XLSX, or real durable file belongs in the release
commit.

## Validation commands

The final gate includes:

- `.venv/bin/python -m pytest tests/test_inventory_workflow.py -q`
- all Libib, inventory, catalog, audit, and workflow tests
- `.venv/bin/python -m pytest -q`
- `.venv/bin/python -m compileall -q library_pipeline.py valuation tests`
- Markdown-link, terminology, contradiction, privacy, version-reference,
  architectural-boundary, and `git diff --check` checks

Final results on 2026-07-21 were 20 workflow tests passed, 160 combined Libib/
inventory/catalog/audit/workflow tests passed, and 462 full-suite tests passed.
Compilation, links, privacy, architectural boundaries, terminology,
contradictions, version references, and whitespace checks passed.

## Deferred work

Durable locations and aliases, manual reconciliation editing, condition and
disposition tracking, recursive discovery, Library Explorer, Action Center,
and automated monthly cross-source refresh remain outside v0.10.0.

## Remaining release actions

1. Commit the reviewed PR10 documentation.
2. Create annotated tag `v0.10.0` with message `Release v0.10.0`.
3. Push the final commit and tag.
4. Publish GitHub Release `Library Valuation v0.10.0 — Libib Physical Inventory Integration`
   using `docs/RELEASE_NOTES_v0.10.0.md`.

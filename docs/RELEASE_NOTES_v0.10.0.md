# v0.10.0 — Libib Physical Inventory Integration

Library Valuation v0.10.0 adds a durable, auditable physical-inventory layer
without changing the existing Amazon acquisition history or market-evidence
workflows. An approved Libib export can now be previewed end to end, reviewed,
and explicitly published when its results are acceptable.

## What is new

- Conservative parsing of untouched Libib CSV exports with raw evidence,
  normalized ISBN/date/creator fields, and friendly Excel-corruption diagnostics.
- Registered `input/libib/<audit-area>/` folders that keep operational folder
  context separate from immutable Libib collection-label evidence.
- Strict versioned repositories for imports, immutable observations,
  append-only physical and catalog reconciliation decisions, and current
  physical holdings.
- Physical reconciliation before catalog reconciliation, with stable
  `holding_id` values and unresolved ambiguity preserved for review.
- Exact-ISBN and corroborated metadata catalog matching, plus guarded creation
  of stable catalog identities for strongly identified Libib-only books.
- Generated exception and audit views, including physical, catalog, location,
  audit-coverage, newly discovered, reconciled, import, and decision context.
- A polished nine-sheet inventory review workbook with collector-facing
  guidance, technical provenance, deterministic output, and explicit empty
  states.
- The `update-inventory` workflow, with safe preview by default and explicit
  `--publish` authorization for durable changes.

## Safe operational workflow

Preview one approved audit first:

```bash
python3 library_pipeline.py update-inventory \
  --source input/libib/study/library_20260720_013144.csv \
  --audit-scope "Study" \
  --audit-completeness partial_scope
```

Preview processes temporary copies of durable state and writes only generated
review artifacts. Identical source content, starting state, audit area, scope,
and completeness produce identical preview IDs, completion JSON, summary CSV,
and workbook bytes.

After reviewing the completion summary and workbook, repeat the command with
`--publish` to authorize durable publication. Publication snapshots all seven
mutable catalog/inventory repositories. Any later import, reconciliation,
validation, or artifact failure restores the prior bytes. An exact file repeat
reuses the existing import and creates no duplicate observations, holdings,
decisions, catalog identities, or acquisitions.

Generated review artifacts are:

- `output/inventory_audit_summary.csv`
- `output/inventory_review_workbook.xlsx`

Generated artifacts and raw Libib exports are local private inputs/outputs and
must remain outside version control.

## Recovery guidance

- **Parser or validation failure:** Correct or replace the source export; do not
  resave the authoritative export through Excel. No durable state was accepted.
- **Folder or collection mismatch:** Confirm whether the collection was
  intentionally renamed or the export was placed in the wrong audit-area
  folder. Do not create a location or alias automatically.
- **Malformed durable state:** Stop and restore or repair the affected
  repository from reviewed state. The workflow fails closed rather than
  guessing across an unsupported schema or broken decision chain.
- **Artifact-generation failure:** Fix the output-path or filesystem problem
  and rerun. Publication rolls back if the artifacts cannot be completed.
- **Interrupted or rolled-back publication:** Verify the failure message and
  rerun the same command after the cause is corrected; the pre-run durable
  bytes remain authoritative.
- **Preview used when publication was intended:** Review the preview, then rerun
  with `--publish`. Preview never implies authorization.
- **Safe rerun:** Unchanged input is content-hash idempotent. Changed input uses
  the existing conservative reconciliation rules and may produce review items.

## Acceptance evidence

The untouched 30-row Libib audit was run twice in preview against the current
3,014-row Amazon-derived catalog. Each run produced 30 holdings, 22 existing
catalog links, 5 proposed new catalog identities, 3 unresolved catalog cases,
and 0 acquisitions. Completion summaries, preview identities, summary CSVs,
and workbooks were identical. Real durable repository hashes were unchanged.
The audit was not published during development.

## Important boundaries

- Libib inventory never fabricates acquisition history. Libib `added` is source
  context, not an acquisition date.
- Libib metadata cannot silently overwrite canonical catalog metadata or
  silently relink an existing catalog identity.
- Partial-audit absence does not mark a holding missing; `verified_missing`
  remains explicitly gated.
- Durable location management and source-label aliases remain deferred. Libib
  collection labels remain reviewable source evidence, not `location_id`.
- Manual reconciliation editing, condition tracking, disposition workflows,
  recursive audit-folder discovery, Library Explorer, and Action Center remain
  deferred.
- Market Evidence and Research Assessment refresh are not part of this workflow.

## What comes next

- v0.11.0: Library Explorer and Action Center.
- v0.12.0: reviewed automated monthly refresh and freshness orchestration.

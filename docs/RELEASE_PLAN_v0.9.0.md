# Library Valuation v0.9.0 Release Plan

## v0.9.0 — Full-Library eBay Baseline & Resumable Collection

## 1. Objective

Safely collect production eBay active-listing evidence for the full assessed
library through a resumable, restartable, unattended process. The workflow must
recover from interruption without repeating completed books or duplicating
observations, and must materialize reviewable final artifacts without treating
them as durable valuation history.

## 2. Current Baseline

Version 0.8.0 is released at
`192271ecb658e82cd0a28c181316b5d5bf9476c9`. Production OAuth and Browse access
are validated. A representative 100-book production run produced 229 observed
listings across 87 books and 13 `no_results` rows. The source-aware summary,
reviewer workbook, and static HTML report are implemented and validated.

Seller username has been removed from normalized eBay results, observation
seller fields remain blank, and seller identity is not displayed in reviewer
artifacts. The targeted command is capped at 100 books. The existing full
AbeBooks baseline covers approximately 3,014 assessed catalog items.

## 3. Non-Goals

This release does not add:

- sold/completed eBay evidence;
- Libib integration;
- Library Explorer or a redesigned Action Center;
- one-command monthly refresh orchestration;
- shipping-inclusive pricing or currency conversion;
- automatic high-confidence eBay edition matching;
- changes to AbeBooks core ranges, confidence, or recommendation logic; or
- a complete durable market-history architecture beyond minimum safe resume
  state.

Outputs remain asking-price evidence, not appraisals, fair-market-value
estimates, realized-sale estimates, or expected proceeds.

## 4. Operational Requirements

- Require explicit confirmation of production operation; sandbox must not be
  accepted accidentally for a full run.
- Read credentials only from ignored environment configuration. Never persist
  credentials, tokens, authorization headers, or raw API responses.
- Process a deterministic catalog-item order and checkpoint after each book or
  deliberately small transaction batch.
- Resume by default and skip terminal completed items.
- Survive interruption without corrupting accepted results.
- Bound retries and backoff; do not create retry storms.
- Make pacing, maximum results, retry count, and retry delay explicit and safe.
- Report progress, totals, current item, elapsed time, retry counts, and a final
  outcome summary without leaking protected data.
- Distinguish observed, `no_results`, `no_query`, retryable failures, and
  terminal source-unavailable outcomes.
- Preserve seller suppression throughout state and outputs.
- Keep detailed collection and reviewer artifacts ignored.
- Support unattended overnight use, including a clear exit status and a run
  summary suitable for checking the next morning.

## 5. Resumability Model

### Options considered

1. **Append-only observation CSV with completed-item detection.** Simple, but a
   crash can leave a partial row, one book can produce several rows, retry state
   is awkward, and provenance is inferred rather than explicit.
2. **Single checkpoint or run-state JSON file.** Easy to inspect, but repeated
   whole-file rewrites become fragile unless atomic and can mix configuration,
   item state, and observations into one growing document.
3. **Manifest plus per-item status ledger and incremental observation parts.**
   Separates run identity/configuration from item outcomes and detailed rows;
   supports atomic updates and deterministic final materialization.
4. **Durable database-backed collection history.** Strong long-term option, but
   premature for a generated v0.9.0 baseline and broader than this release.

### Recommendation

Use an ignored run directory containing:

- an immutable run manifest with run ID, source/environment, marketplace,
  input identity/hash, deterministic ordering/version, query-policy version,
  relevant options, start time, and output schema version;
- a per-item status ledger keyed by `catalog_item_id`, stored through atomic
  write-then-replace snapshots after every book (or a very small configured
  batch); and
- one atomically written observation part per completed catalog item, or an
  equivalently transaction-safe item result file.

The ledger records attempt count, selected query/strategy, state, timestamps,
row count, retryability, and sanitized error classification—not tokens, raw
responses, or seller identity. Terminal states are `observed`, `no_results`, and
`no_query`; retryable failures remain pending/failed-retryable. A terminal
source-unavailable classification needs an explicit policy during implementation.

Final CSV/XLSX files are deterministically materialized from completed item
parts only after collection, and may be rebuilt safely. This prevents partial
CSV rows, makes duplicate prevention a key-based invariant, and separates
checkpoint state from final generated detail.

On resume, validate the manifest against the current input and collection
options before reading the ledger. Skip terminal items, retry only eligible
states within configured bounds, and reject incompatible state rather than
silently merging runs. `--restart` creates a new run identity or requires
explicit destructive confirmation; it never silently overwrites the only
checkpoint.

This model is compatible with later monthly refresh because the per-item ledger
can inform a future durable checked/attempted/success/staleness model. v0.9.0
must keep the ledger scoped to safe execution and must not declare it the final
durable market-history schema.

### PR2 implemented state contract

PR2 implements this state layer in `valuation/ebay_full_library_state.py`
without adding a collection command or network behavior. Manifest, ledger, and
observation-part envelopes use explicit `1.0` schema versions. The generated run
layout is:

```text
output/full_library_ebay/
  manifest.json
  ledger.json
  parts/<zero-padded ordinal>-<catalog-id-hash>.json
  run_summary.json        # reserved for later orchestration
  final/                  # reserved for later materialization
```

Manifest compatibility is intentionally limited to fields whose changes make
resume unsafe: schema version, environment, marketplace, input fingerprint,
candidate count/order hash, query-strategy version, observation-schema version,
maximum results, source name, and seller-suppression policy. Delay and retry
settings may vary safely between resumed invocations.

The ledger statuses are `pending`, `in_progress`, `observed`, `no_results`,
`no_query`, `source_unavailable_retryable`, `source_unavailable_terminal`, and
`failed_terminal`. Recovery adopts a valid deterministic part written before an
interruption; otherwise it changes `in_progress` back to `pending`, retaining
attempt/query metadata and adding a sanitized interruption reason. Completed
source outcomes reference one immutable atomic JSON part;
terminal internal failures may be partless. Each part contains an envelope plus
one or more rows with exactly the canonical 25 observation fields, source
`ebay_active_listings`, and a blank seller field.

JSON writes use a same-directory temporary file, flush, file `fsync`, atomic
`os.replace`, and best-effort directory `fsync`; temporary files are cleaned up
on failure. Integrity validation reconciles manifest count/order, ledger item
identity and ordinals, part paths, part schema/identity/outcome, canonical rows,
row counts, and unreferenced parts. Final CSV/XLSX materialization remains
deferred to later PRs.

## 6. Command Design

Proposed separate command:

```bash
.venv/bin/python library_pipeline.py collect-full-library-ebay-observations \
  --summary output/full_abebooks_market_evidence_summary.csv \
  --output-dir output/full_library_ebay \
  --data-dir data \
  --checkpoint output/full_library_ebay/checkpoint \
  --resume \
  --delay 1 \
  --max-results-per-book 3 \
  --max-retries 2 \
  --retry-delay 5 \
  --confirm-production
```

Proposed options:

- `--summary`: required assessed-library input.
- `--output-dir`: required ignored run/output boundary.
- `--data-dir`: explicit durable catalog/acquisition context.
- `--checkpoint`: explicit or safely derived checkpoint directory.
- `--resume`: documented default behavior; may be accepted explicitly for
  clarity.
- `--restart`: start a distinct run or require a second confirmation before
  replacing compatible state.
- `--delay`: positive pacing delay; conservative default one second.
- `--max-results-per-book`: default and initial maximum three.
- `--max-retries` and `--retry-delay`: bounded retry policy.
- `--limit`: optional safe implementation/smoke-test bound, not a way to define
  the full workflow.
- `--confirm-production`: required deliberate production acknowledgement.

The command should also require `EBAY_ENVIRONMENT=production` and reject any
other value. Resume should be the safe default when compatible state exists;
restart must never be implicit. Partial item results and state are written
incrementally. Final CSV is assembled deterministically from completed parts;
XLSX should normally be built only after a coherent CSV is available.

### PR3 implemented orchestration boundary

PR3 adds `collect-full-library-ebay-observations` with the options above. Both
output and checkpoint paths must resolve below `output/`, and neither may be the
output root itself. Production environment and `--confirm-production` are
mandatory. Candidate IDs are unique and sorted deterministically; `--limit`
selects only the first compatible bounded subset and becomes part of manifest
count/order compatibility.

New runs create manifest, ledger, `parts/`, and reserved `final/` state. Resume
is the default, validates the manifest and checkpoint, recovers interrupted
entries, skips terminal items, and continues retry-eligible work. `--restart`
renames the whole existing run directory to a timestamped sibling archive and
then creates fresh state; it never deletes or silently overwrites the only
checkpoint.

Every transition is saved atomically. No-query, observed, no-results, and
terminal source-unavailable outcomes receive immutable parts. Transient/rate-
limit failures retry within configured bounds; authentication/credential/token
failures terminalize the current item and stop the run; unexpected sanitized
failures become terminal for that item without stopping later candidates. A
safe aggregate `run_summary.json` records completion/status/attempt counts,
timing, resume count, paths, schemas, archive, and stop reason. Final combined
CSV/XLSX remains deferred.

The existing reusable active-listings client currently acquires an application
token for each search. PR3 preserves that tested behavior rather than adding a
new token lifecycle. It is safe but potentially inefficient for a multi-hour
run; token reuse/renewal and long-run authentication behavior remain explicit
PR4 hardening work.

## 7. Rate-Limit and Runtime Planning

The initial input is approximately 3,014 books. Under the current conservative
query policy, each book normally issues one primary Browse search, usually by
ISBN-13, with no more than three returned results. A one-second inter-book delay
implies at least about 50 minutes of deliberate pacing, before OAuth, request
latency, retries, checkpoint writes, and final materialization. A practical run
may take materially longer; no completion-time guarantee should be documented.

Implementation must inspect actual eBay headers/errors where safely available,
handle rate-limit responses with bounded backoff, refresh expired application
tokens safely, and stop rather than retry storm. Do not hardcode assumptions
about production quotas until verified. The command should work under
`caffeinate` and unattended overnight, while documenting that laptop sleep,
network changes, or process termination are normal resume scenarios.

## 8. Query Strategy

Retain the existing order:

1. ISBN-13;
2. ISBN-10;
3. title plus author; and
4. usable title.

Most assessed books are expected to use ISBN-13. The chosen query and strategy
must remain auditable. eBay match confidence remains `unknown`; ISBN lookup does
not guarantee edition, format, condition, translation, or bundle identity, so
human review remains required.

## 9. Outputs

| Artifact | Role | Durability |
|---|---|---|
| Run manifest | Run identity, input/configuration provenance | Minimum ignored checkpoint state |
| Per-item ledger and item parts | Resume, retry, outcome, crash-safe detail | Minimum ignored checkpoint state |
| Full eBay observations CSV/XLSX | Normalized listing/status detail | Generated, ignored |
| Run summary | Counts, timing, retries, failures, completion | Generated, ignored |
| Multi-source summary CSV/XLSX | AbeBooks plus supplemental eBay evidence | Generated, ignored |
| Reviewer workbook | Source-aware review artifact | Generated, ignored |
| Static HTML report | Source-aware sharing/review artifact | Generated, ignored |

No generated output, checkpoint, cohort, credential, token, header, or raw API
response is committed. Promotion of any collection state to durable repository
data requires a separate design decision.

## 10. Proposed PR Sequence

1. **PR1 — Release plan and operational design.** Finalize command boundaries,
   state invariants, failure taxonomy, and artifact policy.
2. **PR2 — Checkpoint schema and pure state management.** Implement manifest,
   ledger, atomic item-result writes, compatibility validation, deterministic
   materialization, and network-independent tests.
3. **PR3 — Full-library command with mocked collection.** Add the production
   guard, selection/order, incremental processing, progress, and safe limits.
4. **PR4 — Interruption, resume, token, and retry hardening.** Exercise crashes,
   partial writes, incompatible state, bounded backoff, and duplicate prevention.
5. **PR5 — Small bounded production resume validation.** Interrupt and resume a
   safe cohort; document privacy, state, pacing, and failure behavior.
6. **PR6 — Full-library production run and evidence-quality report.** Run the
   approximately 3,014-book baseline and document coverage, runtime, failures,
   privacy, and matching limitations.
7. **PR7 — Full summary and reviewer-artifact regeneration.** Produce and
   reconcile the multi-source summary, workbook, and HTML report locally.
8. **PR8 — Final documentation and release readiness.** Finalize release notes,
   operational instructions, limitations, validation, and artifact audits.

Each PR remains reviewable and uses fixture/mocked tests; only explicitly scoped
validation PRs contact production.

## 11. Acceptance Criteria

- A separate `collect-full-library-ebay-observations` command exists.
- Production environment and explicit confirmation guards are enforced.
- Compatible runs resume safely; incompatible state is rejected.
- Successful, `no_results`, and `no_query` items are skipped on resume.
- Interrupted execution continues without duplicate successful observations.
- Partial writes cannot be mistaken for completed item results.
- Retry behavior is bounded, paced, classified, and independently testable.
- Retryable failures can be retried under an explicit policy.
- Progress and final run summaries are useful without exposing secrets.
- Seller identity remains absent from client normalization, checkpoint state,
  observations, notes, summaries, and reviewer artifacts.
- Full observation and multi-source summary CSV/XLSX artifacts are produced.
- Source-aware workbook and HTML report regenerate and reconcile successfully.
- AbeBooks core ranges, confidence, and recommendations remain unchanged for
  mixed-source books.
- Tests are deterministic and network-independent.
- Credentials, tokens, raw responses, checkpoints, and generated artifacts
  remain ignored and uncommitted.
- The full production run and its evidence-quality limitations are documented.

## 12. Risks and Open Questions

- What are the verified production Browse quota and rate-limit signals?
- Will application-token lifetime require transparent renewal during the run?
- Which API/network failures are retryable, and which must stop the run?
- Should `source_unavailable` retry automatically on resume or require an
  explicit flag after a likely credential/configuration failure?
- Is `no_results` terminal for the baseline, and when should it become stale?
- What atomic format and validation/checksum best detects checkpoint corruption?
- Should item parts be JSON, CSV, or another simple inspectable format?
- Should checkpointing occur after every item or a configurable small batch?
- How should restart preserve or archive prior run state?
- How should listings changing during a multi-hour run be described in
  provenance and reviewer guidance?
- How will a later monthly refresh distinguish baseline completion from stale
  evidence without treating the v0.9.0 ledger as final durable history?
- What is the measured runtime, and what guidance is needed for laptop sleep,
  `caffeinate`, network loss, and disk space?
- Should XLSX be materialized only at completion, on demand, or after a fully
  coherent checkpoint snapshot?

These questions should be resolved incrementally with fixture tests and small
production validation; the plan intentionally does not pretend they are final.

## 13. Deferred Items

- Libib physical-inventory integration.
- Library Explorer and Action Center redesign.
- Automated monthly refresh orchestration and final durable freshness state.
- Sold/completed eBay evidence.
- Shipping-inclusive pricing.
- Currency normalization/conversion.
- Automated eBay match-confidence scoring and edition matching.
- Additional market-evidence sources and richer reviewer workflow.

Seller suppression remains an established privacy rule. AbeBooks remains the
primary/core range source for mixed-source evidence unless a future reviewed
release explicitly redesigns that behavior.

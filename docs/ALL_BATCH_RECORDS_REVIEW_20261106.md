# Records-only check review across all frozen batches

The owner requested the same records-only adjudication for checks from the remaining
batches, keeping estimates unchanged and work in PR #2. At review time, collection
was still waiting for quota after batch 19. No later market results were invented
or requested to complete this source-record review.

## Scope and outcome

Identification checks in the pinned reviewer depend on frozen catalog, acquisition,
inventory observation and source-page records, not on live asking prices. That lets
us screen **all 2,435 records in 98 batches now**. Only records with edition or
inferred-copy flags are adjudicated; ordinary market-research and grading tasks
are not silently closed.

The records-dependent checks exactly match all 40 flags already produced in the
19 completed batches. The same unchanged rules and frozen inputs identify another
122 potential flags across 101 books in the unfinished batches. This is a forecast
of identification checks only, not a claim of completed market collection.

| Cumulative source-review result | Count |
| --- | ---: |
| Books with identification checks reviewed | 133 |
| Identification flags covered | 162 |
| Edition flags | 129 |
| Inferred-copy flags | 33 |
| Edition questions resolved from records | 77 |
| Inferred-copy questions resolved at source-profile level | 8 |
| Duplicate inferred-copy questions merged | 23 |
| Distinct remaining physical-book tasks | 54 |
| Format/binding/market-variant tasks | 43 |
| Missing edition-evidence tasks | 6 |
| Identifier-focused tasks | 5 |

The 54-task cumulative checklist includes the previous **14** and **40 additional**
tasks from unfinished batches. It covers this 2,435-record run; the separate
original 130-book pilots remain in their earlier reports. There are currently 14
physical tasks associated with completed batches. The other 40 can be addressed
when those books are handled, even before their market collection finishes.

Resolved source profiles do not verify a physical ISBN, upgrade work-link confidence,
assign an actual condition or approve a value. Some source profiles are a known
edition family with the exact later printing still unknown; no first-printing
premium is inferred. Format and identifier question types can overlap in their
reasoning, although each remaining book has one consolidated task.

## Additional records findings

- Four inventory records contain mutually consistent ISBN-10/13 forms that differ
  from the purchase/catalog target. They supply a recorded source identifier,
  rather than an owner task to reread it. Agent research must use that inventory
  profile separately and preserve the catalog/purchase provenance; no metadata or
  pricing correction is applied during the frozen run.
- A separate record has two valid but incompatible inventory identifiers. The
  checksum cannot select the correct one, so the actual printed identifier remains
  a physical task. Records with neither an identifier nor source-page evidence
  remain narrowly scoped physical questions, even if a purchase ISBN exists.
- Regional identifiers on one documented publication page are retained as regional
  alternatives without inventing a binding or asking the owner to choose a country.
- Re-reading an existing copyright photograph clarified that both publication-line
  identifiers are labelled paperback, rather than representing hard/paper choices.
  The valid identifier is bibliographic evidence only. Conflicting publication-line
  and cataloging-block strings remain separately rejected/held. The unchanged image
  is privately copied and fingerprinted; original frozen transcriptions remain intact.
- Two further recorded alternatives fail checksums. Another source explicitly
  rejects an identifier even though its checksum passes. None is repaired or
  promoted into a candidate. The remaining physical questions name the exact gap.
- Inferred-only questions target the specific unbarcoded observation and location,
  not every copy of the work. Evidence from an identified copy cannot discharge
  another copy's question. Known earlier printings and documented separate copies
  are kept distinct; the inventory's already-recorded two-copy holding is preserved.

## Implementation and future arrivals

`valuation.records_check_scope.prepare_scope` freezes all predicted identification
checks and the per-batch inputs under the existing job manifest. It compares completed
batch checks exactly, and requires source/code integrity via the existing read-only
worker guard. `validate_completed` can be run after later batches finish: it matches
exact scope, questions, target observations, source inputs and adjudication provenance.
Changed or unreviewed flags are rejected rather than silently inheriting a resolution.
It writes a fresh coverage receipt and a physical-check CSV limited to completed
batches, without overwriting previous validation snapshots.

The authored adjudication advances to v2. It supports inferred-only flags, consistent
target inventory evidence, unresolved cases without source-page notes, copy-specific
locations, source-rejected identifiers, and fingerprinted additional existing images.
Unresolved questions are never merged away unless a same-book edition task actually
exists. The original v1 report remains preserved.

The records-only review is complete for this frozen source scope now, independently
of when market requests complete. It does not require another periodic collector or
modify the running worker to consume a changing input. Original raw flags remain in
immutable batch reports; the cumulative sidecar is the owner-facing identification
checklist. It is not a new publication path or approval of candidate estimates.

## Private artifacts and verification

The Mini and laptop copy retain the new scope, authored findings, supplemental image,
all 133 decisions, 54-task checklist, and coverage receipt under:

`output/valuation_review_20261106/all_batch_check_review_v1/`

The entry point is `results/review.html`; the owner-only task download is
`results/physical_checks_only.csv`. `coverage_at_review/` separates the 40 arrived
flags from 122 pre-reviewed flags awaiting collection. Findings and images are not
committed to GitHub.

Canonical files, the frozen worker's code/inputs/completed outputs, quota ledger
and job status matched before and after. Source requests and estimate changes were
zero; all actual grades remain unassigned and physical grading stays deferred.

**726 tests pass on laptop and Mini.** Eight additional cases cover inferred-only
status, consistent versus conflicting identifiers, evidence and locations for the
correct copy, checksum-valid but source-rejected identifiers, fingerprinted stored
images, pre-review followed by exact later-arrival matching, and refusing changed
checks or job manifests. Artifact checks confirm 133 book sections, 162 decisions,
54 distinct tasks, preserved earlier 14 questions, valid downloads and matching
input/image fingerprints. Compilation and whitespace checks pass.

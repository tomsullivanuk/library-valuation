# Library Valuation v0.10.0 Release Plan

## v0.10.0 — Libib Physical Inventory Integration

## 1. Release Theme

Add a durable, auditable physical-inventory layer from Libib exports without
confusing possession evidence with catalog identity or acquisition history.

## 2. Problem Statement

The released v0.9.0 system has durable catalog identities, Amazon acquisition
history, bibliographic enrichment, research state, and generated market-review
artifacts. It cannot reliably answer whether a cataloged book is currently
present, how many physical copies exist, where they are, or when possession was
last checked. Amazon orders are evidence that an item was acquired, not proof
that it is still owned.

Libib can supply current or recently observed inventory evidence, but its
identifiers and user-edited metadata must not replace `catalog_item_id` or
silently overwrite canonical bibliographic fields. Version 0.10.0 establishes
that boundary and makes unmatched, ambiguous, duplicate, and incomplete
inventory evidence reviewable. It also permits strong Libib evidence to create
a new catalog identity for a non-Amazon book and treats progressive audit scope
as first-class provenance rather than assuming every import covers the library.

## 3. Current State After v0.9.0

- `data/catalog_items.csv` owns stable `catalog_item_id` values.
- `data/acquisitions.csv` preserves Amazon purchase facts and quantities.
- `data/import_manifest.csv` records Amazon full-history imports, but is not yet
  a general source-import repository.
- The conceptual data model already names Source Import, Source Item,
  Acquisition, and Owned Copy / Inventory Holding; only the first three have
  partial or concrete Amazon representations.
- No durable physical-holding, inventory-match, or inventory-review repository
  exists.
- Generated CSV, XLSX, HTML, and checkpoint artifacts are projections or
  execution state, not canonical durable data.
- v0.9.0 completed resumable full-library eBay collection. It deliberately
  deferred Libib, shared presentation, and monthly orchestration.

## 4. User Outcomes

By the end of v0.10.0, a user can:

- import a supported Libib export with provenance and repeat-import detection;
- preserve every accepted source row, including unmatched and ambiguous rows;
- distinguish acquisition history from believed current physical inventory;
- add a confidently identified non-Amazon book to the durable catalog and link
  it to a holding without fabricating an acquisition;
- represent separate copies of the same catalog item with stable `holding_id`
  values;
- see how and why inventory evidence was matched to a catalog item;
- review unmatched, ambiguous, duplicate, location, quantity, and audit
  exceptions in a generated artifact;
- re-import an identical or newer export without silently duplicating holdings
  or losing user-maintained inventory state; and
- recover safely from an interrupted durable write.

## 5. Scope

- Profile representative Libib CSV or batch exports and document their actual
  schemas and semantics.
- Parse supported export types behind a Libib-specific source boundary.
- Add versioned durable inventory import, source-item, holding, match, and
  narrowly scoped review/override state.
- Establish the shared source-family direction as Amazon Import, Libib Import,
  and Manual Entry without migrating historical Amazon structures.
- Add stable project-owned physical locations and conservative mapping from
  preserved Libib catalog/location labels.
- Allow sufficiently strong, unambiguous Libib evidence with no existing match
  to initialize a new catalog item and `catalog_item_id`; preserve unknown
  acquisition origin/date without creating a synthetic acquisition record.
- Implement conservative, deterministic catalog matching with explicit method,
  confidence, candidates, and provenance.
- Reconcile partial, location-specific, filtered, full, and unknown-scope audit
  imports without treating missing rows as automatic dispositions.
- Generate exception views and an inventory reviewer artifact.
- Provide a separate, validated end-to-end Libib import workflow.
- Update documentation, fixtures, release notes, and release-readiness evidence.

## 6. Explicit Non-Goals

Version 0.10.0 will not:

- change an existing `catalog_item_id` or derive a new ID value from Libib data;
- treat ISBN, title, author, Libib IDs, or fingerprints as project identity;
- rewrite canonical catalog metadata from Libib without a separate explicit
  catalog-correction workflow;
- infer current possession from Amazon acquisitions alone;
- infer sale, donation, disposal, or loss solely from absence in a later Libib
  export;
- implement Library Explorer, Action Center, or their shared presentation model;
- implement unified or automated monthly refresh orchestration;
- change valuation, market-evidence, or research-assessment semantics;
- add a database, split `library_pipeline.py`, or perform unrelated cleanup; or
- claim parser or column behavior before representative exports are profiled.

## 7. Architectural Principles

1. `catalog_item_id` remains the durable intellectual/catalog identity.
2. `holding_id` is the project-owned, stable identity of one physical copy.
3. Source identifiers and normalized bibliographic values are matching evidence,
   never canonical project identity.
4. Acquisition, inventory, audit, and disposition are different facts with
   different lifecycles.
5. Catalog creation, physical-holding creation, and acquisition recording are
   separate operations. A holding and catalog item do not require a known
   acquisition.
6. Libib evidence is append-preserving and auditable; canonical catalog metadata
   is not silently overwritten.
7. Each physical copy is independently representable, including identical
   copies and quantity-expanded source rows.
8. Weak, ambiguous, invalid, and unmatched rows are preserved for review before
   any new catalog identity is created.
9. Audit conclusions are scoped. No match defaults to `not_yet_audited`, not
   missing, unless an explicit completed scope supports a stronger conclusion.
10. User-confirmed matches and inventory state survive regeneration and re-import.
11. Generated reports and workbooks remain reproducible projections.
12. Schema changes are explicit and versioned; interrupted multi-file writes do
    not expose a partially accepted import.
13. The shared source model has three principal families: Amazon Import, Libib
    Import, and Manual Entry. Scanning is an input mechanism, not a source family.
14. `location_id` is durable physical-location identity. Source labels are
    evidence; renames and holding moves preserve catalog and holding identities.

The detailed contract is in [LIBIB_INVENTORY_DESIGN.md](LIBIB_INVENTORY_DESIGN.md).

## 8. Proposed PR Sequence

### PR1 — Libib Physical Inventory Design and Release Plan

**Purpose:** Establish the reviewed release boundary, terminology, tentative
entities, matching policy, idempotency rules, and implementation sequence.

**Major deliverables:** This release plan; the Libib inventory design; narrow
links and terminology updates in current documentation.

**Exclusions:** Parser code, schemas, fixtures presented as representative
exports, CLI changes, and production behavior.

**Tests or validation:** Existing test suite; repository checks; Markdown link
verification; terminology audit; `git diff --check`.

**Exit criteria:** Both documents are internally consistent, distinguish settled
decisions from PR2 questions, and introduce no behavior change.

### PR2 — Libib Export Profiling and Parser

**Purpose:** Replace export assumptions with evidence and implement a
privacy-conscious, source-specific parser.

**Major deliverables:** Sanitized representative fixtures; format/column profile;
explicit-path and discovery rules; normalized parser contract; file hashing;
validation diagnostics; fixture-driven tests.

**Exclusions:** Durable writes, catalog matching, holdings, and reviewer UI.

**Tests or validation:** CSV dialect, encoding, missing/extra column, invalid
value, quantity, Libib catalog/location semantics, stable-ID, privacy, and
deterministic parsing tests.

**Exit criteria:** Supported export variants and completeness signals are
documented; every normalized field traces to source evidence; unsupported
inputs fail without mutation.

### PR3 — Durable Inventory Import and Physical-Item State

**Purpose:** Add versioned repositories for import evidence and stable physical
copy identity.

**Major deliverables:** Durable inventory imports, source items, and holdings;
atomic staged writes; exact-file idempotency; quantity expansion policy;
audit-scope and completeness provenance; durable inventory-location repository;
tentative alias repository evaluation; operational audit-area folder registration
under `input/libib/`; explicit-file and one-directory import boundaries;
collection-label mismatch review; repository validation and migrations or
explicit compatibility gates. Recursive all-folder discovery remains deferred.

**Exclusions:** Fuzzy catalog matching, exception workbook, and disposition
inference from absence.

**Tests or validation:** Identity stability, repeat import, interrupted write,
duplicate prevention, quantity, location rename, holding move, label mapping,
unmapped-label review, first/subsequent folder import, renamed/misfiled export,
folder rename, hash-versus-filename identity, user-field preservation, and
schema-version tests.

**Exit criteria:** The same accepted evidence cannot create duplicate imports or
holdings, and verified/user-maintained holding fields survive reconciliation.

### PR4 — Inventory Observation and Reconciliation Design

**Purpose:** Settle the durable evidence/current-belief boundary and physical
reconciliation workflow before implementation.

**Major deliverables:** Inventory Observation recommendation and lifecycle;
holding lifecycle; immutable evidence rules; append-preserving reconciliation
decision concept; closed outcome taxonomy; physical-before-catalog pipeline;
tentative repositories; alternatives; and explicit PR5 boundary.

**Exclusions:** Repository, reconciliation, matching, importer, CLI, report, or
review-workbook implementation.

**Tests or validation:** Documentation links, terminology and contradiction
checks, full suite, and confirmation that no production behavior changed.

**Exit criteria:** Observation existence, holding evolution, reconciliation
ordering/outcomes, and PR5 implementation scope are unambiguous.

### PR5 — Durable Inventory Observations and Holding Reconciliation

**Purpose:** Preserve immutable row-level evidence and reconcile it
conservatively to current physical holdings.

**Major deliverables:** Versioned observation repository; deterministic
observation identity; append-only decisions; physical candidate generation;
closed outcomes; exact high-confidence existing-holding acceptance; conservative
changed/duplicate/edition/quantity review; scope-aware non-observation behavior;
atomic publication; source-total balancing; and compatible PR3 holding migration
only where required.

**Exclusions:** Catalog matching or creation, canonical metadata changes,
locations/aliases, reports, workbooks, recursive discovery, and CLI workflow.

**Tests or validation:** Observation immutability/idempotency, unchanged and
changed rows, ISBN corrections, candidate ambiguity, duplicate copies, quantity
groups, new holdings, partial/complete audits, non-mutation on unresolved cases,
transaction recovery, migration compatibility, and source-total balancing.

**Exit criteria:** Every accepted import row persists as immutable evidence;
every holding effect has an auditable decision; and no ambiguous evidence
creates, merges, removes, or mutates a holding.

**Implemented contract:** Observation and decision repositories use schema
version 1; holdings use schema version 2 with fail-closed PR3 compatibility.
Observation IDs are import-scoped and deterministic; decisions are append-only
with validated single-chain supersession; automatic holding changes are limited
to exact same-folder reobservation and sufficiently identified new one-copy
evidence. Unresolved rows persist without holding mutation. Audit absence is a
non-mutating classifier only, and `verified_missing` remains deferred.

### PR6 — Catalog-to-Inventory Matching

**Purpose:** Link inventory evidence to catalog items conservatively and
explainably.

**Major deliverables:** Matching cascade; candidate records; match method,
confidence, count, rule version, and evidence snapshot; manual confirmation and
supersession behavior; automatic creation of a new catalog identity from strong,
unambiguous no-match evidence, followed by holding linkage without requiring an
acquisition. PR9 validates this behavior end to end.

**Exclusions:** Title-only automatic matches, canonical metadata updates, and
presentation redesign.

**Tests or validation:** ISBN-13, ISBN-10 conversion, title/author, edition
evidence, ties, duplicate catalog records, invalid ISBN, unmatched, override,
rule-version, confident new-catalog creation, acquisition-free holding, and weak
evidence non-creation tests.

**Exit criteria:** No ambiguous row is force-matched or creates a catalog item;
every accepted link or new identity is auditable and can be superseded without
deleting history.

**Implemented contract:** Catalog reconciliation decisions use schema version
1 and are append-only; holdings remain schema version 2 and the historical
nine-column catalog header remains unchanged. Unique valid ISBN matches and
publisher-corroborated title-plus-creator matches may link automatically.
Strong no-candidate ISBN/title/creator evidence may initialize one catalog item
and link its accepted physical holding without creating an acquisition. Title-
or creator-only, duplicate, conflicting, ineligible, edition-ambiguous, and
relink evidence remains reviewable and non-mutating. Catalog items, decisions,
and holding links publish atomically. PR7 remains generated exception/audit
views; it does not need a sequence change.

### PR7 — Inventory Exceptions and Audit Views

**Purpose:** Derive complete, deterministic queues for inventory discrepancies
and follow-up.

**Major deliverables:** Exception taxonomy and generated CSV/XLSX-ready views;
audit freshness policy; separate confirmed-holding, not-yet-audited,
outside-scope, and completed-scope-not-found views; unmapped, ambiguous, and
logical-versus-physical location-label exceptions.

**Exclusions:** Editing workflow, Library Explorer, Action Center, and automated
disposition changes.

**Tests or validation:** Fixture coverage for every exception category,
deterministic ordering, deduplication, and partial/location/filtered/full/unknown
scope behavior, including non-invalidation across scopes.

**Exit criteria:** Every unmatched or ambiguous row appears in a review view and
absence-based exceptions carry the correct completeness caveat.

**Implemented contract:** `valuation/inventory_audit.py` builds one generated,
source-neutral presentation model and writes deterministic
`output/inventory_audit_summary.csv` plus
`output/inventory_review_workbook.xlsx`. Explicit supersession chains determine
current decisions and malformed chains fail closed. The workbook contains
Summary, Physical Review, Catalog Review, Audit Coverage, Location Review,
Newly Discovered, Reconciled Holdings, Import Detail, and Decision Detail.
Repository reads are allowlisted and validated; raw-evidence JSON is not
exposed. Generation does not import, match, append decisions, or mutate catalog,
holding, acquisition, or location state.

### PR8 — Inventory Reviewer Artifact

**Purpose:** Complete reviewer usability, definitions, privacy inspection, and
visual acceptance over the PR7 generated workbook and shared presentation
model. PR8 must not create a second presentation model.

**Major deliverables:** Reviewer acceptance refinements, a data dictionary and
regeneration notes, plus focused visual or navigation improvements justified by
PR7 artifact inspection. The core summary and detail sheets already exist.

**Exclusions:** Reading edits back from the workbook and the v0.11.0 shared UI.

**Tests or validation:** Workbook structure/content tests, formula-free data
checks where practical, privacy inspection, and visual acceptance testing.

**Exit criteria:** A user can understand what is believed, observed, unresolved,
and stale without treating the artifact as the durable repository.

**Implemented contract:** PR8 retains the PR7 presentation model and business
semantics while making the workbook collector-facing. Sheet order follows the
review path from summary and identity exceptions through newly discovered,
location, audit, reconciled, and technical provenance views. Suggested next
steps, book descriptions, and explanations precede stable IDs. Empty sheets
contain a concise generated message, all worksheets remain visible, and no
formulas or editable workflow fields are introduced. Shared workbook styling
adds readable headers, alternating rows, section emphasis, hidden gridlines,
fixed package timestamps, and text-preserved ISBNs without changing durable
state or reconciliation behavior.

### PR9 — End-to-End Import Workflow and Validation

**Purpose:** Connect parse, persist, match, reconcile, and generate steps in a
safe user-invoked workflow.

**Major deliverables:** Explicit import entry point; dry validation before
commit; transaction/recovery behavior; summaries; representative end-to-end
acceptance evidence.

**Exclusions:** Amazon/market unified refresh and unattended scheduling.

**Tests or validation:** Clean import, exact repeat, changed full export, partial
batch, progressive/location-specific audit, Libib-only catalog-and-holding
creation without acquisition, interruption/recovery, incompatible schema, and
privacy tests.

**Exit criteria:** Accepted imports are atomic and repeatable, failures preserve
prior durable state, and all reconciliation outcomes balance to source totals.

**Implemented contract:** `update-inventory` accepts one explicit Libib file or
one selected audit-area directory. It defaults to a full preview against
temporary repository copies and requires `--publish` for durable mutation. The
workflow reuses the PR2–PR8 parser, repositories, reconciliation functions, and
presentation model; it adds no identity rules. Publication has an outer rollback
boundary across catalog items and all six mutable inventory repositories, while
the acquisition repository remains read-only. Audit artifacts are staged and
published only after validated processing. Exact content-hash repeats are
idempotent, completion output is machine-readable JSON, and Libib creates no
acquisition history.

### PR10 — Documentation and Release Readiness

**Purpose:** Finalize user guidance and prove the release boundary.

**Major deliverables:** README usage, architecture/data-model alignment, release
notes, release-readiness report, changelog, operational and recovery guidance.

**Exclusions:** New features or opportunistic refactors.

**Tests or validation:** Full suite, compile check, link check, clean fixture
run, artifact audit, privacy audit, and release checklist.

**Exit criteria:** Acceptance criteria below are evidenced, limitations are
explicit, generated/private artifacts are uncommitted, and the repository is
ready to tag.

## 9. Release Acceptance Criteria

- Supported Libib inputs are evidence-backed and documented.
- Shared architectural terminology uses Amazon Import, Libib Import, and Manual
  Entry as the three principal source families; barcode scanning and acquisition
  origins do not create additional top-level families.
- Exact-file imports are detected and do not duplicate durable records.
- Libib files normally retain their original filename under one registered
  audit-area directory below `input/libib/`; folder names remain operational
  labels and never become import or location identity.
- First import registers the audit-area folder only after successful parsing and
  preserves the observed collection label exactly.
- A subsequent folder/collection mismatch produces
  `collection_label_changed_or_misfiled` with both labels, path, and review
  guidance; it does not create a location or remap an alias automatically.
- File hash and `inventory_import_id` determine import history. Filename,
  modification timestamp, folder name, and `folder_id` do not.
- Renaming a folder can preserve `folder_id` only after manual confirmation; an
  unrecognized path is not automatically joined to a registration.
- Import provenance includes a project ID, content hash, source type, parser and
  schema versions, import time, row counts, and completeness classification.
- Every accepted source row is retained or has an explicit rejection diagnostic.
- Existing `catalog_item_id` values remain unchanged, new IDs are project-owned,
  and canonical metadata is not silently overwritten.
- Separate copies receive stable, unique `holding_id` values.
- Renaming a durable physical location preserves its `location_id` and every
  linked `holding_id`.
- Moving a holding changes its current believed `location_id` without changing
  `holding_id` or `catalog_item_id` and records updated verification context.
- Several inconsistent Libib labels can map, after confirmation, to one durable
  project location.
- An unmapped or ambiguous Libib location label remains preserved source
  evidence and appears for review without creating a location automatically.
- The workflow distinguishes a logical Libib catalog/group label from a
  confirmed physical location and does not assign physical-location confidence
  without mapping and audit evidence.
- A confidently identified Libib-only physical book creates a new durable
  `catalog_item_id` and linked holding with source provenance, no acquisition
  row, and unknown acquisition origin/date.
- Weak, conflicting, or ambiguous Libib evidence does not create a catalog item
  before manual review.
- Re-import and newer-export reconciliation preserve holding identities where
  evidence is sufficient and preserve user-maintained fields.
- Match records expose method, confidence, candidate count, evidence, rule
  version, status, and supersession provenance.
- Ambiguous and unmatched rows are visible; title-only evidence never produces
  an automatic high-confidence match.
- Missing rows never automatically become sold, donated, missing, or discarded.
- Import provenance preserves whether audit scope is partial, location-specific,
  filtered, full, or unknown and whether that scope is complete.
- A catalog item without Libib evidence defaults to `not_yet_audited` or
  `outside_audit_scope`; `verified_missing` requires an explicitly completed
  applicable audit scope.
- A later partial import does not invalidate a holding confirmed in another
  audit scope.
- Generated views separate confirmed holdings, not-yet-audited items,
  outside-scope items, and items not found inside a completed scope.
- All documented exception categories appear in generated review views.
- Interrupted writes leave the last accepted state intact and can be retried.
- Generated reviewer artifacts are reproducible and contain no unintended
  private source fields.
- Existing tests and new inventory tests pass without valuation or market-model
  regressions.

## 10. Risks and Unresolved Questions

PR1 settles the identity, authority, overwrite, audit-scope, review, new-catalog,
and conservative-match boundaries. PR2 must resolve the actual Libib export
variants and columns, stable identifier availability and scope, quantity and
location semantics,
tags/groups/collections, completeness signals, row order stability, encoding,
and the privacy surface. The design must be revised if representative evidence
contradicts its tentative fields or reconciliation assumptions.

Additional risks include source identifiers changing across exports, one row
representing a set rather than a copy, quantity reductions lacking disposition
meaning, duplicate catalog records creating false certainty, and manual Libib
metadata diverging from bibliographic sources. All require visible exceptions
rather than optimistic mutation.

## 11. Documentation and Release Readiness

- Keep this plan and the design document current as PR2 evidence resolves open
  questions; record material decisions in the design decision log.
- Update `ARCHITECTURE.md` and `DATA_MODEL.md` when tentative repositories become
  implemented contracts, not before.
- Add operational instructions only when the workflow exists.
- Add release notes, changelog, schema/migration guidance, recovery procedure,
  fixture provenance, privacy audit, and exact acceptance results in PR10.
- Preserve historical release documents and do not rewrite v0.9.0 evidence.

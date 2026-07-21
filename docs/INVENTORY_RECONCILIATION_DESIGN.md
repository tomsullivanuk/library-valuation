# Inventory Observation and Reconciliation Design

## 1. Decision

Library Valuation should introduce a durable **Inventory Observation** before it
implements reconciliation.

The durable inventory model should distinguish three kinds of truth:

1. An **Inventory Import** records the accepted source file and declared audit
   context.
2. An **Inventory Observation** records immutable row-level evidence from that
   import.
3. An **Inventory Holding** records the project's current belief about one
   physical copy or, temporarily, one unresolved quantity group.

An append-preserving **Inventory Reconciliation Decision** should connect an
observation to zero, one, or several candidate holdings and record how the
current belief was reached. It is not source evidence and should not be folded
into either the observation or holding.

**Sequence note:** Earlier PR1 text in `LIBIB_INVENTORY_DESIGN.md` used “PR4”
for catalog matching before this design step was inserted. The current sequence
in `RELEASE_PLAN_v0.10.0.md` controls: this document is PR4, observation and
holding reconciliation implementation is PR5, and catalog matching is PR6.

This separation is required by the evidence already encountered in PR2 and PR3:
Libib supplies no stable copy identifier; title, creator, and ISBN values may be
corrected; collection labels may be renamed; quantities greater than one remain
semantically uncertain; and partial audits cannot support absence conclusions.
PR3 can safely create first-pass holdings from one import, but its changed-row
guard must reject an entire later import because it has no immutable row-level
place to retain unresolved evidence. Durable observations remove that pressure
without forcing an identity decision.

## 2. Entity Responsibilities

### Inventory Import

**Purpose:** Identify one accepted source file and its import-wide provenance.

**Owns:** Source hash, original filename, parser/schema version, imported time,
folder registration reference, descriptive audit scope, completeness, source
collection label, and accepted row count.

**Does not own:** Physical-copy identity, row-level bibliographic evidence,
catalog links, location identity, or reconciliation conclusions.

### Inventory Observation

**Purpose:** Preserve what one source row or logical source record asserted at a
particular import boundary, whether or not its physical or catalog identity can
be resolved.

**Lifecycle:** Created only after the parent import parses and validates. Once
accepted, it is immutable. It may remain unreconciled, receive one or more
reconciliation decisions, or be referenced by a later superseding decision. It
is never deleted merely because a later export omits or contradicts it.

**Relationship to imports:** Every observation belongs to exactly one accepted
`inventory_import_id`. One import owns zero or more observations. Exact-repeat
import detection prevents a second observation set for the same accepted file
hash and parser contract.

**Relationship to holdings:** An observation may resolve to no holding, one
holding, or—when quantity/group semantics are unresolved—several candidate or
eventual holdings. The link belongs in reconciliation history, not as a mutable
authoritative field on the observation.

**Durability:** Durable evidence. Original privacy-filtered source values,
source-row reference, normalized values accepted under a named parser version,
and source fingerprints do not change in place.

**Regeneration:** Raw source evidence is not regenerated. Deterministic
normalization may be reproduced from the retained input, but a new parser or
normalization contract must not rewrite an accepted observation silently. PR5
should choose either a versioned derived projection or a new observation
revision linked to its predecessor. In both cases, the accepted earlier evidence
remains addressable.

**Provenance:** Import ID, source-row reference, source-file hash reference,
parser version, exact collection label, copies value, audit scope/completeness
snapshot, and privacy policy/version where applicable.

### Inventory Holding

**Purpose:** Represent current project belief about one physical copy. Until
Libib quantity semantics are proven, one explicitly marked unresolved quantity
group may temporarily stand in for several possible copies.

**Lifecycle:** Durable and mutable only through validated reconciliation or an
explicit user decision. A holding retains its `holding_id` through repeated
observations, metadata corrections, catalog relinking, location changes, and
status changes. It is never regenerated wholesale from the newest export.

**Relationship to observations:** A holding can accumulate many historical
observations. Its current fields are a projection of accepted decisions, not a
copy of the latest row and not the only record of what sources asserted.

**Durability:** `holding_id` is immutable and never recycled. Current believed
fields may change under controlled rules. Superseded or duplicate holding
records remain traceable rather than being physically deleted.

**Regeneration:** Holdings are not regenerated from observations. A current
snapshot may be rebuilt only from a complete, validated decision/event history
once such reconstruction is explicitly supported.

### Inventory Reconciliation Decision

**Purpose:** Record the interpretation that connects immutable observations to
current holdings.

**Lifecycle:** Append-only. Automated proposals, accepted automated outcomes,
manual decisions, reversals, and superseding decisions remain auditable. A
later decision may supersede an earlier one but does not edit or delete it.

**Owns:** Observation, candidate holding(s), outcome code, confidence, evidence
summary, rule version, decision state, timestamps, reviewer where applicable,
and supersession reference.

**Does not own:** Raw source evidence, canonical bibliographic metadata, or the
current holding snapshot itself.

## 3. Current Belief Versus Historical Evidence

The recommended model is deliberately asymmetric:

- Inventory Observation answers **what did this source assert at this time?**
- Inventory Holding answers **what does the project currently believe exists?**
- Reconciliation Decision answers **why did that evidence change or preserve
  the current belief?**

This lets the project improve current belief without destroying contradictory
history. It also prevents a source metadata correction from accidentally
creating a second physical book or rewriting a catalog record.

The tradeoff is additional durable state and referential-integrity work. Every
import must balance to observations and every accepted holding change must trace
to a decision. That cost is justified because the alternative makes changed
rows, partial audits, and manual corrections irreversible or inexplicable.

## 4. Reconciliation Pipeline

The intended flow is:

```text
Libib export or Manual Entry
            |
            v
     Inventory Import
            |
            v
 Immutable Inventory Observations
            |
            v
 Physical-identity candidate generation
            |
            v
 Inventory Reconciliation Decisions
            |
            v
 Current Inventory Holdings
            |
            v
 Catalog candidate generation and matching
            |
            v
 Catalog link, reviewed new catalog item, or unresolved catalog state
```

Physical reconciliation precedes catalog reconciliation. “Is this the same
physical copy?” and “which bibliographic identity describes it?” are different
questions. A corrected ISBN may preserve one holding while changing its catalog
candidate; two physical copies may share one catalog item; and a new physical
holding may remain catalog-unmatched.

Catalog data may be read as supporting candidate evidence, but catalog linkage,
catalog creation, or canonical metadata mutation must not decide physical-copy
identity implicitly. The physical outcome must first be accepted or left
unresolved. Catalog matching then operates against the accepted holding and its
observation evidence.

All stages must be batch-planned before publication. One unresolved observation
may be persisted safely, but it must not cause a guessed holding or catalog
mutation. Accepted observations, reconciliation decisions, and resulting
holding changes should publish under one validated transaction boundary when
PR5 implements the flow.

## 5. Observation Identity and Immutability

`inventory_observation_id` should be project-owned and deterministic within an
accepted import. A tentative identity input is:

- `inventory_import_id`;
- source-row or logical-record reference;
- canonical privacy-filtered row bytes or fingerprint; and
- an occurrence discriminator when identical rows appear in the same file.

Using a row position inside an immutable source file is acceptable for
observation provenance because the ID does not claim continuity across imports.
It remains unacceptable for `holding_id`.

Observations should never change in place. Corrections are new source evidence,
new normalization versions, or new reconciliation decisions. This rule applies
even when a later value is obviously better, such as a valid ISBN replacing a
malformed one. “Better” is an interpretation; the earlier assertion remains
historical fact.

An observation should not carry an authoritative mutable `holding_id` or
`catalog_item_id`. Current links belong in decision/current-link projections so
that reversal and supersession remain possible without rewriting evidence.

## 6. Holding Lifecycle

A holding begins only when evidence or a user decision supports a distinct
physical possession. Its lifecycle is expressed through decisions and current
state, not by replacing its identity.

| Scenario | Required lifecycle behavior |
| --- | --- |
| Observed repeatedly | Add observations and `unchanged`/`confirmed_existing` decisions; retain `holding_id` and refresh verification context only when scope supports it. |
| Not observed in a partial/unknown audit | Add no negative holding conclusion; classify coverage as `not_yet_audited` or `outside_audit_scope`. |
| Not observed in a completed applicable scope | Create a `possible_missing` review outcome; `verified_missing` requires explicit completed-scope policy or confirmation. Never infer disposal. |
| Moved | Preserve `holding_id`; update current believed location only through an accepted location decision with verification context. Preserve the source label on the observation. |
| Corrected metadata | Preserve observation history. If physical identity is accepted, retain `holding_id`; catalog metadata changes remain a separate catalog decision. |
| Changed ISBN | Treat as possible identifier correction, different edition, or different book. Preserve the holding until reviewed; never replace the catalog link automatically. |
| Merged duplicate records | If two holding records represent one physical copy, retain both IDs and mark one superseded by the survivor through a decision. Never merge two proven physical copies. |
| Duplicate physical copies | Keep distinct `holding_id` values even when every bibliographic field matches. Require copy evidence or manual confirmation when the source cannot distinguish them. |
| Removed | Change current status only from explicit evidence or a user decision; retain all observations and the holding record. |
| Donated or sold | Record the explicit disposition and date without deleting the holding or acquisition history. Absence from Libib is insufficient. |
| Unknown | Preserve the last supported state and open review; uncertainty must not create, delete, merge, move, or relink a holding. |

Movement, disposition, duplicate supersession, and catalog relinking may
eventually justify a general holding-event repository. PR5 should implement only
the minimum reconciliation decision history needed for observation-to-holding
interpretation; it should not prematurely build a general event-sourcing system.

## 7. Reconciliation Outcome Vocabulary

PR5 should implement a closed, versioned outcome vocabulary. New cases must map
to an existing conservative outcome or require a schema/rule-version change;
they must not introduce ad hoc strings.

### Accepted physical-identity outcomes

- `exact_holding_match`: Strong identity evidence identifies exactly one
  existing holding under the current rule version.
- `unchanged`: The observation is already represented by the holding and adds
  no accepted current-state change.
- `confirmed_existing`: New evidence confirms an existing holding and may
  refresh verification context.
- `metadata_changed_same_holding`: Non-identifier source metadata changed, but
  reviewed evidence supports the same physical holding. Canonical catalog data
  is untouched.
- `metadata_improvement_proposed`: New source metadata appears more complete or
  valid, but remains a proposal until physical and later catalog interpretation
  are accepted separately.
- `isbn_correction_proposed`: New ISBN evidence may correct an earlier value;
  retain the observation and current holding without relinking automatically.
- `isbn_corrected_same_holding`: Reviewed evidence supports an identifier
  correction while retaining the physical holding. Catalog relinking remains a
  separate outcome.
- `location_update`: The same holding is accepted at a different mapped
  project-owned location. Unmapped labels cannot produce this automatically.
- `new_holding`: Evidence supports one new physical holding without asserting a
  catalog match or acquisition.
- `quantity_group_preserved`: A source quantity remains one unresolved group;
  no speculative copy IDs are allocated.
- `duplicate_holding_superseded`: Reviewed state determines two holding records
  represent one physical copy; one ID is retained and the other remains as a
  superseded historical identity.

### Non-mutating physical-identity outcomes

- `exact_observation_repeat`: The observation evidence is already accepted for
  the same import contract; create no duplicate observation or decision.
- `possible_duplicate`: Evidence may describe a holding already represented,
  but is insufficient for an accepted link.
- `ambiguous_holding_candidates`: More than one holding is plausible.
- `changed_identity_evidence`: Title, creator, ISBN, or other identity-bearing
  evidence changed and continuity is unresolved.
- `different_edition_possible`: Evidence may be another edition rather than a
  correction.
- `conflicting_identifiers`: Valid identifiers or other strong signals disagree.
- `quantity_ambiguous`: Copy/group semantics cannot safely produce individual
  holdings.
- `unresolved_no_candidate`: No holding candidate is strong enough, but evidence
  is insufficient to assert a new holding.
- `requires_manual_review`: A policy-defined human decision is required. This
  is a decision state/reason wrapper, not permission to mutate.

### Audit-coverage outcomes

- `verified_present`: Positive evidence confirms presence within the declared
  audit context.
- `not_yet_audited`: No applicable completed audit covers the item.
- `outside_audit_scope`: The item is outside the declared scope.
- `possible_missing`: A completed applicable scope did not observe the holding;
  review is required.
- `verified_missing`: Explicit completed-scope evidence and reviewed policy or
  manual confirmation support the conclusion.

These outcomes describe coverage/current belief and do not mean sold, donated,
discarded, or removed.

### Subsequent catalog outcomes

Catalog reconciliation uses a separate vocabulary after physical reconciliation:

- `catalog_link_unchanged`;
- `catalog_match_confirmed`;
- `catalog_relink_proposed`;
- `catalog_relink_confirmed`;
- `different_edition_catalog_candidate`;
- `catalog_candidates_ambiguous`;
- `catalog_unmatched`;
- `new_catalog_item_proposed`;
- `new_catalog_item_created`; and
- `catalog_review_required`.

An accepted physical outcome does not imply an accepted catalog outcome. A new
catalog item still requires the strong, unambiguous PR1 contract and must not
fabricate an acquisition.

## 8. Refresh and Audit Semantics

### Monthly or repeated refresh

Each new file creates a new import and immutable observations unless its exact
hash is already accepted. Reconciliation compares new observations with prior
observations and current holdings. It never treats the newest export as a full
replacement unless explicit complete scope says so—and even then it records
absence outcomes rather than deleting state.

### Partial and progressive audits

Positive observations may confirm or propose holdings. Non-observation has no
negative meaning outside an explicitly completed applicable scope. A later
partial import cannot invalidate a holding confirmed by another audit scope.

### Complete audits

Completeness applies only to the caller-declared scope. Holdings believed to
belong inside that scope but not observed may become `possible_missing`.
`verified_missing` remains narrower and requires explicit policy or review.
Completion never implies sold, donated, or removed.

### Renamed collections and folders

Folder registration and source collection labels remain separate from
observation and holding identity. A confirmed folder rename preserves
`folder_id`; a Libib collection rename creates new exact source evidence. Manual
confirmation may relate old and new labels, but no label automatically becomes
`location_id` or changes a holding.

### Location changes

An observation preserves its exact source label. Only a confirmed mapping and
accepted `location_update` decision may change a holding's current
`location_id`. A broad location remains valid; fine shelf discipline is not
required.

## 9. Implemented PR5 Repositories

### `data/inventory_observations.csv` — schema version 1

**Purpose:** Append-preserving row-level evidence for every accepted inventory
import, including unmatched and unresolved rows.

**Identity:** Project-owned `inventory_observation_id`, deterministic within
`inventory_import_id`; never a Libib ID and never a holding identity.

**Implemented field groups:**

- identity and provenance: observation ID, import ID, source-row/logical-record
  reference, raw source reference, observation/schema/parser/privacy versions;
- exact source evidence: collection label, raw title/creators/ISBNs/publisher,
  raw copies, source dates, and allowlisted row values;
- accepted normalized projection: normalized ISBNs, title/creator keys, copies,
  Libib-added date, and source-row fingerprint. Publication date remains only in
  the privacy-safe evidence object in schema version 1 and is therefore not a
  PR6 matching input;
- audit context snapshot: folder registration reference, descriptive scope,
  completeness, and observation/import time; and
- grouping flags: grouped quantity, duplicate occurrence, unsupported or
  ambiguous evidence markers.

The repository contains no mutable current holding or catalog links. Durable raw
evidence uses a fixed privacy allowlist; unknown column names and diagnostic
codes are retained, while unknown values and notes/tags/reviews are not copied.
Accepted normalized values are frozen with `normalization_version`; improved
normalization requires later versioned evidence or projection, never rewriting.

### `data/inventory_reconciliation_decisions.csv` — schema version 1

**Purpose:** Append-only explanation of observation-to-holding interpretation.

**Implemented field groups:** Decision ID, observation ID, candidate/accepted
holding IDs, outcome code, decision status, confidence, evidence/rule version,
scope applicability, proposed current-state changes, actor, decided time,
supersedes decision ID, and notes/reason codes.

Candidate holding IDs and reason codes use deterministic JSON string lists. All
plausible candidates are retained. A later explicit decision may supersede the
one current decision for the same observation; the prior row remains immutable.
Branching supersession and cycles fail closed.

### Existing `data/inventory_holdings.csv` — schema version 2

This remains the current-belief repository. Version 2 adds folder context,
physical-copy versus legacy quantity-group type, latest accepted observation and
decision provenance, and verification scope/completeness. It preserves every
PR3 `holding_id`, catalog/location value, and current field. Unsupported headers
or versions fail closed.

PR3 schema-v1 holdings migrate only when every historical import's `row_count`
equals its persisted holding count. The migration creates deterministic
`pr3_backfill` observations with `legacy_derived` completeness and append-only
`pr3_backfill_existing_holding` decisions. Only persisted comparison keys,
quantity, collection, timestamps, and raw references are used; unavailable
historical row values remain blank. Backfill is atomic and idempotent. An
unbalanced or partially migrated state fails before publication.

## 10. Alternatives Considered

### Mutate holdings on every import

**Advantage:** Few repositories and a simple current-state read.

**Rejected because:** It overwrites historical assertions, makes corrected ISBNs
indistinguishable from replacement books, allows partial audits to erase belief,
and cannot explain why a holding changed. PR3 already demonstrates the failure
mode: a plausible changed row must block publication to avoid a duplicate.

### Regenerate all holdings from the latest export

**Advantage:** Deterministic snapshot construction.

**Rejected because:** Holding IDs and user-maintained state become unstable;
partial audits are mistaken for complete truth; removed rows disappear; and
manual location/disposition decisions are lost.

### Store observations only and derive holdings on every read

**Advantage:** Pure evidence history with no mutable snapshot.

**Rejected because:** Physical identity decisions, dispositions, locations, and
manual confirmations are durable user-owned facts. Recomputing them from source
evidence would either be expensive or silently change belief when rules change.

### Use only a general event-sourced inventory ledger

**Advantage:** Maximum reconstructability.

**Deferred because:** It introduces movement, disposition, correction, and
projection infrastructure before representative reconciliation behavior exists.
Immutable observations plus append-only decisions and a validated current
holding snapshot provide the required auditability with less speculative
machinery.

## 11. PR5 Implemented Boundary

PR5 implements **Durable Inventory Observations and Holding Reconciliation**,
limited to:

- a strict, versioned, privacy-filtered observation repository;
- deterministic observation identity and exact-repeat behavior;
- append-only reconciliation decisions and a closed outcome vocabulary;
- candidate generation between new observations and existing holdings;
- automatic acceptance only for exact, high-certainty existing-holding cases;
- conservative proposals/review outcomes for changed metadata, corrected ISBN,
  different-edition evidence, duplicates, and ambiguous candidates;
- new holding creation only when evidence supports a distinct physical holding;
- preservation of PR3 holding IDs and user/current fields;
- deterministic legacy-derived backfill from persisted PR3 holding evidence,
  with unavailable row content left blank and unbalanced state rejected;
- partial/complete scope-aware non-observation outcomes without disposition;
- atomic validation/publication and source-total balancing; and
- fixture-driven tests for every physical and audit outcome.

PR5 does not implement catalog matching or creation, canonical bibliographic
updates, durable locations or label aliases, reports, workbooks, CLI workflow,
recursive discovery, Library Explorer, or Action Center.

Catalog-to-inventory matching becomes the following implementation PR after
physical reconciliation is stable. Inventory exception views must consume
durable observation and decision outcomes rather than reconstructing them from
mutated holdings. PR6 catalog matching must consume the observation repository's
explicit, versioned normalized fields (including normalized ISBN, title, and
creator evidence); it must not interpret or depend on arbitrary keys in
`raw_evidence_json`.

## 12. Deferred and Unresolved Questions

The entity boundary and PR5 implementation are settled. These questions remain
for later evidence or PR6:

- whether normalized reprocessing uses new observations or a separate versioned
  projection;
- whether candidate volume later justifies a normalized candidate repository;
- whether quantity groups later become a separate entity;
- whether reconciliation decisions are sufficient history or a narrow holding
  event repository is also required; and
- the reviewed policy, if any, that permits `verified_missing` after a complete
  applicable audit.

None of these questions permits destructive mutation or a guessed identity in
the meantime.

## 12A. PR6 Implemented Catalog Reconciliation

PR6 adds schema-v1 append-only
`data/inventory_catalog_reconciliation_decisions.csv`. Catalog reconciliation
accepts only holdings whose latest observation is backed by an accepted current
physical decision. Candidate generation reads explicit normalized ISBN, title,
creator, publisher, copies, diagnostic, and provenance columns; it never reads
arbitrary values from `raw_evidence_json`.

The automatic cascade is: unique valid ISBN-13 (including explicitly detectable
ISBN-10 derivation), then exact normalized title plus creator with exact
publisher corroboration. Title-only and creator-only candidates are always
review-only. For a unique exact ISBN, ordinary subtitle truncation, contributor
list differences, or missing/unknown creator text are not conflicts; automatic
linking is blocked only when both independently available title and creator
evidence strongly disagree. Multiple ISBN/title candidates, conflicting dual
ISBNs, strong title-and-creator conflict, and excluded/merged/invalid status
projections do not change holdings. The historical catalog currently has no status column, so its
rows default to active unless a caller supplies an explicit closed status
projection; the statuses actually evaluated are snapshotted in the decision.

A no-candidate observation may create a catalog item only with a valid ISBN-13
(direct or derived), nonblank title and creator, `copies = 1`, no ISBN conflict,
and an accepted physical holding. The catalog row is initialized from explicit
Libib fields without overwriting existing canonical rows. PR5 did not promote
publication date into a dedicated observation column, so the new catalog row
leaves `publication_year` blank rather than inspecting raw-evidence JSON. The
holding link, new catalog row, and decision publish atomically. No acquisition
or acquisition date is created.

Relinking is never automatic. A different supported catalog candidate produces
`catalog_relink_requires_review` and preserves the current link. A later manual
decision may explicitly supersede the prior decision, update the holding, and
retain both decision rows. A newer accepted physical observation also produces
a new catalog decision that explicitly supersedes the prior observation's
decision; rerunning against the same observation is idempotent. Catalog items
are not merged, deleted, or refreshed.

## 13. Implemented Identity, Outcomes, and Thresholds

Observation identity is UUIDv5 over `inventory_import_id`, the source-row
fingerprint, and a one-based occurrence discriminator for that fingerprint.
`source_row_number` remains provenance only. Reordering rows in a later file
creates new import-scoped observations but does not change holding identity.
Identical rows in one import receive distinct observation IDs and the shared
`indistinguishable_duplicate_rows` outcome; no copy ordinal becomes a holding
identity.

The implemented accepted outcomes are `new_holding_created`,
`existing_holding_confirmed`, `existing_holding_reobserved`,
`holding_evidence_updated`, `quantity_group_confirmed`, and
`pr3_backfill_existing_holding`. Only `new_holding_created`,
`existing_holding_reobserved`, and backfill are produced automatically in PR5;
the other accepted codes are reserved for explicit superseding decisions.

The implemented unresolved outcomes are
`holding_identity_changed_requires_reconciliation`,
`multiple_holding_candidates`, `indistinguishable_duplicate_rows`,
`quantity_requires_review`, `edition_or_identity_ambiguity`,
`insufficient_identity_evidence`, `manual_review_required`, and
`possible_duplicate`. Each observation receives exactly one current terminal
decision, and accepted plus unresolved counts must balance the import row count.

Automatic reobservation requires exactly one fingerprint candidate in the same
registered folder and no other physical candidate. Collection/location text is
not identity. Automatic new-holding creation requires `copies = 1`, no credible
candidate, no ISBN conflict, and either a valid normalized ISBN or normalized
title plus creator. Title alone never suffices. A single non-exact candidate,
cross-folder exact evidence, changed title/creator with inconclusive identifiers,
or multiple candidates is non-mutating. When no strong candidate exists, a same-folder title-only or
creator-only overlap is a review guard, not an accepted match; it prevents an
edited row with lost evidence from silently creating a duplicate holding. The
guard does not apply between two rows that each carry valid, nonconflicting,
different ISBN-13 identities: that identifier difference is strong evidence of
distinct bibliographic items and permits distinct holdings. Exact fingerprint
or ISBN continuity remains eligible, while same-ISBN multiplicity, missing or
inconclusive ISBN evidence, and conflicting identifiers remain review outcomes.

PR5 preserves audit context and provides only a non-mutating absence classifier:
partial or unknown applicable scope returns `not_yet_audited`, outside scope
returns `outside_audit_scope`, and completed applicable scope returns
`possible_missing`. It never generates `verified_missing` or disposition.
Scope-wide absence persistence remains deferred.

## 14. Acceptance Scenarios for the Design

- A repeated unchanged row becomes a new historical observation for a new
  import and confirms the same holding; an exact repeated file creates neither.
- A title edit is retained as new evidence and produces a physical-identity
  decision rather than a duplicate holding.
- A corrected ISBN can retain one holding while opening separate catalog
  relinking review.
- Two identical physical copies retain different holding IDs when copy evidence
  supports them; indistinguishable quantity remains grouped and unresolved.
- A partial audit confirms observed holdings but makes no missing conclusion
  about unobserved holdings.
- A complete applicable audit may create `possible_missing`, not disposal.
- A moved holding retains its ID and changes location only after a confirmed
  mapping/decision.
- A renamed source collection creates new immutable label evidence without
  changing folder, holding, location, or catalog identity automatically.
- A donated or sold holding remains historically present with an explicit
  disposition rather than disappearing.
- Every accepted current-belief change traces to immutable evidence and an
  append-preserving decision.

## 15. PR7 Read-Only Audit Projection

PR7 does not add a reconciliation stage. Its generated presentation model
resolves exactly one current unsuperseded physical decision per observation and
one current unsuperseded catalog decision per holding using explicit
`supersedes_decision_id` chains. Historical rows remain visible in Decision
Detail. A missing predecessor, branch, cycle, cross-entity link, or multiple
current rows is repository corruption and stops artifact generation.

Current unresolved outcomes populate Physical Review and Catalog Review without
new candidate generation or recommendations. Accepted physical and catalog
outcomes populate Reconciled Holdings as a positive control. Audit Coverage
displays durable holding status and scope context; absence from partial or
unknown scope remains neutral, and PR7 never creates `verified_missing`.

Location and acquisition labels in these views are generated review
classifications rather than reconciliation decisions. They never mutate a
holding, create a location or acquisition, or become inputs to later runs.

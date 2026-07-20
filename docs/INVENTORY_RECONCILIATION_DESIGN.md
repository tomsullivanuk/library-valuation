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

## 9. Tentative Repositories

### `data/inventory_observations.csv`

**Purpose:** Append-preserving row-level evidence for every accepted inventory
import, including unmatched and unresolved rows.

**Identity:** Project-owned `inventory_observation_id`, deterministic within
`inventory_import_id`; never a Libib ID and never a holding identity.

**Tentative field groups, not a final schema:**

- identity and provenance: observation ID, import ID, source-row/logical-record
  reference, raw source reference, observation/schema/parser/privacy versions;
- exact source evidence: collection label, raw title/creators/ISBNs/publisher,
  raw copies, source dates, and allowlisted row values;
- accepted normalized projection: normalized ISBNs, title/creator keys,
  publication date, copies, and source-row fingerprint;
- audit context snapshot: folder registration reference, descriptive scope,
  completeness, and observation/import time; and
- grouping flags: grouped quantity, duplicate occurrence, unsupported or
  ambiguous evidence markers.

The repository should not contain mutable current holding or catalog links.

### `data/inventory_reconciliation_decisions.csv` (tentative)

**Purpose:** Append-only explanation of observation-to-holding interpretation.

**Tentative field groups:** Decision ID, observation ID, candidate/accepted
holding IDs, outcome code, decision status, confidence, evidence/rule version,
scope applicability, proposed current-state changes, actor, decided time,
supersedes decision ID, and notes/reason codes.

PR5 should evaluate whether multiple holding candidates require a normalized
candidate repository or a deterministic encoded set. It must not store only the
winner and discard the alternatives that made a case ambiguous.

### Existing `data/inventory_holdings.csv`

This remains the current-belief repository. PR5 may need a versioned migration
to distinguish a normal one-copy holding from an unresolved quantity group and
to store safe supersession/current-verification fields. The migration must
preserve every PR3 `holding_id` and blank catalog/location references. This
design does not authorize that migration in PR4.

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

## 11. PR5 Implementation Boundary

PR5 should implement **Durable Inventory Observations and Holding
Reconciliation**, limited to:

- a strict, versioned, privacy-filtered observation repository;
- deterministic observation identity and exact-repeat behavior;
- append-only reconciliation decisions and a closed outcome vocabulary;
- candidate generation between new observations and existing holdings;
- automatic acceptance only for exact, high-certainty existing-holding cases;
- conservative proposals/review outcomes for changed metadata, corrected ISBN,
  different-edition evidence, duplicates, and ambiguous candidates;
- new holding creation only when evidence supports a distinct physical holding;
- preservation of PR3 holding IDs and user/current fields;
- deterministic backfill of PR3 imports when retained raw input is available,
  with an explicit legacy-evidence marker rather than fabricated row content
  when it is not;
- partial/complete scope-aware non-observation outcomes without disposition;
- atomic validation/publication and source-total balancing; and
- fixture-driven tests for every physical and audit outcome.

PR5 must not implement catalog matching or creation, canonical bibliographic
updates, durable locations or label aliases, reports, workbooks, CLI workflow,
recursive discovery, Library Explorer, or Action Center.

Catalog-to-inventory matching becomes the following implementation PR after
physical reconciliation is stable. Inventory exception views must consume
durable observation and decision outcomes rather than reconstructing them from
mutated holdings.

## 12. Deferred and Unresolved Questions

The architectural entity boundary and ordering are settled. These implementation
details remain deliberately open for PR5 evidence:

- exact observation schema and privacy allowlist;
- occurrence identity for byte-identical rows in one export;
- whether normalized reprocessing uses observation revisions or a separate
  versioned projection;
- candidate storage shape when several holdings are plausible;
- the threshold for automatically accepting `confirmed_existing`;
- how much evidence is sufficient for automatic `new_holding`;
- whether a quantity group belongs in the holding repository or a separate
  unresolved-group entity;
- minimum migration fields needed by the PR3 holding repository;
- exact backfill/compatibility policy for already accepted PR3 imports;
- whether reconciliation decisions are sufficient history or a narrow holding
  event repository is also required; and
- the reviewed policy, if any, that permits `verified_missing` after a complete
  applicable audit.

None of these questions permits destructive mutation or a guessed identity in
the meantime.

## 13. Acceptance Scenarios for the Design

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

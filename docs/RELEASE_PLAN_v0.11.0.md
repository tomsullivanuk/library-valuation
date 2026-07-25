# Library Valuation v0.11.0 Release Plan

## v0.11.0 — Steward Workspace

**Status:** PR1 design, PR2 shared presentation-model implementation, PR3
workspace shell and Explore implementation, and PR4 Recommendations are
complete. PR5 Reports implementation is complete and awaiting review.

## 1. Release Theme

Turn the project's existing catalog, inventory, evidence, and review
capabilities into one understandable Steward experience.

Version 0.11.0 should generate a local, read-only workspace that helps the
Steward explore the library, understand what needs attention, and find useful
reports without first learning the system's internal architecture.

## 2. Governing Direction

This release is governed by:

- [Product Vision](PRODUCT_VISION.md);
- [Roadmap](ROADMAP.md);
- [Architecture](ARCHITECTURE.md); and
- [Steward Workspace Design](STEWARD_WORKSPACE_DESIGN.md).

The Product Vision defines why the product exists. The Roadmap defines the
steward workflow and release direction. The Architecture defines durable system
boundaries. The Steward Workspace Design defines the v0.11.0 presentation
contract and user experience.

## 3. Problem Statement

Through v0.10.0, Library Valuation can maintain a durable catalog and acquisition
history, prioritize research, collect and summarize market evidence, reconcile
Libib observations to physical holdings and catalog items, classify audit
exceptions, and generate several review artifacts.

Those capabilities are exposed through separate commands, files, workbooks,
reports, schemas, and technical terms. A Steward should not need to understand
that structure to answer:

- What is in the library?
- What is known and uncertain about it?
- What deserves attention next?
- Which report should I use?

The release should solve this presentation problem without introducing a new
system of record or hiding the evidence behind its answers.

## 4. User Outcomes

By the end of v0.11.0, the Steward can:

- open one generated workspace locally;
- choose among Explore, Recommendations, and Reports from a task-oriented home
  screen;
- search and filter the catalog and its physical holdings;
- inspect bibliographic, acquisition, inventory, research, and market context
  through progressive disclosure;
- identify existing evidence-backed review tasks and understand why they
  surfaced;
- distinguish current, stale, and unavailable evidence;
- locate appropriate existing reports without browsing project directories;
- reach technical provenance when needed; and
- understand that recommendations are advisory and the workspace is read-only.

## 5. Scope

Version 0.11.0 includes:

- a versioned, generated Steward Presentation Model;
- a deterministic, self-contained static HTML workspace;
- a task-oriented home screen;
- Explore, Recommendations, and Reports experiences;
- stable links among books, holdings, recommendations, evidence, and reports;
- integration with existing strict durable repositories and validated
  projections;
- explicit source availability, freshness, limitation, and snapshot metadata;
- deterministic and privacy-allowlisted rendering;
- graceful degradation for optional evidence;
- clear failure for invalid required durable state;
- a narrow generation workflow;
- fixture-driven, repository-state, rendering, privacy, and end-to-end tests;
- real-state performance and Steward acceptance validation; and
- documentation and release-readiness evidence.

## 6. Explicit Non-Goals

Version 0.11.0 will not:

- change catalog, acquisition, inventory, reconciliation, market-evidence,
  Research Assessment, or collector-review semantics;
- write durable decisions from the browser;
- add catalog, inventory, or disposition editing;
- create new durable recommendation or report repositories;
- implement collection intelligence, collection grouping, or collection-level
  opportunity detection planned for v0.12.0;
- implement new value/effort/disposition strategy logic planned for v0.13.0;
- implement new dealer, family, listing, or marketplace artifacts planned for
  v0.14.0;
- implement final disposition tracking planned for v0.15.0;
- add a database, server, authentication, multitenancy, cloud service, live API,
  or deployment platform;
- add arbitrary recursive report discovery;
- read generated output as canonical state;
- redesign existing workbooks or reports merely for visual consistency;
- replace established CLI workflows; or
- generalize beyond the current Steward use case.

## 7. Architectural Principles

1. Durable repositories and accepted decisions remain authoritative.
2. The presentation model is generated and versioned, not durable state.
3. The static workspace is the first client, not the definition, of the shared
   presentation model.
4. Presentation construction is separate from HTML rendering.
5. Domain components own matching, reconciliation, assessment, evidence
   aggregation, and current-decision resolution.
6. Explore, Recommendations, and Reports consume one snapshot and cannot
   calculate conflicting meanings independently.
7. Required durable state fails closed; missing optional evidence degrades
   explicitly.
8. “Unavailable,” “stale,” “unknown,” “none,” and “zero” remain distinct.
9. Recommendations expose existing evidence-backed next steps and remain
   advisory.
10. Reports come from an explicit registry and prove their relationship to the
    workspace snapshot.
11. Identical validated inputs and arguments produce byte-identical workspace
    output.
12. Only explicit allowlisted information is presented.
13. Stable project identities support cross-view links; technical IDs do not
    lead the user experience.
14. The workspace writes only generated artifacts under `output/`.
15. Future hosted use remains possible, but v0.11.0 introduces no speculative
    service architecture.

## 8. Product Structure

The opening screen should ask:

> What would you like to accomplish today?

The three primary experiences are:

- **Explore:** Find books and inspect catalog, holding, acquisition, inventory,
  research, market, confidence, and provenance context.
- **Recommendations:** Review existing evidence-backed next-step queues without
  confusing generated guidance with steward decisions.
- **Reports:** Find current supported artifacts by purpose and audience rather
  than by filename or pipeline.

The detailed behavior and presentation contract are defined in
[Steward Workspace Design](STEWARD_WORKSPACE_DESIGN.md).

## 9. Proposed PR Sequence

### PR1 — Design and Release Plan

**Purpose:** Settle product boundaries, information architecture, presentation
contract, acceptance tasks, implementation sequence, and release criteria.

**Major deliverables:** This release plan and
`STEWARD_WORKSPACE_DESIGN.md`.

**Exclusions:** Application code, release implementation, schema changes,
prototype artifacts, and CLI behavior.

**Validation:** Documentation links, governing-document consistency, terminology
and contradiction checks, documentation-only scope, and `git diff --check`.

**Exit criteria:** The shared-model boundary, three experiences, non-goals,
acceptance tasks, and PR sequence are explicit enough to begin implementation.

### PR2 — Shared Steward Presentation Model

**Purpose:** Implement one source-neutral, read-only model over existing
validated domain state and projections.

**Major deliverables:** Versioned in-memory contract; snapshot identity;
book, holding, recommendation, report, and summary views; strict source joins;
availability and freshness states; field allowlists; deterministic ordering;
fixture-driven tests.

**Exclusions:** HTML interface, new durable schemas, domain-rule changes,
report redesign, and workflow orchestration.

**Validation:** Exact repository-schema loading, cross-repository integrity,
missing optional evidence, stale/incompatible evidence, stable IDs, deterministic
model bytes, privacy allowlists, and malformed-state failures.

**Exit criteria:** One validated model can serve all three planned experiences
without duplicating matching, reconciliation, or evidence logic.

**Implemented contract:** `valuation/steward_presentation.py` provides immutable
version `steward_presentation_v1` records and deterministic canonical JSON
bytes without rendering or writes. The catalog is required; other durable
subsystems are optional-but-strict; inventory is an all-or-none validated
bundle. Derived market evidence and Research Candidates require explicit paths
and catalog-snapshot provenance. Reports require explicit registration.
Evidence states distinguish current, missing, unavailable, stale, and
incompatible. Historical duplicate Amazon acquisition IDs receive
occurrence-scoped presentation references without changing durable identity.

### PR3 — Workspace Shell and Explore

**Purpose:** Generate the self-contained static client and make the library
understandable from a book-first entry point.

**Major deliverables:** Deterministic HTML packaging; Home and About This Data;
navigation; search; filtering; sorting; book and holding detail; progressive
evidence disclosure; stable local links; accessibility foundation.

**Exclusions:** Recommendation queues, report registry, durable writes, server
runtime, and domain-rule changes.

**Validation:** HTML safety, file-URL operation, deterministic bytes, search and
filter correctness, stable linking, empty/missing states, keyboard navigation,
privacy, and real-catalog size/performance profiling.

**Exit criteria:** The Steward can open the workspace, find a known book, and
understand its catalog and physical context without repository knowledge.

**Implemented contract:** `valuation/steward_workspace.py` renders
`steward_workspace_v1` as deterministic, self-contained HTML bytes from a
`StewardPresentation` alone. Hash-fragment navigation supports Home, Explore,
book and evidence detail, About This Data, and honest PR4/PR5 placeholders.
Explore searches title, creator, ISBN, publisher, catalog ID, holding ID, and
acquisition presentation reference; filters current presentation statuses; and
sorts by title, creator, publication year, or catalog ID. Subject search is not
implemented because `steward_presentation_v1` has no authoritative subject
field; the renderer does not infer one. Results disclose the first 250 matches
while preserving the full match count.

### PR4 — Recommendations

**Purpose:** Present current review conditions and existing recommendations as
explainable steward next-step queues.

**Major deliverables:** Closed queue taxonomy; deterministic ordering; up to
three “Start here” actions; plain-language guidance; reason, confidence,
limitation, and evidence links; integration of inventory exceptions, Research
Candidates, market-review guidance, and steward-owned priority where supported.

**Exclusions:** New disposition strategies, global optimization score, AI
service, durable recommendation state, and decision acceptance.

**Validation:** Queue completeness and exclusivity where required, stable
ordering, unsupported-evidence guards, reason traceability, advisory labeling,
weak-evidence language, and no durable mutation.

**Exit criteria:** The Steward can identify a useful next action and explain why
it surfaced without mistaking it for a final decision.

**Implemented contract:** PR4 projects actionable audit-coverage conditions and
explicit steward priority overrides into the existing in-memory
`RecommendationView` contract. The workspace organizes those records together
with existing physical-review, catalog-review, location, newly-discovered,
market-evidence, and research-candidate guidance into separate queues. Queue
precedence is fixed; within each queue, ordering is confidence, steward-facing
entity label, suggested action, and stable recommendation reference. “Start
here” selects the first item from each of the first three nonempty queues rather
than assigning a global score. Exact duplicate recommendation references are
suppressed. Recommendations remain generated, advisory, read-only, and linked
to their affected entity and supporting evidence.

Unavailable, stale, or incompatible optional evidence is explained through the
workspace source-status contract and cannot generate current market or research
recommendations. PR4 does not invent recommendations from absent optional
subsystems. Rich disposition strategy, effort/value optimization, and
recommendation acceptance remain deferred.

### PR5 — Reports

**Purpose:** Provide a curated, trustworthy index to existing stewardship
artifacts.

**Major deliverables:** Explicit report registry; purpose and audience metadata;
availability, scope, freshness, snapshot compatibility, and limitations;
local open/download links; missing/stale guidance.

**Exclusions:** Arbitrary output-directory discovery, new report products,
artifact redesign, hosted downloads, and durable report repository.

**Validation:** Registry allowlist, path safety, current/stale/unavailable
classification, snapshot compatibility, missing artifacts, deterministic
ordering, and no promotion of arbitrary output to authority.

**Exit criteria:** The Steward can select the appropriate existing report and
understand whether it is current without knowing its filename or producer.

**Implemented contract:** PR5 presents only explicit `RegisteredReport` values
already accepted by the shared model. It groups reports by declared
steward-facing purpose into inventory and audit, catalog and research, market
evidence, steward review, family or external communication, and other
registered reports. Within a group, ordering is status, name, and stable report
key.

A present artifact is `current` only when its registered catalog snapshot
matches and its declared format agrees with both source and public filename
extensions. A mismatched snapshot is `stale`; a missing registered file is
`missing`; and a format/path disagreement is `incompatible`. No registrations
is explained as unavailable report coverage. Current and stale artifacts may
be opened or downloaded through their validated relative public paths; stale
artifacts carry an explicit mismatch warning. Missing, unavailable, and
incompatible entries have no open action.

The implemented `registered_report_v1` contract does not contain a separate
scope field or related book, holding, or recommendation references. PR5 shows
purpose, audience, workflow, generated time, status, limitations, content hash,
and snapshot context, but does not infer scope or entity links. No directory is
scanned, no report is recalculated, and no durable report state is introduced.

### PR6 — Integrated Generation and Steward Acceptance

**Purpose:** Provide one safe generation path and validate the combined
experience with actual project state and the current Steward.

**Major deliverables:** Narrow workspace-generation command; integration with
existing builders; atomic generated-artifact publication; end-to-end tests;
real 3,000-item catalog performance validation; supported-browser validation;
Steward task observations; focused usability and terminology refinements.

**Exclusions:** Durable publication, background refresh, new domain logic,
server infrastructure, and new product scope.

**Validation:** Full suite; deterministic repeat generation; rollback or no
partial artifact on failure; byte-for-byte durable-state non-mutation; privacy;
performance; accessibility; file-URL browser behavior; all Steward acceptance
tasks.

**Exit criteria:** One command generates a trustworthy workspace, the real
Steward can complete the approved tasks, and no source or durable repository is
modified.

### PR7 — Documentation and Release Readiness

**Purpose:** Prepare v0.11.0 for release without adding product behavior.

**Major deliverables:** README and architecture updates; final release plan;
release notes; changelog; recovery and operating guidance; release-readiness
record.

**Exclusions:** Features, domain changes, presentation redesign, and
infrastructure expansion.

**Validation:** Full automated suite; deterministic artifact comparison;
privacy and generated-artifact audit; links; version consistency; contradiction
review; clean release scope.

**Exit criteria:** Documentation matches implemented behavior, acceptance
evidence is recorded, no private or generated data is staged, and the release
is ready to commit, tag, and publish.

## 10. Steward Acceptance Tasks

Release acceptance requires evidence that the current Steward can:

1. Open the generated workspace locally and identify Explore,
   Recommendations, and Reports.
2. Find a known book by title, creator, or ISBN.
3. Determine whether it has a believed physical holding and inspect location or
   verification context.
4. Distinguish absent acquisition history from absent physical inventory.
5. Find a physical, catalog, audit, location, metadata, or evidence issue and
   understand why it requires review.
6. Inspect an existing research or market-evidence recommendation and reach its
   supporting evidence.
7. Distinguish current, stale, and unavailable evidence or reports.
8. Find and open an appropriate existing inventory, collector, or market
   report.
9. Reach detailed provenance without encountering technical detail first.
10. State correctly that the workspace is read-only and recommendations do not
    record decisions.

Acceptance should be based on observed task completion and confusion, not only
on visual approval.

## 11. Release Acceptance Criteria

### Product

- The opening screen asks what the Steward wants to accomplish.
- Explore, Recommendations, and Reports are the primary experiences.
- The workspace uses progressive disclosure and human language.
- The three experiences present consistent facts from one snapshot.
- Existing evidence-backed next steps are useful without claiming unsupported
  strategy or value precision.
- The current Steward completes all acceptance tasks without needing repository
  or pipeline knowledge.

### Data and Architecture

- No durable schema or domain behavior changes merely to support presentation.
- The presentation model loads required repositories through strict validators.
- Broken required state fails closed.
- Missing optional state degrades explicitly and cannot imply negative facts.
- All cross-view links use stable project identities.
- Report currency is established through explicit registry and snapshot rules.
- Generation writes no file beneath `data/`, `input/`, or `cache/`.
- The workspace never imports browser edits or creates steward decisions.

### Determinism and Integrity

- Identical validated input state and arguments produce identical model and HTML
  bytes.
- Stable sorting and tie-breaking govern all views and starting actions.
- Failed generation leaves no partially published workspace.
- Real durable repositories remain byte-for-byte unchanged.

### Privacy and Security

- Presented fields are explicitly allowlisted.
- Private Amazon fields, seller identity, secrets, arbitrary raw evidence,
  local absolute paths, and unreviewed diagnostics are absent.
- Embedded data is safely escaped.
- The workspace makes no runtime network request.
- Only explicit registered local report links are exposed.

### Usability and Accessibility

- The real catalog loads and searches within an accepted, documented performance
  budget established in PR3.
- The supported browser set and `file://` behavior are documented.
- Primary workflows are keyboard accessible.
- Status is not communicated by color alone.
- Common laptop and tablet layouts remain usable.
- Technical terms include contextual explanation.

### Quality and Release

- Fixture-driven and real-state tests cover the presentation contract and all
  three experiences.
- The full existing test suite passes.
- Python compilation, Markdown links, privacy searches, architectural-boundary
  checks, contradiction review, and `git diff --check` pass.
- No generated workspace, private source data, caches, or durable project state
  is committed.
- Release notes accurately describe limitations and deferred work.

## 12. Major Risks and Tradeoffs

### Presentation Drift

Independent views could disagree about counts, status, or recommendations. One
shared snapshot and presentation model is mandatory.

### Stale Generated Evidence

Existing market summaries and reports may not match current durable state.
Snapshot compatibility must be explicit; file presence is insufficient.

### False Recommendation Authority

Polished guidance may appear more certain than its evidence. Every next step
must expose reason, confidence or limitation, and advisory status.

### Static Artifact Size

Embedding the real catalog may produce a large file. Measure before adding a
framework or server. Prefer a simple multi-file fallback only if the approved
performance budget cannot be met safely.

### Read-Only Expectations

Interactive search and filters can imply saved state. The workspace must state
that it does not record decisions and direct the Steward to existing explicit
workflows where relevant.

### Technical Language

Simplifying terminology saves time but can accidentally merge catalog,
acquisition, holding, observation, and recommendation semantics. Progressive
disclosure must preserve those distinctions.

### Scope Expansion

Collection inference, disposition strategy, new publishing outputs, and
disposition recording are attractive adjacent features with explicit later
release homes. They should not enter v0.11.0.

## 13. Deferred Work

The following remain deferred:

- writable steward decisions from a workspace;
- hosted deployment or remote access;
- background or monthly refresh orchestration;
- collection intelligence and proposed collection identities;
- expected-effort and expected-value strategy recommendations;
- dealer, family, marketplace, or institution publishing products;
- final disposition recording;
- richer location management;
- authentication, sharing, and multiple users; and
- generalization beyond evidence from the current family use case.

Deferral does not prohibit future clients from using the shared presentation
concept. It prevents v0.11.0 from designing infrastructure without a demonstrated
stewardship need.

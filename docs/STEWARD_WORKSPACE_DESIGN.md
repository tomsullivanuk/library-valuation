# Steward Workspace Design

## 1. Decision

Library Valuation v0.11.0 should introduce a generated, local-first, read-only
**Steward Workspace** backed by one shared presentation model.

The workspace is the first client of that presentation model. It should be a
deterministic, self-contained HTML artifact that opens locally without a server
or network connection. It presents existing catalog, inventory, market-evidence,
research, and review capabilities through three steward-facing experiences:

- **Explore**
- **Recommendations**
- **Reports**

The release should not add a database, service tier, authentication,
multitenancy, cloud deployment, or new durable recommendation state. Existing
domain repositories and rules remain authoritative. The workspace makes them
understandable; it does not replace or redesign them.

## 2. Product Outcome

The Steward should no longer need to understand separate pipelines, repository
names, reconciliation stages, or generated workbook layouts to answer:

- What is in the library?
- What is known about a particular book or physical copy?
- What needs attention now?
- Why does it need attention?
- Which report is useful for the task at hand?

The workspace should reduce navigation and interpretation effort while
preserving access to detailed evidence. It should optimize
**Return on Stewardship Time**, not maximize the amount of information shown on
the first screen.

## 3. Scope

Version 0.11.0 should:

- generate one local Steward Workspace from validated project state;
- provide a task-oriented home screen;
- provide Explore, Recommendations, and Reports experiences;
- use one shared, source-neutral presentation model across all experiences;
- reuse existing catalog, acquisition, research, collector-review, inventory,
  reconciliation, audit, and market-evidence infrastructure;
- show evidence authority, availability, freshness, confidence, and limitations;
- preserve stable project identities for cross-view links and evidence detail;
- support progressive disclosure from summary to explanation to provenance;
- use explicit field and artifact allowlists for privacy;
- behave deterministically for identical validated inputs; and
- remain usable when optional evidence is unavailable.

## 4. Explicit Non-Goals

Version 0.11.0 should not:

- edit or publish durable catalog, inventory, review, or decision state;
- add a new recommendation or disposition-strategy engine;
- implement collection intelligence planned for v0.12.0;
- implement effort/value strategy recommendations planned for v0.13.0;
- create dealer prospectuses, listing drafts, or other new publishing products
  planned for v0.14.0;
- add final disposition workflows planned for v0.15.0;
- treat generated artifacts as canonical project state;
- scan arbitrary files under `output/` and present them as current reports;
- recalculate catalog matching, inventory reconciliation, market evidence,
  Research Assessments, or audit semantics in presentation code;
- add a hosted deployment, server, database, account model, or synchronization
  service; or
- generalize for hypothetical users before the current Steward experience is
  validated.

## 5. Steward Workflow

The workspace should support the middle of the broader stewardship lifecycle:

```text
Import and durable domain workflows
                 |
                 v
        Generate Steward Workspace
                 |
                 v
     What would you like to accomplish today?
          /              |              \
         v               v               v
      Explore      Recommendations      Reports
         \               |               /
          +------ inspect evidence -----+
                         |
                         v
              Steward decides what to do
```

Import, reconciliation, and publication remain explicit command workflows
outside the workspace. The generated workspace may explain how to invoke an
established workflow, but it must not imply that a browser interaction has
changed durable state.

## 6. First Experience

The opening screen should ask:

> What would you like to accomplish today?

It should offer three primary actions:

1. **Explore the library**
2. **Review what needs attention**
3. **Open reports**

A compact status area may show:

- catalog-item count;
- confirmed or believed physical holdings;
- physical-audit coverage;
- unresolved physical or catalog identity questions;
- location questions;
- market-evidence availability;
- existing steward review state; and
- generation time and important freshness warnings.

The home screen should highlight no more than three useful starting actions.
It should not expose every metric, technical subsystem, or outcome code.

If required state is missing or invalid, generation should fail with a specific
diagnostic. If optional evidence is missing, the workspace should still open and
describe the unavailable capability without guessing.

## 7. Information Architecture

### 7.1 Global Structure

Persistent navigation should contain:

- Home
- Explore
- Recommendations
- Reports
- About This Data

“About This Data” should contain generation metadata, included sources,
freshness, limitations, privacy notes, and links to technical provenance. It
should not compete with the three primary experiences.

Stable URLs or fragments should allow a book, holding, recommendation, or report
to be linked across views. Human-readable labels lead; stable IDs remain
available in evidence detail.

### 7.2 Explore

Explore answers:

> What do we have, and what do we know about it?

The initial view should be book-oriented because that is the Steward's natural
entry point. It should still represent multiple physical holdings explicitly
when present.

Explore should support:

- search by title, creator, ISBN, subject, publisher, and stable ID;
- filters for inventory state, location evidence, acquisition presence,
  research priority, market-evidence state, and review need;
- sorting by title, creator, publication year, research priority, evidence
  confidence, and verification recency where supported; and
- concise result rows that distinguish “unknown” from “none.”

A detail view should disclose information in this order:

1. **Summary:** Bibliographic identity, physical holdings, current location
   belief, and important status.
2. **Steward context:** Why attention may be useful and what remains uncertain.
3. **Evidence:** Catalog, acquisition, inventory, research, and market evidence.
4. **Provenance:** Source observations, reconciliation decisions, timestamps,
   model versions, and stable IDs.

The workspace must not collapse catalog items, acquisitions, observations, and
holdings into one implied fact. It may simplify their language initially, but
the detail view must preserve their distinct meanings.

### 7.3 Recommendations

Recommendations answers:

> What deserves my attention next?

For v0.11.0, a recommendation is an evidence-backed next-step presentation of
an existing review condition or existing generated recommendation. It is not a
new disposition decision.

Initial queues should be limited to supported evidence:

- resolve physical identity;
- resolve catalog identity;
- review audit coverage or possible-missing status;
- map or verify location;
- review newly discovered books;
- investigate metadata or edition ambiguity;
- research missing, weak, conflicting, or stale market evidence;
- review existing Research Candidates; and
- review explicit steward-owned priorities.

Each recommendation should include:

- a plain-language suggested next step;
- the affected book or holding;
- why it surfaced;
- the evidence or condition supporting it;
- confidence, uncertainty, or limitation;
- an effort category only where it can be honestly supported;
- a link to supporting detail; and
- the source rule or current outcome code in technical detail.

Queues should use deterministic, explainable ordering. The release should not
force unlike tasks into one global score. A short “Start here” selection may
choose up to three actions using documented precedence, severity, steward
priority, and stable tie-breaking. It must not claim a mathematically optimized
stewardship plan.

Generated suggestions remain advisory. Existing collector-owned state may
affect presentation where current architecture already permits it, but the
workspace must not overwrite that state.

### 7.4 Reports

Reports answers:

> Which artifact will help with this task?

Reports should use an explicit registry of supported artifacts, not directory
discovery. Each registered report should define:

- stable report key;
- steward-facing name and purpose;
- intended audience;
- artifact type and path;
- producing workflow;
- scope and included sources;
- generated time or snapshot identity;
- freshness status;
- important limitations; and
- availability.

Initial entries may include existing collector, inventory, market-evidence, and
catalog review artifacts. The release need not redesign those artifacts.

A report should appear as current only when it was generated or validated
against the workspace snapshot under an approved rule. An old file's presence
under `output/` is not proof that it belongs to current state. Missing reports
should show a concise explanation and the established generation command where
appropriate.

## 8. Shared Presentation Architecture

The intended flow is:

```text
Durable project state             Validated derived evidence
---------------------             --------------------------
Catalog items                     Research Candidates
Acquisitions                      Market Evidence Summary
Collector Reviews                 Inventory Audit Presentation
Inventory repositories            Registered report metadata
        \                                  /
         +---------- validation ----------+
                        |
                        v
             Steward Presentation Model
                        |
          +-------------+-------------+
          |             |             |
          v             v             v
       Explore    Recommendations   Reports
                        |
                        v
        Deterministic static HTML workspace
```

Presentation construction should be separate from HTML rendering. Domain
components own matching, reconciliation, assessment, evidence aggregation, and
current-decision resolution. The presentation model may join and label their
results, but it must not independently reimplement their rules.

The static client should use embedded data, CSS, and JavaScript without external
CDNs or runtime network requests. The tentative generated path is
`output/steward_workspace.html`. A future hosted client should be able to
consume the same conceptual contract, but v0.11.0 should not design a service
API prematurely.

### 8.1 Source Availability Contract

The minimum required source is a valid `data/catalog_items.csv`. Other
subsystems may be unavailable, but partial or malformed subsystems must never be
accepted silently.

| Source | Availability rule |
| --- | --- |
| Catalog items | Required; missing or invalid state stops generation. |
| Acquisitions | Optional as a complete validated repository; absence means acquisition evidence is unavailable, not that no acquisitions exist. |
| Research Assessments and Collector Reviews | Optional independently; when present, each must pass its existing strict validation. |
| Inventory repositories | Optional only as a subsystem; if any required member of the implemented inventory repository set exists, the complete set and its cross-repository integrity are required. |
| Market Evidence Summary and Research Candidates | Optional validated derived projections supplied explicitly or generated in the same workflow; arbitrary existing output is not loaded. |
| Reports | Optional registered artifacts; presence, freshness, and snapshot compatibility are evaluated separately. |

This contract allows catalog exploration before every subsystem is available
without converting incomplete evidence into negative facts.

## 9. Presentation Contract

The presentation model is a generated, versioned contract, not a durable
repository. Its initial conceptual records should include:

### Workspace Snapshot

- presentation-contract version;
- generation time;
- included durable repository versions and content hashes;
- included derived-projection versions and provenance;
- source availability and freshness;
- warnings and limitations; and
- deterministic snapshot identity.

### Workspace Summary

- compact counts and coverage indicators;
- current review-queue counts;
- optional-evidence availability; and
- up to three explainably selected starting actions.

### Book View

- stable `catalog_item_id`;
- allowlisted bibliographic display fields;
- acquisition summary;
- holding summary;
- research context;
- market-evidence summary;
- current review flags;
- source availability and freshness; and
- links to related holdings, recommendations, and evidence.

### Holding View

- stable `holding_id`;
- linked catalog identity when resolved;
- current believed inventory state;
- current believed location and verification context;
- acquisition presence without fabricated acquisition;
- current physical and catalog reconciliation context; and
- links to supporting observations and decisions.

### Recommendation View

- generated recommendation key;
- queue and deterministic order;
- affected entity type and stable ID;
- suggested next step;
- explanation;
- confidence or limitation;
- reason codes and originating subsystem;
- evidence links; and
- explicit indication that the recommendation is advisory.

Recommendation keys identify generated presentation rows only. They must not be
treated as durable decisions or cross-run business identity.

### Report View

- registered report key;
- name, purpose, audience, and format;
- path or local link;
- availability, scope, freshness, and snapshot compatibility;
- producing workflow; and
- limitations.

Exact serialized fields should be finalized in PR2 from existing repository and
projection evidence. The conceptual boundaries above are settled.

## 10. Contract Rules

The shared presentation model must:

1. Load durable repositories through their strict existing validators.
2. Fail closed on unsupported schemas, broken identities, or invalid
   cross-repository references.
3. Distinguish required durable state from optional derived evidence.
4. Never infer “none,” “missing,” “zero value,” or “no acquisition” from an
   unavailable source.
5. Resolve current append-only decisions through existing domain rules.
6. Preserve stable project IDs and deterministic ordering.
7. Include only explicit allowlisted fields.
8. Exclude arbitrary raw evidence, private Amazon fields, seller identity,
   secrets, local absolute paths, and unreviewed diagnostic payloads.
9. Record source versions, hashes or snapshot references, freshness, and
   limitations sufficient to explain the displayed state.
10. Produce identical model and workspace bytes for identical validated inputs
    and arguments, excluding no undocumented runtime values.
11. Remain read-only and perform no writes under `data/`, `input/`, or `cache/`.
12. Keep presentation labels and ordering separate from domain calculations.

## 11. Missing and Stale Data

The workspace should use three distinct states:

- **Available:** Valid evidence belongs to the current workspace snapshot.
- **Unavailable:** The source or projection was not supplied or does not exist.
- **Stale or incompatible:** Evidence exists but cannot be established as
  current for this snapshot.

These states must not be collapsed. In particular:

- unavailable market evidence is not evidence of no market;
- no acquisition record is not proof that a holding was never acquired;
- absence from a partial audit is not a missing holding;
- an ungenerated report is not an empty report; and
- a stale report should not be labeled current.

Required durable repository failure should stop generation. Optional derived
evidence failure should produce an explicit warning and omit only the affected
capability when safe.

## 12. Determinism and Packaging

Identical validated inputs and generation arguments should produce:

- the same snapshot identity;
- the same presentation records and order;
- the same default starting actions;
- the same embedded data;
- and byte-identical HTML.

The generated workspace should:

- contain no runtime timestamp unless derived deterministically from the
  accepted snapshot or supplied explicitly;
- use stable sorting and tie-breaking;
- avoid third-party runtime assets;
- avoid machine-specific absolute paths;
- escape embedded data safely;
- open through `file://` in supported browsers; and
- remain an ignored generated artifact rather than committed project state.

## 13. Accessibility and Usability

The initial workspace should:

- support keyboard navigation;
- use semantic headings, landmarks, tables, and controls;
- expose visible focus states;
- avoid color-only status communication;
- preserve readable contrast and zoom behavior;
- work at common laptop and tablet widths;
- explain domain terminology in place; and
- keep technical IDs and provenance accessible without making them primary.

The design should prefer browser-native controls and modest client-side
behavior over a framework unless implementation evidence demonstrates that a
framework materially reduces complexity.

## 14. Steward Acceptance Tasks

The release should be tested with the current Steward using realistic state.
The Steward should be able to:

1. Open the workspace locally and understand the three available experiences.
2. Find a known book by title, creator, or ISBN.
3. Determine whether that book has a believed physical holding and where it was
   last believed to be.
4. Distinguish a missing acquisition record from a missing physical book.
5. Identify a current inventory or catalog issue and explain why it needs
   review.
6. Find an existing high-priority research or market-evidence task and inspect
   its supporting evidence.
7. Tell when evidence or a report is unavailable, stale, or current.
8. Find and open the appropriate inventory, collector, or market report.
9. Reach technical provenance from a summary without encountering it first.
10. Understand that workspace actions and recommendations do not save a
    decision or alter durable data.

The target is successful completion without needing to know repository names,
outcome-code definitions, or CLI architecture. Observed confusion should drive
language and hierarchy changes before adding features.

## 15. Assumptions Questioned

### A Workspace Requires a Server

It does not. The current single-Steward, read-only need is served by a generated
local artifact with far less operational burden.

### Interactivity Requires Durable Editing

Search, filters, navigation, and evidence inspection can be interactive without
writing state. Durable decisions require a separate, explicit workflow.

### Recommendations Require a New Engine

They do not for v0.11.0. Existing audit exceptions, Research Candidates, market
review guidance, and steward priorities can support useful next-step queues.

### Every Task Belongs in One Ranked List

Physical identity, metadata, market research, and location review are not
directly comparable. Separate explainable queues avoid false precision.

### Reports Are Whatever Exists Under `output/`

They are not. A generated file becomes a workspace report only through an
explicit registry and freshness rule.

### Market Value Should Lead the Workspace

It should not. Inventory confidence, unresolved identity, evidence quality, and
steward effort may be more important to the next action.

### A Shared Presentation Model Is a New Repository

It is not. It is a deterministic, versioned projection over authoritative state
and validated derived evidence.

## 16. Risks and Tradeoffs

### Static Artifact Versus Server

A static artifact avoids deployment, authentication, and operational state. It
cannot persist browser edits or run background jobs. That is the correct trade
for a read-only, single-Steward release.

### Shared Model Versus Independent Views

One model requires careful joining and versioning but prevents Explore,
Recommendations, and Reports from disagreeing. Independent view logic would be
faster initially and more expensive to reconcile later.

### Existing Evidence Versus New Recommendations

Reusing existing queues limits the apparent intelligence of v0.11.0, but it
avoids presenting unsupported disposition advice. Richer recommendations should
wait for v0.13.0.

### One HTML File Versus Asset Directory

A self-contained file is easy to open and move but may be larger. The real
catalog should be profiled early. A multi-file package should be adopted only
if measured size or performance makes it necessary.

### Usability Versus Technical Precision

Human language must lead, but simplification must not merge catalog, holding,
acquisition, observation, and recommendation semantics. Progressive disclosure
is the resolution.

### Freshness Versus Availability

Strict snapshot compatibility may hide an older useful report. Showing it as
current would be misleading. The workspace may expose it as stale with a clear
warning only under an explicit rule.

## 17. Questions for Implementation Evidence

PR2 should determine:

- the smallest shared record shape that serves all three experiences;
- which existing generated projections can prove snapshot compatibility;
- the measured size and browser performance of the real 3,000-item catalog;
- whether embedded data should be one payload or several embedded sections;
- the minimum supported browser set;
- which report workflows already expose sufficient generation provenance; and
- which steward-facing labels require usability refinement.

These questions may change serialization or packaging details. They must not
weaken the settled read-only, generated-artifact, shared-model, privacy, or
domain-boundary decisions.

## 18. Implemented PR2 Contract

PR2 implements the shared model in `valuation/steward_presentation.py` with
contract version `steward_presentation_v1`. It is an immutable in-memory object
graph with canonical JSON bytes for deterministic testing and future clients;
it writes no files and contains no rendering behavior.

The implemented records are:

- workspace snapshot and source status;
- collection summary;
- book and physical-holding views;
- acquisitions;
- Research Assessments and steward reviews;
- inventory imports and observations;
- physical and catalog reconciliation decisions;
- market-evidence summaries;
- generated advisory recommendation references; and
- explicitly registered reports.

`catalog_items.csv` is required and uses the existing strict catalog adapter.
Acquisitions, Research Assessments, and Collector Reviews are optional, but a
present file must have its exact implemented header and valid catalog
references. Inventory remains optional as a subsystem; if any inventory
repository exists, the complete import, folder, observation, physical-decision,
holding, and catalog-decision bundle must exist and pass the existing strict
repositories and audit-presentation integrity checks.

Market Evidence Summaries and Research Candidates are accepted only through an
explicit `DerivedEvidenceInput`. Exact headers and catalog identities are
validated. Caller-supplied catalog snapshot hashes distinguish `current` from
`stale`; malformed derived input is `incompatible`; absent input is
`unavailable`. Stale or incompatible evidence cannot generate current
recommendations.

Reports are accepted only as explicit `RegisteredReport` values. The model
exposes a safe relative public path, never its source filesystem path, and uses
the catalog snapshot hash to classify a present report as current or stale.
There is no output-directory discovery.

The model uses `current`, `missing`, `unavailable`, `stale`, and `incompatible`
as distinct evidence states. `missing` means a validated current source has no
row for an entity; `unavailable` means the source was not supplied.

Existing Amazon acquisition evidence can contain duplicate
`acquisition_id` values because historical source data lacks a true line-item
identifier. PR2 preserves those IDs and creates deterministic, occurrence-scoped
presentation references such as `acquisition:AMZ-…:1`. These references are
generated navigation identity only; they do not change durable acquisition
semantics.

Privacy is structural. Dataclasses expose only reviewed fields; arbitrary raw
Libib evidence, unknown columns, private Amazon order identifiers, reviewer
identity, local source paths, and unreviewed derived fields cannot enter the
serialized model.

## 19. Implemented PR3 Workspace Contract

PR3 implements `valuation/steward_workspace.py` as a pure renderer for
`steward_presentation_v1`. It produces deterministic
`steward_workspace_v1` HTML bytes with inline styling, behavior, and
script-safe canonical presentation JSON. The artifact uses no external assets,
network access, server runtime, browser persistence, or durable writes.
Hash-fragment routes allow direct `file://` navigation without weakening the
single-file delivery model.

The implemented shell provides:

- a task-oriented Home view and persistent Home, Explore, Recommendations,
  Reports, and About This Data navigation;
- a functional book-first Explore view;
- distinct book, holding, acquisition, assessment, review, market-evidence,
  observation, and reconciliation-decision detail routes;
- progressive Summary, Steward context, Evidence, and Technical provenance
  disclosure;
- explicit source-state messages for unavailable, stale, incomplete, or
  incompatible evidence;
- keyboard focus treatment, a skip link, semantic landmarks, labelled controls,
  live result counts, and non-color status text; and
- visible read-only notices explaining that decisions and filters are not
  saved.

Explore searches the fields actually present in the shared contract: title,
creator, ISBN-10, ISBN-13, publisher, catalog item ID, holding ID, and
acquisition presentation reference. It filters by inventory, acquisition,
market-evidence, and review state, and sorts by title, creator, publication
year, or catalog item ID. The browser displays at most 250 matching rows for
responsive local use while reporting the complete match count.

The approved design listed subject search, but `steward_presentation_v1`
contains no authoritative subject evidence. PR3 therefore does not offer or
simulate subject search. Adding it requires a future, explicit presentation
contract backed by an authoritative or approved-derived source. Likewise,
location, research-priority, confidence, and verification-recency controls
appear only after the shared contract can supply them consistently.

Recommendations and Reports remain honest navigation placeholders in the PR3
contract. Their records are preserved in the embedded shared model; their full
experiences are assigned to PR4 and PR5 respectively.

## 20. Implemented PR4 Recommendations Contract

PR4 presents existing evidence-backed operational guidance without introducing
a recommendation engine or durable recommendation repository. The shared
presentation builder now includes actionable audit-coverage rows and explicit
steward priority overrides alongside its existing inventory-review,
market-evidence, and research-candidate recommendations. It does not turn
unavailable evidence into a recommendation or reproduce the rules that created
the underlying audit, reconciliation, assessment, or market condition.

The workspace uses a closed, presentation-only queue taxonomy:

- resolve physical identity;
- resolve catalog identity;
- review inventory coverage;
- verify locations;
- review newly discovered books;
- review market evidence;
- review research candidates;
- review steward priorities; and
- other supported review conditions, as a forward-compatible fallback.

Only nonempty queues appear. Queue precedence follows the order above. Within a
queue, current records sort by stated confidence, steward-facing entity label,
suggested action, and stable recommendation reference. This is an explainable
display order, not a cross-queue score. “Start here” shows at most one item from
each of the first three nonempty queues.

Every recommendation displays the existing suggested action and explanation,
stated confidence or an explicit “not stated” value, advisory status, source
kind, reason codes, affected entity, supporting evidence links, and generated
recommendation reference. Book, holding, observation, assessment, market,
review, and recommendation routes remain hash-fragment links suitable for the
self-contained `file://` artifact.

Exact duplicate recommendation references are displayed once. Recommendation
references remain deterministic presentation identity only; accepting,
dismissing, annotating, or otherwise persisting a recommendation is outside
v0.11.0.

Stale or incompatible derived evidence remains visible as a source limitation
but cannot generate current market or research guidance. An unavailable
optional subsystem produces neither invented guidance nor a false “nothing
needs attention” conclusion. Rich disposition recommendations—including
selling, donating, retaining, publishing, or dealer outreach—remain deferred to
v0.13.0.

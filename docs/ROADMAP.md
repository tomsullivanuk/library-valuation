# Roadmap

This roadmap connects the durable mission in
[Product Vision](PRODUCT_VISION.md) to future, release-specific plans. It
describes the product outcomes Library Valuation should pursue without
repeating implementation history or prematurely fixing technical designs.

This roadmap is intentionally organized around the steward's workflow rather
than the system's internal architecture. Infrastructure exists to support
stewardship outcomes, not define the product.

Release plans should translate the direction here into bounded deliverables,
acceptance criteria, sequencing, and implementation decisions. Completed work
belongs in release notes, the changelog, and architecture documentation.

## Current Product Baseline

Through v0.11.1, Library Valuation has established:

- a durable catalog and acquisition history derived from Amazon imports;
- research prioritization and collector-owned review state;
- source-aware AbeBooks and eBay asking-price evidence;
- generated catalog, evidence, and review artifacts;
- Libib physical-inventory imports with immutable observations;
- conservative physical and catalog reconciliation;
- explicit handling of unresolved identity and audit exceptions;
- safe preview and explicit publication with deterministic previews, atomic
  rollback, and idempotent repeat processing; and
- an inventory review workbook for collector and steward review;
- a shared, versioned Steward Presentation Model;
- a generated, deterministic, local-first, read-only Steward Workspace centered
  on a book-first Library with details and supporting evidence; and
- atomic generation of inventory summaries, review workbooks, and the
  registered-report workspace.

v0.11.1 adds the completed physical-inventory default, a local background service,
saved Action Items and dispositions, and reviewed estimate history. The generated
HTML remains a read-only fallback.

The detailed record is maintained in [the changelog](../CHANGELOG.md),
[v0.11.0 release notes](RELEASE_NOTES_v0.11.0.md), prior release notes, and the
architecture documents.

## Steward Workflow

The product should support one understandable lifecycle:

```text
Import
  ↓
Catalog
  ↓
Inventory
  ↓
Understand
  ↓
Prioritize
  ↓
Recommend
  ↓
Publish
  ↓
Record Final Disposition
```

- **Import:** Accept evidence from Amazon, Libib, and deliberate manual entry
  while preserving provenance.
- **Catalog:** Maintain stable intellectual identities and bibliographic facts
  without confusing source metadata with canonical state.
- **Inventory:** Establish what physical copies are believed to exist, where
  they are believed to be, and how recently that belief was verified.
- **Understand:** Reveal the character of the library, including subjects,
  authors, editions, duplicates, sets, and coherent collections.
- **Prioritize:** Direct limited steward attention toward the books,
  collections, uncertainties, and opportunities most likely to matter.
- **Recommend:** Explain practical next steps, expected value, expected effort,
  uncertainty, and fallback strategies without making decisions for the
  steward.
- **Publish:** Generate the materials needed for family review, specialist
  outreach, donation, sale preparation, or marketplace handoff.
- **Record Final Disposition:** Preserve the final known outcome of a holding
  without managing the external transaction.

Future releases should materially strengthen one or more of these stages.

## Product Principles

Roadmap proposals should be evaluated by whether they:

- reduce uncertainty for the steward;
- reduce clerical work and avoid low-value effort;
- improve Return on Stewardship Time;
- improve the quality and explainability of decisions;
- preserve evidence, provenance, and reproducibility;
- preserve optionality before irreversible choices;
- use progressive disclosure instead of exposing technical subsystems first;
- keep recommendations advisory and final decisions steward-owned; and
- remain within the product boundaries defined by the Product Vision.

Technical sophistication is valuable only when it improves a stewardship
outcome.

## Delivered Release

### v0.11.0 — Steward Workspace

Create a steward-oriented entry point to the current catalog, inventory,
evidence, and review capabilities.

The delivered release established a generated, read-only workspace over a
shared presentation model. Future workspace evolution is governed by the
[Steward Workspace Design Principles](STEWARD_WORKSPACE_DESIGN.md): books and
stewardship tasks lead, Library presents conclusions, Details presents evidence,
and separate pages or reports must provide value beyond search and filtering.

## Planned Releases

Release titles and boundaries remain working direction until each release plan
is approved.

Future release plans that change the workspace should reference the
[Steward Workspace Design Principles](STEWARD_WORKSPACE_DESIGN.md) rather than
restate or redefine them.

### v0.12.0 — Migration, Library Valuation Review, and Family Access

Approved direction: November 5, 2026. Deliver the following milestones in order,
using v0.11.1 as the stable migration baseline. Each milestone has its own
acceptance gate; partial implementation does not imply the whole release is done.

#### 1. Mac Mini migration

Status: completed November 5, 2026. Final transfer, source write protection,
automatic login and locking, reboot recovery, laptop reconnection, and independent
iCloud snapshot verification passed. See the migration runbook for evidence and
ongoing operational limitations.

Move authoritative operation from the laptop to the Mac Mini. Inventory and
privately back up source data, saved decisions, reviewed estimates, imports,
required market evidence, configuration and reports. Recreate the runtime and
rehearse a restore before final cutover. Verify identities, hashes, application
counts, browsing and disposable write tests. Establish startup, authenticated
administration, independent backup/restore, and reboot recovery. The Mac Mini
must be the only production writer after cutover; the laptop may remain a
development or administration client.

Acceptance: matching durable state and evidence, verified recovery, agreed startup
behavior, documented rollback, and a recorded single-writer cutover. See the
[Mac Mini migration runbook](MAC_MINI_MIGRATION.md).

#### 2. Whole-library valuation review

Status: read-only audit completed November 6, 2026; a private 30-record diagnostic
pilot cohort is prepared. Live source access and revised comparison/publication
rules remain prerequisites. The isolated offline replay is complete: 30 books,
19 with historical candidates, zero verified fresh proposals, no published
changes, and 635 passing tests on both machines. See the
[audit and pilot readiness](VALUATION_REVIEW_AUDIT_20261106.md) and
[offline replay results](VALUATION_OFFLINE_REPLAY_20261106.md).
The eBay-only live pilot is also complete: 30 books, 156 listing details,
26 candidate comparisons, and no estimate changes. See the
[live pilot review](VALUATION_LIVE_PILOT_20261106.md); wider collection and
publication remain subject to review.

Programmatically reassess the physically inventoried library using current
bibliographic identities and available AbeBooks/eBay evidence. Review coverage,
edition and condition matching, duplicate/set ambiguity, outliers, currencies,
source dates and evidence quality. Start with a bounded pilot and inspect its
results before a resumable full-library run. Preserve prior evidence and manually
reviewed estimates; conflicting updates require an explicit policy rather than
silent replacement. Preview proposed ranges and exceptions before publishing.

Acceptance: reproducible coverage and before/after results, source-backed ranges,
no unsupported values, preserved history, and actionable exceptions for checks
that automation cannot resolve. API access, source terms, cost and rate limits
must be verified when the implementation is designed.

#### 3. Friends-and-family access

Expose a separate, private subset of capabilities: browse eligible books, keep a
personal selection list and submit requests for Tom to review. Publish an explicit
allowlist of recipient-facing fields; exclude purchase history, valuation,
private notes, storage locations and operational details. Separate recipient
access from steward administration. Requests do not automatically allocate or
remove physical copies. Choose hosting (potentially Sites) only after verifying
access, durable storage, recovery and operating cost with a synthetic pilot.

Acceptance: private access and isolated lists, durable submissions and revisions,
owner review, backup/restore, and a successful recipient pilot independent of the
laptop. This brings the family-facing subset of the former v0.14 Publishing
scope forward; broader dealer and marketplace publishing remains later work.

#### Deferred collection intelligence

The former v0.12 scope remains a backlog direction rather than a prerequisite:
subject/classification/author/publisher/period/language analysis; scholarly,
thematic and family-significant groupings; duplicate, edition, incomplete-set and
multi-volume detection; and collection-level market, donation, retention and
institutional opportunities. Retain explicit confidence and evidence. Proposed
groupings must not silently replace catalog or holding identity. Use duplicate
and edition checks in milestone 2 where necessary for dependable valuation.

### v0.13.0 — Decision Support

Transform catalog, inventory, collection, and market evidence into practical,
explainable recommendations.

Each recommendation should communicate:

- what action is suggested;
- why it is suggested;
- the evidence and uncertainty behind it;
- expected steward effort;
- expected financial or stewardship value;
- a preferred strategy; and
- reasonable fallback strategies that preserve optionality.

Recommendations may address individual books, groups, or collections. They
remain advisory: the application recommends and the steward decides.

### v0.14.0 — Broader Publishing

Generate stewardship artifacts that prepare work for review or for external
systems.

Possible outputs include:

- dealer or specialist prospectuses;
- family review packets and retention lists;
- collection catalogs and institutional inquiry materials;
- donation and estate reports;
- eBay listing drafts;
- AbeBooks listing drafts;
- marketplace-ready exports; and
- printable or archival reports.

Published materials should be generated from durable evidence and accepted
decisions, identify important caveats, and remain reproducible. Publishing
prepares information for dealers, marketplaces, institutions, and family
members; it does not replace those external systems.

### v0.15.0 — Disposition Tracking

Record the final known outcome of each physical holding.

Initial disposition categories may include:

- retained;
- sold;
- donated;
- gifted;
- recycled or discarded; and
- another explicitly documented removal outcome.

Disposition changes should preserve provenance, dates when known, and relevant
steward notes. The application should know what remains available and what has
left the collection without becoming a marketplace, dealer CRM, payment
processor, shipping system, or estate-accounting system.

## Future Direction

The following directions remain strategically valuable but should be promoted
into planned releases only when evidence and steward need justify them.

### Operational Continuity

- Provide a safe, repeatable refresh workflow for new Amazon and Libib evidence,
  inventory audits, stale market observations, and regenerated steward views.
- Track freshness and provenance so the steward can tell what needs attention
  without rerunning every source indiscriminately.
- Preserve preview, explicit publication, rollback, and idempotent rerun
  guarantees as workflows expand.

### Market Evidence

- Preserve the distinction among asking prices, completed sales, estimates,
  formal appraisals, and realized proceeds.
- Add completed-sale or other market sources only with source-specific
  provenance, matching confidence, capture dates, condition context, and
  explicit limitations.
- Improve edition matching, comparable-quality assessment, shipping treatment,
  and currency handling before using those factors in recommendations.
- Keep AbeBooks and eBay integrations replaceable; the product outcome is
  trustworthy evidence, not dependence on a particular provider.

### Stewardship Intelligence

- Improve durable location mapping and practical audit support without
  requiring fine-grained shelf discipline.
- Support manual discovery and non-Amazon provenance without fabricating
  acquisition history.
- Identify specialist dealers, institutions, archives, or donation channels
  where collection evidence supports outreach.
- Revisit valuation and prioritization models when new real-world outcomes
  provide better evidence than asking-price proxies.

Detailed candidates and deferred implementation tasks belong in
`BACKLOG.md`. A future release plan should select only the smallest coherent
set needed to deliver a demonstrable steward outcome.

## Generalization Strategy

Library Valuation should continue to solve the current family's stewardship
problem well before attempting broad productization.

The architecture may later support other families, executors, trustees,
estates, or professional stewards, but generalization should follow additional
real-world use cases and evidence. New abstractions should earn their place by
solving observed problems rather than anticipated ones.

## Success

Every release should help the steward answer one question more effectively:

> What is the next best use of my time?

## November 2026 workspace iteration

A local loopback service now adds explicit saved dispositions and action decisions
to the generated workspace baseline. The agreed scope and acceptance behavior are
recorded in [the November workspace review](WORKSPACE_REVIEW_20261104.md). Offline
HTML remains read-only; imports and inventory identity corrections continue through
the established evidence-preserving workflows.

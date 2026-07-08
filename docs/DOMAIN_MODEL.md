# Domain Model

## Purpose

Library Valuation is an information system for collectors of scholarly and
personal libraries. Its purpose is to help a collector identify which books are
worth researching, keeping, insuring, selling, donating, gifting, or otherwise
preserving.

The domain model defines the concepts that exist in the system and the
relationships between them. It intentionally avoids implementation details such
as Python modules, command-line entry points, CSV layouts, or directory
structure except where a concrete example clarifies a concept.

Each layer in the system represents a different kind of knowledge with a
different owner, provenance, and lifecycle. The system should make those
differences explicit rather than blending source facts, automated assessments,
collector judgment, market evidence, and final decisions into one flat view.

## Layer Model

Information generally flows from source evidence toward collector decisions.
Later layers may depend on earlier layers, but they should not erase or reshape
the evidence that came before them.

```text
Acquisition
     |
     v
Catalog
     |
     v
Research Signals
     |
     v
Research Assessment
     |
     v
Research Candidates
     |
     v
Collector Review
     |
     v
Observation (future)
     |
     v
Market Evidence (future)
     |
     v
Valuation (future)
     |
     v
Collector Decision (future)
```

The arrows show conceptual dependency, not a requirement that every item pass
through every layer. A collector may review an item before any market evidence
exists. A future valuation may be revised without changing the original
acquisition record. A final decision may depend on family priorities as much as
market value.

## Layers

### Acquisition Layer

Purpose: preserve evidence about how books and book-like objects entered, or
were observed in, the collection.

Primary owner: the source system or the collector, depending on the source.
Amazon order history is source-owned evidence. Future manual intake records are
collector-owned source evidence.

Source of truth: the original import evidence plus normalized acquisition
records derived from it.

Typical lifetime: long-lived historical evidence. Acquisition facts should not
be discarded simply because a book is later sold, donated, or lost.

Determinism: mostly automated and reproducible when derived from source files.
Collector-entered acquisition notes are manually maintained and must be
preserved.

Examples include Amazon order history, manual imports, future barcode scans,
scanner imports, estate inventories, or dealer-provided lists.

### Catalog Layer

Purpose: maintain canonical identities for books and book-like objects and
attach bibliographic facts to those identities.

Primary owner: the system owns canonical catalog identity. Bibliographic facts
come from source evidence and external metadata providers, with future support
for explicit collector corrections.

Source of truth: durable catalog identity plus source and bibliographic
evidence. Generated reports are never the catalog source of truth.

Typical lifetime: long-lived. A catalog item should keep its identity even when
metadata improves or additional acquisitions are linked to it.

Determinism: primarily automated and reproducible, though future explicit
collector corrections or overrides may be manually maintained.

Examples include canonical catalog items, ISBNs, editions, authors, publishers,
subjects, classifications, and bibliographic metadata.

### Research Layer

Purpose: decide which catalog items deserve human attention first and explain
why.

Primary owner: the system owns deterministic research signals and assessments.
The collector owns workflow review state.

Source of truth: catalog and metadata evidence, configuration, deterministic
research signals, generated research assessments, and collector review state.

Typical lifetime: medium-lived. Research signals and assessments may be
recomputed as metadata or configuration improves. Collector review state should
remain durable until the collector changes it.

Determinism: research signals, research assessments, and generated Research
Candidates are automated and reproducible. Collector reviews are manually
maintained and must not be overwritten.

Examples include research signals, explainable research assessments, Research
Candidates, and collector workflow.

### Observation Layer (Future)

Purpose: record what the collector observes about a specific physical copy or
holding.

Primary owner: the collector.

Source of truth: collector-entered observations and supporting evidence such as
photographs.

Typical lifetime: long-lived but revisable. A condition assessment may change
after closer inspection, but prior observations may remain useful as evidence.

Determinism: manually maintained. Automated tools may assist, but they should
not replace collector-owned observations without explicit acceptance.

Examples include physical condition, dust jacket presence, signatures,
inscriptions, first edition verification, photographs, marginalia, provenance
notes, and other collector observations.

### Market Layer (Future)

Purpose: preserve external market evidence relevant to a catalog item or
observed copy.

Primary owner: the source of the market evidence, captured and curated by the
collector or the system.

Source of truth: captured comparable sales, dealer listings, auction records,
source URLs, capture dates, and provenance metadata.

Typical lifetime: time-sensitive. Market evidence can become stale, but should
remain historically useful if its capture date and source are preserved.

Determinism: mixed. Automated collection may be reproducible when source
access, provider rules, and captured responses are preserved. Manual market
research notes are collector-owned.

Examples include comparable sales, dealer listings, auction history, and other
market evidence.

### Valuation Layer (Future)

Purpose: estimate value from catalog facts, collector observations, and market
evidence.

Primary owner: the system owns generated valuation assessments; the collector
owns accepted overrides and notes.

Source of truth: valuation assessments derived from documented evidence,
configuration, and valuation methods, plus any explicit collector overrides.

Typical lifetime: medium-lived and revisable. Valuations should be expected to
age as market evidence changes.

Determinism: generated valuations should be reproducible from evidence and
method. Collector overrides and judgment are manually maintained.

Examples include estimated retail value, dealer value, insurance value,
confidence, supporting evidence, rationale, and valuation history.

### Decision Layer (Future)

Purpose: preserve collector choices about what should happen to an item or
group of items.

Primary owner: the collector.

Source of truth: collector decisions, optionally informed by catalog facts,
research assessments, observations, market evidence, and valuations.

Typical lifetime: long-lived but intentionally revisable. A collector may
change a decision when goals, family context, market evidence, or item
condition changes.

Determinism: manually maintained. The system may recommend or summarize, but
the final decision belongs to the collector.

Examples include keep, sell, donate, insure, gift, estate planning, retain for
family history, or ignore for resale.

## Core Domain Objects

### Acquisition

An Acquisition represents evidence that an item entered the collection or was
observed as part of it. For Amazon, this is usually a purchase line item. For
future sources, it may be a manual intake row, a barcode scan, a donation, or
an estate inventory record.

Owner: source-owned when imported from an external system; collector-owned when
manually entered.

Generated or manual: usually generated from source evidence, with possible
collector-maintained notes.

Durability: should be durable historical evidence.

Relationships: an Acquisition is linked to one or more Catalog Items when the
system can identify what was acquired. It may later support observations,
valuation, and decisions, but it does not by itself prove that the item is
still owned.

### Catalog Item

A Catalog Item is the canonical system identity for a book or book-like object
that the collection may contain. It is the stable anchor used by research,
observation, market, valuation, and decision layers.

Owner: system-owned identity.

Generated or manual: generated and reconciled from acquisition evidence and
bibliographic metadata. Future explicit collector corrections may supplement
it, but should not replace source evidence silently.

Durability: should be durable. Its identity should remain stable even when
metadata improves.

Relationships: a Catalog Item may be linked to many Acquisitions, one or more
sets of Bibliographic Metadata, many Research Signals, Research Assessments,
Research Candidates, Collector Reviews, future Observations, Market
Observations, Valuation Assessments, and Collector Decisions.

### Bibliographic Metadata

Bibliographic Metadata describes a Catalog Item as a publication or edition:
title, authors, publishers, publication date, identifiers, classifications,
subjects, language, format, and related facts.

Owner: source providers and the system. The system selects and normalizes
metadata for catalog use.

Generated or manual: mostly generated from acquisition evidence and external
bibliographic sources. Future manual corrections should be explicit and
preserved separately from provider evidence.

Durability: should be durable as evidence and reproducible where possible.
Selected metadata may change when better evidence is available.

Relationships: Bibliographic Metadata supports Catalog Item identity,
Research Signals, Research Assessments, market matching, valuation, and
collector-facing reports.

### Research Signal

A Research Signal is a deterministic reason that a Catalog Item may deserve
human attention.

Examples include an old publication year, a university press, a specialist
publisher, a scholarly subject area, missing classification data, ambiguous
metadata, multiple acquisitions, or product-title clues suggesting a set,
volume, rare edition, import, or specialized academic work.

Each Research Signal should be explainable on its own. A signal includes a
stable code, a human-readable label, a point value used by later Research
Assessments, the evidence field and value that triggered it, and a short
collector-facing explanation.

Owner: system-owned.

Generated or manual: generated from catalog facts, metadata, acquisitions, and
configuration.

Durability: may be regenerated. The rules and configuration used to generate
signals should be traceable.

Relationships: Research Signals are inputs to Research Assessments and should
also appear as explanations for Research Candidates.

### Research Assessment

A Research Assessment summarizes the system's current judgment about how much
research attention a Catalog Item deserves. It may include a priority band,
a numeric score used for sorting, and the signals that explain the assessment.

Owner: system-owned.

Generated or manual: generated from deterministic Research Signals and
configuration.

Durability: should be durable enough to audit what the system produced, but may
be recomputed when metadata or scoring rules change.

Relationships: a Research Assessment belongs to a Catalog Item, is derived
from Research Signals, and helps generate Research Candidates. It does not
represent market value.

### Research Candidate

A Research Candidate is a collector-facing recommendation that a Catalog Item
should be considered for human review. It is not merely a score. It is the
presentation of the item, its priority, and the reasons it surfaced.

Owner: system-owned as a generated recommendation.

Generated or manual: generated from Research Assessments, Catalog Items,
Acquisitions, Bibliographic Metadata, and Collector Review state.

Durability: generated Research Candidate lists are outputs and should be
reproducible. The underlying evidence and collector review state are durable.

Relationships: a Research Candidate points to a Catalog Item and should include
or reference the Research Assessment and Research Signals that explain it.
Collector Review state may include, exclude, deprioritize, or override how the
candidate appears.

### Collector Review

A Collector Review records the collector's workflow state and lightweight
review notes for a Catalog Item.

Examples include whether the item is new, currently being researched, or
reviewed; whether the collector has set a priority override; and brief notes
about next steps.

Current lightweight fields include workflow state, disposition, priority
override, reviewer, review timestamp, review notes, and created/updated
timestamps.

Owner: collector-owned.

Generated or manual: manually maintained. The system may create an empty
placeholder for a new Catalog Item, but must not overwrite collector-entered
values.

Durability: must be durable.

Relationships: a Collector Review belongs to a Catalog Item and informs
Research Candidate generation. It is distinct from future Collector
Observations and final Collector Decisions.

### Collector Observation (Future)

A Collector Observation records evidence from inspecting a specific physical
copy or holding.

Examples include condition, dust jacket presence, signatures, inscriptions,
first edition verification, photographs, location, and copy-specific notes.

Owner: collector-owned.

Generated or manual: manually maintained, possibly assisted by future tools.

Durability: must be durable.

Relationships: a Collector Observation belongs to a Catalog Item and may also
belong to a specific copy or holding when that concept is modeled. It supports
future Market Observations, Valuation Assessments, and Collector Decisions.

### Market Observation (Future)

A Market Observation records external evidence about how comparable items are
listed, sold, or valued in the market.

Examples include dealer listings, comparable sales, auction results, source
URLs, asking prices, sale prices, capture dates, and condition notes from the
source.

Owner: market source as evidence, captured by the system or collector.

Generated or manual: may be collected automatically, entered manually, or both.

Durability: should be durable as dated evidence, even after it becomes stale.

Relationships: a Market Observation relates to a Catalog Item or observed copy
and provides evidence for future Valuation Assessments.

### Valuation Assessment (Future)

A Valuation Assessment estimates the value of a Catalog Item or observed copy
using catalog facts, collector observations, market observations, and valuation
methods.

Owner: system-owned when generated; collector-owned when explicitly overridden
or accepted with notes.

Generated or manual: primarily generated from evidence and method, with future
support for collector adjustments.

Durability: should be durable and versioned or historical enough to understand
how the valuation changed over time.

Relationships: a Valuation Assessment depends on Market Observations,
Collector Observations, Bibliographic Metadata, and method configuration. It
may inform but should not dictate Collector Decisions.

### Collector Decision (Future)

A Collector Decision records what the collector intends to do with an item or
group of items.

Examples include keep, sell, donate, insure, gift, retain for estate planning,
or ignore for resale.

Owner: collector-owned.

Generated or manual: manually maintained. The system may provide suggestions,
but the decision belongs to the collector.

Durability: must be durable and revisable.

Relationships: a Collector Decision belongs to a Catalog Item, observed copy,
or future collection group. It may be informed by Research Assessments,
Collector Observations, Market Observations, and Valuation Assessments.

## Ownership Model

The most important architectural boundary in Library Valuation is the boundary
between automated, reproducible information and collector-owned judgment.

### Automated And Reproducible

Automated information is produced by the system from source data, external
metadata, caches, configuration, and deterministic rules.

Examples include:

- acquisitions derived from source imports;
- catalog items and matching decisions;
- bibliographic metadata selected from source evidence;
- research signals;
- research assessments;
- Research Candidate lists;
- generated reports and workbooks.

This information should be reproducible wherever practical. If the same source
data, cached provider responses, and configuration are used, the system should
produce the same conceptual results. Automated processing may update generated
state, but it should preserve provenance and avoid silently erasing evidence.

### Collector-Owned

Collector-owned information represents human judgment, inspection, intention,
or contextual knowledge that the system cannot safely regenerate.

Examples include:

- collector reviews;
- future physical observations;
- condition assessments;
- signatures and inscription notes;
- family or provenance notes;
- disposition and insurance decisions;
- explicit overrides.

Collector-owned information must never be overwritten by automated processing.
The system may create blank records, suggest values, or flag conflicts, but it
must not silently replace human-entered data.

This separation is foundational because the project aims to preserve evidence
and reduce manual effort without taking ownership away from the collector.
Generated analysis is useful only if the collector can trust that their own
observations and decisions remain intact across monthly imports and future
scoring improvements.

## Relationship To v0.3.0

Version 0.3.0 focuses almost entirely on the Research Layer.

The intended v0.3.0 concepts are:

- deterministic Research Signals;
- explainable Research Assessments;
- Research Candidates as the collector-facing recommendation artifact;
- durable Collector Review state.

This release should avoid treating the numeric priority score as the product.
The product value is the collector workflow: a clear set of candidates to
review, with transparent reasons for why each item surfaced.

Version 0.3.0 intentionally defers Observation, Market, Valuation, and Decision
capabilities. Those layers require their own evidence models, ownership rules,
and provenance policies. Deferring them keeps the research workflow useful
without prematurely mixing condition, comparable sales, price estimates, and
final disposition decisions into one release.

## Design Principles

- Separate facts from opinions.
- Separate generated data from human-owned data.
- Keep provenance explicit.
- Prefer explainability over opaque scoring.
- Treat generated reports and workbooks as outputs, not source data.
- Preserve reproducibility wherever practical.
- Keep stable identities independent from source row order or output order.
- Let later layers depend on earlier layers without overwriting them.
- Make collector-owned edits explicit and durable.
- Design for incremental evolution rather than premature complexity.
- Defer market valuation until market evidence and valuation provenance are
  modeled directly.

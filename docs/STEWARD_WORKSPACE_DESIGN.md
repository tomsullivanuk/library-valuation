# Steward Workspace Design Principles

## Purpose

This document is the canonical design reference for the Steward Workspace. It
defines how the product should present a personal library and support the work
of its Steward.

The [Product Vision](PRODUCT_VISION.md) explains why Library Valuation exists.
This document explains how that purpose should shape the workspace. Architecture
documents retain system boundaries, release plans define bounded delivery, and
the backlog records deferred work. Those documents should reference these
principles rather than restate them.

These principles apply beyond any single release, interface technology, or
delivery format.

## The Steward's Mental Model

A Steward works with books, physical copies, locations, purchase history,
evidence, and unanswered real-world questions. The Steward should not need to
understand repositories, pipelines, identifiers, matching stages, or internal
workflow states to use the product.

The workspace should help answer:

- What books do I have?
- Which physical copies are present?
- Where are they believed to be?
- How did they enter the library?
- What is known, uncertain, or unavailable?
- Which genuine exceptions need my judgment?

## Design Principles

### 1. Describe the library, not the software

The primary interface should describe books and the Steward's current
understanding of them. Internal concepts should appear only when they are
necessary to explain evidence or resolve an exception.

Prefer “physical copy,” “purchase history,” and “location not confirmed” over
repository names, reconciliation outcomes, and implementation identifiers.

### 2. Library presents conclusions

Library is the primary workspace. It should summarize the best current
understanding of each book and support:

- searching;
- filtering;
- sorting; and
- browsing.

The Steward should be able to use these conclusions without learning how they
were derived. Uncertainty must remain visible, but derivation detail should not
lead the page.

### 3. Details presents evidence

Details explains why the system reached a conclusion. Depending on what is
available, evidence may include:

- physical inventory observations;
- purchase history;
- market observations;
- provenance and source dates;
- confidence and limitations;
- matching or reconciliation detail; and
- stable technical identifiers.

Library is the place for conclusions. Details is the place for evidence.
Progressive disclosure should connect them without collapsing the distinction.

### 4. Books are the primary content

The application exists to work with books. Books should become visible quickly.
Navigation, summaries, introductory copy, dashboards, and controls should use
only the space justified by the Steward's task.

The workspace should feel like a focused productivity application, not a
marketing website or an observability console.

Physical copies remain distinct from cataloged books, but that distinction
should be explained in library terms. Counts must name their entity and expose
important exceptions so apparently related totals can be understood.

### 5. Search and filtering are the primary workflow

Stewards should usually find work by searching, filtering, and sorting the
library. Useful filters naturally create work queues such as:

- books without a confirmed location;
- physical copies not yet linked to a cataloged book;
- possible duplicates;
- books without purchase history; or
- books whose market information is unavailable or outdated.

A separate destination is justified only when it supports a task that cannot
be served clearly through the library view.

### 6. Automate routine stewardship

When evidence is sufficiently strong and the approved domain rules permit it,
the system should perform routine work automatically. Examples include:

- matching reliable identifiers;
- reconciling repeated observations;
- creating confidently identified catalog entries;
- associating purchase records; and
- summarizing market information.

Automation must remain deterministic where required, preserve provenance, and
make its basis inspectable. Human attention should be reserved for genuinely
ambiguous, conflicting, or consequential cases.

### 7. Exceptions describe real-world problems

Exceptions should tell the Steward what is uncertain in the library, not which
software stage is incomplete.

Prefer:

- “Possible duplicate”;
- “Edition could not be determined”;
- “Physical copy is not linked to a cataloged book”;
- “Location has not been confirmed”; or
- “Purchase history is unavailable.”

Avoid leading with:

- “Needs Review”;
- “Reconciliation Pending”;
- “Identity Resolution”; or
- raw outcome and reason codes.

Technical states may remain available in evidence detail for diagnosis and
auditability.

### 8. Reports provide distinct value

A report should exist only when it provides meaningful capability beyond
searching, filtering, sorting, or exporting the current library view.

Good reasons for a report include:

- analysis across a collection;
- a stable review packet;
- a print-oriented artifact;
- communication with family or an external specialist; or
- evidence that requires a purpose-built layout.

Reports should not duplicate ordinary navigation or become a filesystem
browser. Generated files do not become authoritative merely because they exist.

### 9. Preserve provenance

Every imported fact should remain traceable to its source. Steward-entered
information must be distinguishable from imported observations and generated
conclusions.

Future editing must preserve this distinction. A convenient interface must not
silently overwrite source evidence, canonical facts, or prior decisions.

### 10. Use plain language without hiding uncertainty

Plain language should clarify meaning, not manufacture certainty. The interface
must continue to distinguish:

- absent from unavailable;
- unknown from none;
- stale from current;
- a cataloged book from a physical copy; and
- an imported observation from the present conclusion.

When a simple label could be misunderstood, provide a concise explanation and a
path to evidence.

### 11. Keep decisions Steward-owned

The application may automate routine evidence processing and offer advisory
guidance. The Steward retains judgment over ambiguous identity, significance,
strategy, and final disposition.

Future writable experiences should state clearly what will change, preserve an
audit trail, and never imply that viewing, filtering, or opening a report saved
a decision.

## Decision Order

When evaluating a workspace change, ask:

1. Does it help the Steward understand or manage the library?
2. Can the task be completed through Library and Details?
3. Does it reduce routine effort or reserve attention for a real exception?
4. Is the language about the library rather than the implementation?
5. Are entity boundaries, uncertainty, and provenance still honest?
6. Does a new page or report provide capability that the existing workspace
   cannot provide clearly?

If the answer to the first question is no, the change does not belong in the
Steward Workspace.

## Relationship to Implementation

These principles do not prescribe a framework, deployment model, repository, or
screen layout. The current generated, local-first workspace is one
implementation of them.

Release-specific behavior, presentation contracts, validation evidence, and
technical tradeoffs belong in release plans, release notes, readiness records,
tests, and architecture documentation. Future implementations may change while
these principles remain stable.

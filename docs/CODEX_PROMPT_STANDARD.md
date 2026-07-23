# Codex Prompt Standard

## Purpose

Codex prompts should define the problem, desired outcome, governing context,
and safe boundaries. They should leave unresolved design and implementation
choices to Codex.

The goal is not to minimize detail. The goal is to provide the detail that
controls success without prescribing choices that still require investigation.

## Required Prompt Structure

### Context

Explain the current project state and why the work is needed.

Include only information that changes how Codex should approach the task, such
as the repository path, current release or commit, governing documents,
completed prerequisite work, and known constraints.

### Objective

State the outcome to achieve in one clear sentence or short paragraph.

The objective should describe the result, not a list of editing steps.

### Requirements

Define observable capabilities, decisions, artifacts, acceptance scenarios, and
validation needed for the work to be complete.

Requirements should answer “what must be true?” Leave “how should this be
implemented?” open unless the method is already an approved decision.

### Constraints

Define boundaries and non-goals.

Use this section to protect durable architecture, data, privacy, release scope,
authorization boundaries, and unrelated behavior. State explicitly whether
Codex may implement, commit, push, publish, or use private local data.

### Completion Report

Specify the evidence Codex should return so the result can be reviewed.

Request the decisions made, files changed, behavior delivered, validation
results, unresolved issues, and repository status that matter for this task.
Do not turn the report into a second implementation specification.

## Reusable Template

```text
Repository:

<repository path>

Context

<Current state, governing documents, prerequisites, and reason for the work.>

Objective

<The outcome to achieve.>

Requirements

- <Observable requirement or acceptance condition.>
- <Required artifact, behavior, or decision.>
- <Validation needed to demonstrate success.>

Constraints

- <Architectural, privacy, scope, or authorization boundary.>
- <Explicit non-goal.>
- <Whether to commit, push, publish, or leave changes uncommitted.>

Completion Report

Return:

1. <Important result or decision>;
2. <Files created or changed>;
3. <Validation evidence>;
4. <Unresolved issue or next-step recommendation>;
5. git status --short.
```

Remove placeholders and sections that contain no useful information, but retain
all five headings so the prompt remains easy to review.

## Outcome-Oriented Instructions

Prefer:

- “Make the Steward able to distinguish unavailable evidence from evidence of
  absence.”
- “Design a generated, read-only workspace that does not create a new system of
  record.”
- “Preserve stable holding identity when bibliographic evidence is corrected.”
- “Demonstrate that a failed publication leaves durable repositories
  byte-for-byte unchanged.”
- “Recommend the smallest architecture that satisfies the approved user
  outcome.”

Avoid:

- “Create a class named `EvidenceStatusResolver` with these seven methods.”
- “Organize the design document into exactly twelve sections.”
- “Add three CSV columns and a helper module” when the data contract has not
  been decided.
- “Use React, SQLite, and a REST API” when the product need does not establish
  those choices.

An outcome-oriented prompt may still name files, commands, schemas, or
algorithms when those details are established contracts rather than unresolved
design choices.

## Common Anti-Patterns

### Prescribing Document Organization

Do not dictate headings, paragraph order, or table layout merely to make a
design document look complete. Define the questions it must resolve and let
Codex choose the clearest structure.

Prescribe document structure only when it is an approved template, a
compatibility requirement, or necessary for a specific review process.

### Designing Before Investigation

Do not embed an unreviewed schema, class hierarchy, matching threshold, or user
interface in the prompt. Require Codex to inspect existing architecture and
recommend or implement the simplest compatible solution.

### Specifying Activity Instead of Success

“Add a module, update three docs, and write tests” describes activity. Also
state the user-visible or architectural result and the evidence that proves it.

### Repeating Governing Documentation

Reference the Product Vision, Architecture, Data Model, Roadmap, or approved
design instead of copying large portions into each prompt. Include the specific
boundary that is easy to miss.

### Unclear Authorization

Do not leave commit, push, publication, destructive migration, or use of private
data implicit. State the authorized stopping point.

### Mixing Unsettled Design with an Exact Recipe

If Codex is being asked to recommend an approach, do not simultaneously require
a predetermined implementation. State settled decisions separately from open
questions.

### Excessive Procedure

Avoid long command-by-command instructions when standard repository validation
is sufficient. Name exact commands when reproducibility, safety, or release
approval depends on them.

## When Additional Detail Is Appropriate

Be prescriptive when a decision is already approved or compatibility requires
an exact contract. Appropriate details include:

- an approved file allowlist for a commit;
- an exact commit message, tag, or release title;
- an implemented durable schema that must remain compatible;
- closed outcome values or identity rules established by design;
- an approved algorithm or safety threshold;
- required validation commands and expected results;
- privacy restrictions for real local data;
- atomicity, rollback, or migration guarantees; and
- explicit exclusions needed to keep a PR within scope.

Label these as approved constraints or required compatibility behavior. Do not
present an unresolved preference as settled architecture.

When implementation evidence conflicts with an approved design, instruct Codex
to preserve data, stop short of guessing, and report the conflict.

## Prompt Review Checklist

Before assigning work, confirm:

- Context identifies the relevant state and governing documents.
- The Objective describes one coherent outcome.
- Requirements are observable and testable.
- Constraints protect scope, data, privacy, and authorization boundaries.
- The Completion Report requests useful review evidence.
- Unresolved design choices remain open to Codex.
- Prescriptive details correspond to approved decisions or compatibility needs.
- Non-goals are explicit where scope could easily expand.
- The prompt does not duplicate release history or governing documentation.
- Codex can tell whether to stop before commit, commit without pushing, or
  complete an external publication.

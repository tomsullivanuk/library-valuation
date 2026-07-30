# Library Valuation v0.11.0 — Steward Workspace

## Executive Summary

Version 0.11.0 turns the established catalog, inventory, research,
market-evidence, and review capabilities into one generated Steward Workspace.
It helps a Steward find books, understand physical holdings, review
evidence-backed next steps, and open appropriate reports without first learning
the repository's internal architecture.

The workspace remains local-first, deterministic, self-contained, and
read-only. It introduces no server, network service, database, authentication,
cloud infrastructure, browser persistence, or new system of record.

## What Is New

### Shared Steward Presentation Model

A versioned in-memory contract translates authoritative durable state and
approved derived evidence into privacy-allowlisted steward concepts. Catalog
identities, physical holdings, acquisitions, observations, reconciliation
decisions, assessments, market evidence, and reports remain distinct. Required
state fails closed; optional sources degrade explicitly.

### Steward Workspace

The generated HTML workspace provides:

- **Library**, a dense book-first card list with deterministic search, compact
  filters, reversible sorting, complete filtered rendering, and CSV export; and
- **Details**, with linked physical-copy, purchase, market, review, and
  provenance evidence.

Progressive disclosure keeps technical provenance available without making it
the first thing a Steward must understand. The interface identifies itself as
read-only and does not save steward decisions.

Final experience polish replaces internal status and workflow language with
plain descriptions of physical copies, purchase history, market research,
review needs, report readiness, and unavailable information. Technical
identifiers and source details remain available when the Steward asks for them.

Library-card estimated values use nearest-whole-currency-unit,
`ROUND_HALF_UP` presentation semantics: `$1.94` displays as `$2`, and
`$12.49–$15.99` displays as `$12–$16`. Complete ranges repeat the currency
marker on both endpoints, including `$162–$173`, `£71–£82`, and
`CHF 12–CHF 16`.

Estimated-value sorting follows those displayed numeric endpoints. Low to high
prioritizes the displayed lower endpoint; high to low prioritizes the displayed
upper endpoint. High-to-low is intentionally not the exact reverse of
low-to-high because the two directions answer different stewardship questions.

Filtered Library CSV exports provide precise numeric `Estimate Low` and
`Estimate High` intervals, canonical `Currency`, and a separate `Resale Market
Display` matching the rounded card. `Estimate Low` and `Estimate High` preserve
precise numeric evidence; `Resale Market Display` preserves the steward-facing
rounded presentation. The structured columns remain suitable for sorting and
analysis without discarding the convenient human-readable value.

The same export replaces the former combined `Acquired` field with
`Acquisition Source`, `Acquisition Month`, and `Acquisition Count`.
`Acquisition Source` is the source of the latest acquisition, `Acquisition
Month` is that acquisition's month in `YYYY-MM` format, and `Acquisition Count`
is the total acquisition records for the catalog item. Library-card acquisition
summaries remain unchanged.

### Integrated Inventory Workflow

`update-inventory` generates the inventory summary CSV, collector review
workbook, and Steward Workspace as one atomic artifact set. Preview remains the
default. `--publish` remains the sole authorization boundary for durable
publication.

Reports created by the workflow are registered against the same catalog
snapshot. Arbitrary files under `output/` are never discovered or granted
authority merely because they exist.

## Trust and Safety

- Identical source, durable state, and arguments produce byte-identical preview
  summaries, identifiers, repositories, CSV, XLSX, and HTML.
- Publication failure restores durable repositories and prior artifacts.
- Exact repeat publication remains idempotent.
- Current, stale, unavailable, missing, incompatible, unknown, and zero remain
  distinct.
- Stale or incompatible evidence cannot produce current guidance.
- Explicit privacy allowlists exclude private paths and arbitrary raw evidence.
- No acquisition, location, recommendation, or report state is fabricated.

## Release Validation

The untouched 30-row Libib export was validated in preview against copies of
the real durable state:

- 30 source rows and 30 physical holdings;
- 22 existing catalog links;
- 5 proposed Libib-discovered catalog identities;
- 3 unresolved catalog cases;
- 3,014 established market-evidence records: 2,520 estimates, 417 researched
  without a reliable estimate, and 77 not researched;
- 5 proposed Libib-only books also correctly shown as not researched;
- 38 evidence-backed recommendation items;
- 2 current, explicitly registered reports; and
- 0 acquisitions created.

The polished 11,039,504-byte workspace and its companion artifacts were
deterministic:

| Artifact | SHA-256 |
| --- | --- |
| Inventory summary CSV | `5d1c6b5314825e92e75a2f257e41945ec8964c33930f3ccaad6ecdda174ba98c` |
| Review workbook XLSX | `979ca9c7adb69904dec537fd40110567534de31e5365493da2fabcbe24939a6d` |
| Steward Workspace HTML | `7f7537b9653fd51f0ec693dbb00e79f4f0a1949d1e479a3f8b49b59d21280cda` |

Repeated generation was byte-identical, preview left real durable state
unchanged, and injected failures restored every affected repository and
artifact.

## Operating and Recovery Guidance

Run `update-inventory` without `--publish` to review the complete proposed
result safely. Open `output/steward_workspace.html` directly in a supported
local browser.

Use `--publish` only after reviewing the completion summary, recommendation
queues, report context, and unresolved cases. If publication fails, the
workflow restores the prior state. Correct the reported cause and rerun; do not
hand-edit generated output as canonical state.

## Known Limitations and Deferred Work

- Subject search awaits authoritative subject evidence.
- Durable view preferences, disposition editing, and filtered XLSX export await
  an explicit persistence and publication design.
- The workspace does not save decisions or edit catalog, inventory, or evidence.
- Collection Intelligence is planned for v0.12.0.
- Publishing is planned for v0.14.0 and Disposition Tracking for v0.15.0.
- The application does not become a marketplace, CRM, payment, shipping,
  accounting, lending, reading-tracker, or general library-management system.
- Final supported-browser acceptance, including the approved PR6C Library and
  filtered-CSV refinements, passed before release.

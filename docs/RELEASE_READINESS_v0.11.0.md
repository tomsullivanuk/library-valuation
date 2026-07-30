# Library Valuation v0.11.0 Release Readiness

## Decision

**Ready for the final release commit; do not tag or publish from this task.**

Automated validation, real-state preview validation, release documentation, and
supported-browser acceptance are complete. The browser reviews found no
architectural or functional defect. PR6A and PR6C made approved
presentation-only usability refinements, PR6B established the canonical
workspace design principles, and the Steward completed the focused regression
of Library sorting, value display, filtered CSV export, navigation, and
read-only behavior.

The automated browser environment rejects local `file://` navigation by policy.
A temporary server or alternate control surface would not validate the approved
local-file contract, so neither was used as a substitute for the Steward's
manual acceptance.

## Delivered Scope

Version 0.11.0 includes the shared Steward Presentation Model; a book-first
Library and evidence-rich Details views; deterministic local HTML generation; an
explicitly registered report catalog; atomic CSV, XLSX, and HTML generation;
preview-first operation; explicit publication; rollback; idempotent repeats;
and privacy-allowlisted rendering.

It adds no durable recommendation or report repository and changes no catalog,
acquisition, inventory, reconciliation, assessment, or market-evidence
semantics.

## Automated Acceptance

Final validation covers Python compilation; focused and full tests; embedded
JavaScript syntax; Markdown links; privacy and architecture boundaries;
deterministic generation; rollback; and whitespace.

Static browser-facing checks confirm semantic landmarks, a skip link, labelled
controls, keyboard-operable native elements, visible focus styling, unique
element IDs, script-safe serialization, no external assets, and safe registered
report links.

## Real Inventory and Actual-Catalog Validation

The untouched 30-row Libib export was previewed against isolated copies of the
real durable repositories:

| Result | Count |
| --- | ---: |
| Source rows | 30 |
| Physical holdings | 30 |
| Existing catalog links | 22 |
| Proposed catalog identities | 5 |
| Unresolved catalog cases | 3 |
| Recommendation items | 38 |
| Current registered reports | 2 |
| Acquisitions created | 0 |

The 38 recommendations comprise 3 catalog-identity reviews, 30 location
verification tasks, and 5 newly discovered books. The reports are the same-run
inventory summary CSV and collector review workbook.

The polished workspace measured 11,039,504 bytes. End-to-end preview generation
completed in under one second in the validation environment.

## Determinism, Privacy, and Recovery

Two identical fresh previews produced identical summaries, IDs, temporary
repository bytes, and artifact hashes:

| Artifact | SHA-256 |
| --- | --- |
| Inventory summary CSV | `5d1c6b5314825e92e75a2f257e41945ec8964c33930f3ccaad6ecdda174ba98c` |
| Review workbook XLSX | `979ca9c7adb69904dec537fd40110567534de31e5365493da2fabcbe24939a6d` |
| Steward Workspace HTML | `7f7537b9653fd51f0ec693dbb00e79f4f0a1949d1e479a3f8b49b59d21280cda` |

Preview did not change real durable repository hashes. Injected failures
restored affected repositories and prior CSV, XLSX, and HTML artifacts. Exact
repeat publication remains idempotent.

Raw Libib data, generated artifacts, temporary repositories, and real durable
repositories remain outside version control. The workspace exposes only
allowlisted fields and safe public artifact paths.

## Supported-Browser Acceptance

The Steward completed baseline manual browser acceptance against the real
inventory workspace on 2026-07-26. The earlier Home, Explore, Recommendations,
and Reports structure worked as intended, and the review identified the
book-first simplification implemented in PR6C.

The final focused regression confirmed:

Open `output/steward_workspace.html` directly in a supported browser and verify:

1. Library is the default route and books become visible quickly.
2. Library, Import, and Settings are named clearly; unavailable items do not
   imply writable functionality.
3. Library finds a known book by title, author, ISBN, publisher, and stable ID.
4. Acquired, Resale Market, and Location filters and reversible sorting update
   results predictably.
5. Book and holding routes remain distinct and their relationship is clear.
6. The complete filtered card list renders without paging; CSV export provides
   the spreadsheet-oriented workflow.
7. Filtered CSV contains only the visible, privacy-allowlisted book fields.
8. Details exposes supporting evidence and provenance.
9. Read-only messaging is visible; disposition is not editable and no control
   implies a saved decision.
10. Evidence-state language is understandable in applicable acceptance fixtures.
11. Keyboard navigation reaches all controls with a visible focus indicator.
12. The workspace works at common desktop and narrow viewport widths.

The browser-generated filtered CSV was inspected independently and confirmed
the structured acquisition and estimate columns, precise numeric values,
rounded display values, filtering behavior, and valid spreadsheet parsing.

## Documentation and Version Consistency

The Product Vision remains authoritative for purpose. The Roadmap records
v0.11.0 as the delivered workspace baseline. The Architecture and workspace
design describe system boundaries and the implemented contract. The release
plan, checklist, changelog, release notes, README, and backlog agree on
delivered and deferred scope.

No v0.12.0 release plan or new product behavior was introduced.

## Remaining Actions

1. Commit the approved PR6C and release-readiness work.
2. Create the annotated `v0.11.0` tag at that commit.
3. Push `main` and the tag.
4. Publish the GitHub Release from `docs/RELEASE_NOTES_v0.11.0.md`.

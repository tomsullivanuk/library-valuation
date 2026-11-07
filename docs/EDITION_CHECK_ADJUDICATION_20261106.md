# Review of edition and inferred-copy checks

The owner requested a records-only review of the first 32 edition flags and eight
inferred-copy flags from the whole-library run, leaving only questions that require
handling the books. The review covers exactly those 40 flags across **32 books**,
not later batches or the earlier pilot's separate checklist.

## Outcome

| Disposition | Count |
| --- | ---: |
| Edition questions resolved from existing records | 18 |
| Inferred-copy questions resolved at the source-profile level | 2 |
| Duplicate inferred-copy questions merged with a remaining book question | 6 |
| Remaining distinct physical-book tasks | 14 |
| Of those: binding/format or market-variant checks | 13 |
| Of those: recheck an invalid printed identifier | 1 |

The eight inferred-copy flags all overlapped an edition flag on the same book.
The review does not report the six merged flags as six independently verified
copies. One precise question is retained for each unresolved book.

Existing title/copyright-page transcriptions already establish many publisher,
translator, volume, edition and printing profiles. Missing ISBN alone does not
require the owner to transcribe those facts again. Dates are kept in their proper
roles: original copyright, edition introduction, title-page date and explicit
printing statement are not interchangeable. A journal issue uses its recorded
volume/issue/date and ISSN; production identifiers and library control numbers are
not promoted to ISBNs. Modern facsimiles remain distinct from the old works they
reproduce, and separately documented reprints are not merged.

For the two inferred-copy resolutions, documented earlier paperback source profiles
are kept separate from catalog/purchase dates and identifiers. Existing work links
and their confidence remain unchanged. These are source-profile resolutions,
**not verification that the physical copy carries its catalog/purchase ISBN**.
Where a source lists binding alternatives, purchase history cannot choose the
inventoried binding. One market-variant case also requires a copy-specific identifier;
binding alone may not distinguish the variants.

Recorded nine-digit SBN and coded book-number alternatives have leading-zero,
checksum-valid bibliographic equivalents where supported by their preserved text.
They remain unassigned candidates. A checksum does not establish physical identity,
and an invalid identifier is not repaired by changing a digit. The invalid printed
identifier remains a narrowly worded physical task; the available indexed photo
set did not identify an original image that resolves that line.

## Separate from the frozen run

`valuation.edition_check_adjudication` renders authored findings into a private
review HTML, structured adjudication JSON and `physical_checks_only.csv`. It
requires exact cohort coverage, preserved source notes and an explicit outcome for
every book. It checks that identifier alternatives actually appear in those notes,
allows only an explicit leading-zero transformation, and rejects guessed repairs.
All outputs keep actual condition ungraded, copy ISBN unverified and publication
false. No catalog record, work link, purchase history, source note, valuation,
Action Item status or protected batch artifact is changed.

The adjudication is a sidecar to the frozen run. Original batch reports retain
raw flags for reproducibility; the new checklist records which of those flags are
resolved or merged for this exact snapshot. The pinned review modules are not
changed, so the worker can resume on quota reset without code or data drift.
Later batches may generate additional raw flags requiring a separate review.

The private results are on the Mini and copied to the laptop under:

`output/valuation_review_20261106/edition_check_review_v1/results/`

`review.html` shows the 14 remaining tasks first, ordered by current Libib location,
and includes decisions/source notes for all 32 books. Routine physical grading
remains deferred separately. Nothing in this review requires an immediate owner
response; the remaining questions can wait until handling or a copy-specific
estimate. Existing source facts are shown so the owner need not repeat them.

## Verification

Canonical hashes, the frozen worker's code/inputs/completed-report fingerprints,
quota ledger and worker status all matched before and after. The job remains in
its quota wait, with automatic continuation intact. There were zero source requests
and zero estimate changes. Individual findings, book details and images stay private;
only the renderer, synthetic tests and aggregate results are committed to PR #2.

**718 tests pass on laptop and Mini.** Seven new cases cover resolution versus
merging, unassigned identifiers/grades/values, exact scope, candidate normalization,
rejection of guessed/unrecorded identifiers, source-evidence and question requirements,
private unchanged inputs, escaped HTML/CSV and preserved frozen-job boundaries.
Artifact checks confirm all 40 decisions, 32 book sections, 14 distinct physical tasks,
valid downloads and matching input fingerprints.

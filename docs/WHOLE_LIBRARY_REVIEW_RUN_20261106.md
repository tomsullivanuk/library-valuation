# Remaining-library review: bounded automatic continuation

The owner authorized review of the rest of the physically inventoried library,
continuation from batch to batch unless a critical defect is found, unchanged
estimates for review, deferred physical grading, and work in existing PR #2.

## Frozen scope

The authoritative Mini has 2,565 active catalog records. The original 30-book
pilot and the additional 100-book test are excluded from fresh collection. The
remaining **2,435 records** are frozen into **98 batches**: 97 of 25 records and
one of 10. The complete cohort, each batch's catalog/purchase/inventory evidence,
source-page notes, existing estimate endpoints, and a separate condition policy
are fingerprinted privately before collection. No records outside completed
physical inventory are added, and no purchase history is removed.

The source remains eBay US active fixed-price used listings, with ISBN queries
where available and conservative title/author queries otherwise. Each book has at
most ten detail results; each batch retains a 400-request cap and the existing
collector's 30-book hard limit. Missing ISBNs/editions, unknown binding, thin
comparisons, contradictory metadata, special copies, wrong volumes, placeholder
titles and unusual prices remain exceptions. Missing physical grades do not
prevent collection of clearly labelled binding/condition/currency scenarios.
No condition discount or default grade is invented. Shipping is excluded and
asking prices are not expected sale proceeds. There are no new AbeBooks requests.

## Execution and quota boundaries

`valuation.whole_library_review` prepares a finite job and runs it independently
of the laptop or Codex session. A macOS user LaunchAgent on the Mini starts the
job in the existing automatic-login session and restarts abnormal process exits.
The Mini's existing automatic login/locking setup supports restart after reboot;
this job does not change FileVault, login, locking, energy or server settings.

Application quota is queried before each collection batch. A persisted local
ledger decrements **before** every collection request, including OAuth, retries
and attempts that fail or are interrupted. Within a quota window, a higher server
reading cannot replenish the local balance: the smaller balance wins. Collection
requires room for the entire 400-request batch plus a 100-request reserve. Quota
expiry or the reserve stops further requests before dispatch. The job waits for
the reported daily reset plus two minutes, then queries again and continues.
Quota-control calls are recorded separately. This run is expected to span several
quota windows; it is not claimed complete when the background job is started.

The [November 7 quota reconciliation](QUOTA_RECONCILIATION_20261107.md)
documents an explicit one-batch recovery using a tighter worst-case admission
bound, the same conservative ledger, the unchanged hard cap and reserve, and
the original frozen rules. This does not change the normal controller policy
or credit the unexplained larger provider balance.

**Current policy update:** The owner's subsequent authorization now makes fresh
eBay reports authoritative at each batch boundary. The provider-led continuation
controller preserves this original frozen runner and matching rules, enforces
the same 100-request cushion between checks, and can checkpoint partial batches
instead of reserving a full batch. See the active-policy section of the linked
quota reconciliation for the migration receipt, durable reset waits and tests.

Temporary transport/service failures use bounded backoff and saved progress.
Access failures, exhausted per-batch budgets, frozen-code/data/input changes,
checkpoint/report inconsistencies, broken identity/grade/publication invariants,
or repeated unrecoverable failures create a persistent critical-stop receipt and
exit successfully so launchd does not repeatedly restart a defective job.
No confirmation is requested for ordinary batch or quota boundaries.

Production datasets, decisions and the active estimate summary are read-only.
Source-state changes, including concurrent owner edits, stop the frozen run for
review rather than being overwritten or silently incorporated. A code change to
the pinned review modules likewise stops further processing; future fixes require
a deliberate, documented continuation plan rather than silent rule drift.

## Recovery and outputs

The existing collector retains per-book search/detail checkpoints. Completed
books are not re-requested. If a process dies after writing its completion marker
but before materializing its CSV, a completed zero-request rerun repairs derived
collection output. Each report attempt snapshots its own checkpoint and observation
inputs, so a later attempt cannot invalidate an earlier report's fingerprints.
A result receipt is written last and protects the completed collection/report files.
After restart, completion totals are recovered from receipts instead of trusting
a potentially stale progress counter. A job-wide lock prevents concurrent runners.

Every completed batch is reviewed against its frozen existing records and checked
for identity, unassigned actual condition, disabled publication and deferred grading.
The job maintains these private outputs atomically:

- `index.html`: current progress and links to each completed batch report;
- `status.json`: collection/wait/retry/critical/completion state;
- `reviewed_books.json`: combined results, explicitly marked partial until done;
- `review_scenarios.csv`: binding/condition/currency asking-price scenarios;
- `deferred_physical_checks.csv`: edition checks and deferred grading;
- `research_exceptions.csv`: missing, thin, wide or unknown-binding comparisons;
- per-batch raw normalized evidence, immutable review attempts and result receipts;
- quota history/ledger, protected source hashes and critical/completion receipts.

The previous 130 books remain in their earlier private reports; they are not
silently re-fetched or relabelled as newly reviewed. The production Library does
not import the new results. Publication remains a separate owner-reviewed step.

## Mini operation

The private job directory is:

`/Users/wearypops/library-valuation/output/valuation_review_20261106/whole_library_v1`

The LaunchAgent is `local.library-valuation.whole-review`. Its configuration is
maintained by `operations/install_whole_library_review.py`; it contains paths,
not credentials. Credentials remain in the existing private eBay configuration
outside the repository, job output and backup payloads. Logs are under the
existing `~/Library/Logs/LibraryValuation/` directory.

Read the job's `status.json`, `critical_stop.json` if present, and progress page
on the Mini to inspect the latest state. A laptop copy is a timestamped snapshot,
not a live progress display. Normal operation does not require the laptop to stay
awake. On completion or critical stop the finite worker exits; the LaunchAgent
remains registered but will not repeat a completed or stopped run after login.

## Validation

**711 tests pass on laptop and Mini**, including 14 new cases for disjoint remaining
scope, stale quota telemetry, expiry/reserve, automatic batch continuation,
durable quota wait/resume, protected estimates, critical-stop persistence,
completed-report integrity, stale progress recovery, missing derived CSV recovery,
access/network failures, launch configuration, and partial combined outputs with
unassigned grades. The earlier live interruption/recovery rehearsal remains the
source for process-termination evidence. This job's reboot persistence is configured
and relies on the previously verified Mini login/launchd recovery; it is not a new
cold-boot test of this particular multi-day job.

At installation the job entered `collecting` on batch 1. Final coverage and estimate
review are pending completion; subsequent aggregate snapshots belong here or in
follow-up run notes, without publishing individual library data to GitHub.

## Initial live verification

At 2026-11-06 17:15 UTC, batch 1 had completed all 25 records with 164 collection
requests. Twenty-four books retained used-copy context in 67 scenarios; all 25
condition checks were deferred and no estimates changed. Batch 2 had started
without another confirmation. Three sample retained comparisons were checked
against their returned ISBNs, including an unknown-binding listing that remains
flagged. The frozen-code/input checks and completed report/collection fingerprints
passed, and canonical files matched the pre-run hashes. The LaunchAgent continued
after the installation SSH session ended; its error log was empty.

A private laptop progress snapshot was captured at that point under
`output/valuation_review_20261106/whole_library_progress_20261106_1715/`.
It is explicitly labelled a snapshot and includes only completed report folders.
The live Mini job remains authoritative for later progress. The initial 25-record
outcome is not a completion claim or a forecast of remaining-library coverage.

## Verified completion: November 9, 2026

The finite Mini job completed at **08:47:19 UTC / 2:47:19 a.m. Central**.
All **98 batches and 2,435 remaining catalog records** have completed collection
and review receipts. Together with the earlier disjoint 130-record pilots, the
lookup passes cover the 2,565-record active catalog scope. The run recorded
18,003 collection attempts across quota windows; it is not waiting to resume.

Both controller states report complete, and the completion receipt confirms
canonical files unchanged and publication disabled. Original frozen rules,
inputs, completed-output hashes and the provider continuation policy verify.
There is no critical-stop receipt. Completion means the planned lookup/review
pass finished; it does not imply that every record has sufficient comparisons
for a revised estimate.

The final cumulative records-check validation covers all 98 batches: all 162
identification flags arrived and match the authored review, with zero pending
or unreviewed arrived flags. The same **54 distinct physical tasks** remain
deferred, now all associated with completed batches. No additional owner input
is required to complete lookups. Reviewing proposed value ranges and handling
those physical tasks remain separate follow-up work. Current estimates and
purchase history are unchanged; physical grading remains unassigned.

The final validation receipt is retained privately alongside the all-batch
records-review artifacts. Individual results and source evidence remain private.

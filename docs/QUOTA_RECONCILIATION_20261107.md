# Quota reconciliation and bounded recovery — November 7, 2026

The fresh eBay Analytics response at 15:37 UTC still reported 1,510 remaining
Browse calls (3,490 counted against 5,000), versus 470 in our persisted ledger.
This was more than six hours after collection paused. Reporting lag alone is
not an established explanation, and the larger balance has not been credited
to our ledger.

Checkpoint reconciliation for batches 20–44, completed in this quota window,
finds exactly 4,530 recorded attempts: 625 searches, 3,880 item details and 25
additional attempts, consistent with one OAuth request per batch. There is no
evidence of duplicate local debits in these completed checkpoints. Excluding
OAuth would explain only 25 requests of the 1,040-request difference;
even then, 1,015 requests of provider-accounting discrepancy remain unresolved.
Only 47 detail IDs repeat, and all 3,880 details returned materialized evidence;
neither observation explains the gap.
The private investigation receipts preserve the response and per-batch totals.
No historical allowance is refunded, and no unsupported claim about caching,
endpoint exemptions or the provider's reset semantics is used to resume work.

## Recovery boundary

The normal frozen controller requires the full 400-attempt batch cap plus a
100-request reserve before admission. A fresh 25-book batch needs at most 275
normal Browse calls (one search and at most ten details per book). The explicit
`valuation.quota_recovery` command therefore permits one batch when the existing
conservative allowance covers those calls, 25 extra auth/retry attempts, and
the unchanged 100-request reserve: 400 total for a fresh full batch.

The 400-attempt hard collection cap remains unchanged. Every actual attempt,
including retries and OAuth, still debits the same persisted ledger before
network dispatch. Exhausting the extra margin cannot consume the reserve.
The command takes the original controller lock, verifies frozen inputs before
collection and before/after review, and writes a private recovery receipt with
the manifest hash, recovery-code hash, allowance and outcome. Failures during
collection/review persist a critical stop rather than continuing automatically.

This is a one-batch operator recovery, not a silent modification to the frozen
runner or its admission policy. The waiting LaunchAgent is stopped first and
restored after verification. The original manifest, matching rules, batch
inputs and completed results remain unchanged, preserving the all-batch
identification-review binding. Estimates remain unchanged; physical grades
remain unassigned; the recovered evidence is review-only.

## Validation

Synthetic tests cover admission using 470 without a server-balance top-up,
the full 25-book worst-case bound, reserve enforcement, checkpoint-aware
remaining calls, competing-worker exclusion, insufficient allowance, immutable
inputs/current estimates, deferred grading and a persistent stop after failure.
All **731 tests pass on both laptop and Mini**; compilation and whitespace
checks pass.

## Verified live outcome

Batch 45 completed at 15:45 UTC using 187 attempts. The job now has **45 of 98
batches / 1,125 of 2,435 records complete**, with 8,252 recorded collection
attempts across both quota windows. The ledger decreased from 470 to **283**;
the next fresh batch requires 400 including its reserve and was refused before
collection. A new provider response reported 1,330 remaining, but the lower 283
was retained. The provider counter changed by 180 while we recorded 187 more
attempts; the mismatch therefore remains unresolved rather than reclaimed.

Frozen code, manifest, source records, current estimates and all completed
report hashes verified unchanged apart from the newly completed batch and
derived progress files. The original controller is restored to wait until
**November 8, 08:02 UTC / 2:02 a.m. Central**, then continue automatically.
The original 100-request reserve and 400-attempt hard cap remain enforced.

The records-only sidecar validates all 45 completed batches: 77 arrived
identification flags match the pre-reviewed scope exactly, with zero unreviewed
arrivals. The 54 focused physical tasks remain unchanged (29 apply to collected
batches). No physical grading, estimate publication or new owner decision is
required by this recovery. Individual evidence and audit receipts stay private.

## Explicit fresh-balance experiment (subsequent owner authorization)

The owner subsequently authorized using a newly reported eBay balance for
exactly one batch, retaining the 100-request reserve. This is an explicit,
audited change from the conservative recovery above; it does not explain or
silently refund the historical discrepancy.

`--use-fresh-balance` records the prior ledger, fresh provider response,
manifest/code fingerprints and proposed adjustment **before** increasing the
ledger. The shared lock and all frozen-state checks still apply. The existing
400-attempt hard cap, checkpoint recovery and pre-dispatch reserve guard remain
unchanged. A timestamped, atomically persisted private request journal counts
authentication, search and detail dispatches separately, recording safe outcome
categories and timestamps without request URLs, headers, tokens or response
payloads. The report records a second provider sample immediately after review,
compares counts only within the same reset window, and does not top up again.
A failed comparison is reported separately from a completed review batch.

The normal controller is paused for the experiment and remains on its saved
reset wait afterward, even if the larger balance could cover more batches.
Further use of that headroom is a separate decision from this single-batch test.
The additional tests cover explicit adjustment, separate endpoint counts,
no post-batch top-up, invalid/insufficient provider balances, and stopping after
one batch. All **734 tests pass on laptop and Mini**.

### Fresh-balance live result

At 15:54:24 UTC, the fresh provider balance was 1,330; the prior local balance
was 283. The authorized adjustment was recorded before collection. Batch 46
completed at 15:57:22 UTC with 174 dispatched attempts: **25 searches, 148 item
details, one OAuth request**, and no other operations. The private dispatch
journal matches the checkpoint request total; all dispatches returned normally.

| Measure | Before batch | After batch | Decrease |
| --- | ---: | ---: | ---: |
| eBay reported allowance | 1,330 | 1,160 | 170 |
| Adjusted local allowance | 1,330 | 1,156 | 174 |

Both provider samples have the same reset window. The 173 Browse calls differ
from eBay's reported decrease by only three; the additional OAuth debit explains
one more request of the four-request local/provider difference. The readings
are close for this batch, but no exact provider lag/rounding behavior is proven
and the older 1,015-request discrepancy is still unexplained. The comparison
does not justify attributing the historical gap to the local request counter.
The post-batch reading did not increase the local ledger again.

Exactly one batch ran: the job now has **46 of 98 batches / 1,150 of 2,435
records complete**, with 8,426 recorded collection attempts in total. No second
batch started despite sufficient new headroom. The normal LaunchAgent is
restored on the saved November 8, 08:02 UTC reset wait; automatic use of the
extra current-window balance was not enabled by this single-batch experiment.
The 100-request reserve and 400-attempt batch cap remain unchanged.

Frozen data/code/input and completed-output verification passes. The cumulative
identification-review sidecar validates all 46 completed batches, with zero
unreviewed arrived flags and the same 54 deferred physical tasks. Current
estimates, acquisition records, source identities, physical grades and owner
decisions remain unchanged. No critical stop or new owner-input requirement
arose. Only code, synthetic tests and aggregate findings go into the existing PR.

## Active policy: provider-led automatic continuation

The owner subsequently authorized making eBay's counts authoritative with a
100-request cushion. This supersedes the one-batch-only restriction above.
`valuation.provider_quota_controller` now runs the finite job through the same
user LaunchAgent. Before each batch it takes a fresh validated daily Browse
report and replaces the local starting allowance with that provider balance.
The local historical minimum no longer prevents collection. Every dispatch
still decrements a persisted local guard between checks, stopping before the
remaining allowance would fall below 100. Auth calls are conservatively included
in this between-check guard; the next fresh provider report is authoritative.

The controller no longer requires enough quota for a full batch. It can begin
with any usable allowance above 100, checkpoint a partial batch at the cushion,
and wait until the provider reset plus two minutes. A real provider HTTP 429
also checkpoints and waits. The durable wait survives restarts and does not
repeatedly refill allowance from the same report while waiting. After reset,
the same batch resumes with the existing 400-attempt hard cap. Each book still
has at most ten detail results. Critical integrity/access failures stop the job.

The original frozen runner, manifest, inputs and completed evidence are
preserved. An explicit continuation receipt binds the original manifest and
the two new controller/helper code fingerprints, records the prior status and
ledger, and fixes the cushion at 100. Changed continuation code or policy fails
closed; the receipt cannot silently be replaced. The former LaunchAgent plist
and prior progress are archived privately. Independent controller and collection
locks prevent duplicate workers. New installations select the provider-led
entry point when the explicit continuation policy is present.

Tests cover fresh provider balances replacing the local ceiling, automatic
batch-to-batch continuation and completion, partial checkpoints at exactly 100,
durable reset waits, recovery without estimate changes or grading, provider
429 responses, policy tampering/replacement, and startup configuration. The
complete suite passes **740 tests on laptop and Mini**. Revised values remain
review-only; estimates, purchase history and physical grades are unchanged.

Live verification: batch 47 completed with 184 attempts and the worker
automatically started batch 48. The run now has **47 of 98 batches / 1,175
records complete**. The fresh provider balance before batch 47 was 1,150;
the next batch's fresh report was 970, replacing the intervening local 966
instead of retaining it as a ceiling. Both the continuation policy and frozen
review fingerprints verify, with no critical stop. The cumulative records-only
review matches all 47 completed batches with no unreviewed arrived flags and
the same 54 deferred physical tasks. Automatic bounded collection remains active.

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

# Library Valuation v0.9.0 Release Readiness

## Status

**In progress.** PR5 completed the bounded production interruption/resume gate.
The next gate is PR6: the approximately 3,014-book production baseline and its
evidence-quality report. Final observation materialization and reviewer-artifact
regeneration remain later PRs.

## PR5 Bounded Production Resume Validation

On 2026-07-19, the production-only full-library command ran against a
deterministic 20-book limit with three results per book, one-second pacing, two
bounded retries, a five-second initial retry delay, and a 30-second maximum
retry delay. The local environment required the virtual environment's certifi
CA bundle because the default macOS trust path encountered a self-signed
certificate in the chain. A bounded access check with that bundle confirmed
valid production OAuth and Browse access before the validation checkpoint was
started.

The first invocation was interrupted normally with Ctrl-C after seven items
completed. Its checkpoint contained seven observed terminal entries, seven
referenced parts, one `in_progress` entry, and twelve pending entries. The
atomic summary recorded `stop_reason=interrupted`, one token acquisition, zero
token refreshes, seven Browse requests, and no retry, rate-limit, temporary, or
global-stop events. The command exited with safe resume guidance.

The same command and compatibility-critical options then resumed the same
checkpoint without `--restart`. Recovery returned the partless interrupted
item to eligible work. The completed run contained:

- 20 candidates and 20 observed terminal outcomes;
- 60 observation rows in 20 deterministic item parts;
- zero `no_results`, `no_query`, retryable failures, or terminal failures;
- `resume_count=1`, `resumed_items_count=7`, and
  `recovered_parts_count=0`;
- one token acquisition, zero token refreshes, and 13 Browse requests during
  the resumed invocation; and
- zero retry, rate-limit, temporary-failure, or global-stop events.

Across both invocations, exactly 20 Browse requests served the 20 books. No
already completed catalog item was requested again. The interrupted item has
two cumulative attempts because interruption occurred after its in-progress
transition but before a Browse request completed. All 20 part paths were
unique, deterministic, referenced exactly once by the ledger, and accepted by
checkpoint integrity validation.

## Aggregate Evidence Result

All 20 books produced observed listings, for 60 unique observations and 60
unique listing URLs. All searches used ISBN-13. All listings were USD; asking
prices ranged from $4.04 to $196.07, with a median of $35.37. Every listing
title shared at least half of its catalog-title tokens in the same broad
diagnostic used for the prior representative validation. This is a plausibility
check only: match confidence remains `unknown`, and human title, edition, and
condition review remains necessary.

## Privacy and Artifact Controls

All 60 seller fields were blank, and no `match_notes` value referred to a
seller. Manifest, ledger, run summary, and part envelopes contained no token or
expiration fields, credentials, authorization or response headers, raw
responses, or literal configured eBay client values. The validation checkpoint,
the failed TLS preflight checkpoint, and `.env` remain ignored and local. No
generated artifact is release data or durable market history.

## Validation Command

The validation used the documented production command with a 20-book limit:

```bash
SSL_CERT_FILE="$(.venv/bin/python -c 'import certifi; print(certifi.where())')" \
caffeinate -dimsu .venv/bin/python library_pipeline.py \
  collect-full-library-ebay-observations \
  --summary output/full_abebooks_market_evidence_summary.csv \
  --output-dir output/full_library_ebay_resume_validation \
  --checkpoint output/full_library_ebay_resume_validation \
  --limit 20 \
  --delay 1 \
  --max-results-per-book 3 \
  --max-retries 2 \
  --retry-delay 5 \
  --max-retry-delay 30 \
  --confirm-production
```

The resume invocation used the identical command and did not use `--restart`.

## Remaining Release Gates

- Run and document the full approximately 3,014-book production baseline.
- Report coverage, runtime, failures, rate-limit behavior, and evidence quality.
- Deterministically materialize final observation CSV/XLSX artifacts.
- Regenerate and reconcile the multi-source summary, reviewer workbook, and
  HTML report from ignored final artifacts.
- Complete final privacy, credential, test, documentation, and release audits.

The evidence remains supplemental active-listing asking-price evidence, not an
appraisal, fair-market-value estimate, realized-sale estimate, or expected
proceeds. AbeBooks remains the primary source for core market ranges.

# Full-Library Production eBay Baseline — v0.9.0

## Purpose and Scope

On 2026-07-19, Library Valuation completed the v0.9.0 production eBay
active-listing baseline for all 3,014 currently assessed catalog items. The run
validated full-library operation, token reuse, pacing, checkpoint integrity,
duplicate prevention, evidence coverage, and seller-identity suppression.

This is supplemental asking-price evidence. It is not sold/completed evidence,
an appraisal, a fair-market-value estimate, a realized-sale estimate, or an
expected-proceeds estimate. AbeBooks remains the core market-range source.

## Successful Command

```bash
unset EBAY_CLIENT_ID EBAY_CLIENT_SECRET EBAY_MARKETPLACE_ID EBAY_ENVIRONMENT
set -a
source .env
set +a

SSL_CERT_FILE="$(.venv/bin/python -c 'import certifi; print(certifi.where())')" \
caffeinate -dimsu \
  .venv/bin/python library_pipeline.py collect-full-library-ebay-observations \
  --summary output/full_abebooks_market_evidence_summary.csv \
  --output-dir output/full_library_ebay_baseline_v0_9_0 \
  --checkpoint output/full_library_ebay_baseline_v0_9_0 \
  --delay 1 \
  --max-results-per-book 3 \
  --max-retries 2 \
  --retry-delay 5 \
  --max-retry-delay 30 \
  --confirm-production
```

No `--limit` or `--restart` option was used.

## Completion and Runtime

The single uninterrupted invocation completed in 4,930.068 seconds,
approximately 1 hour, 22 minutes, and 10 seconds. Runtime was substantially
shorter than the earlier conservative overnight estimate, but remains dependent
on the local environment, network, source latency, and API behavior; it is not
a completion-time guarantee.

| Outcome | Count |
| --- | ---: |
| Candidates / terminal items | 3,014 |
| Books with observed listings | 2,881 |
| Books with `no_results` | 133 |
| `no_query` | 0 |
| Pending / in progress | 0 / 0 |
| Retryable failures | 0 |
| Terminal source/internal failures | 0 |
| Cumulative attempts | 3,014 |
| Observation parts | 3,014 |
| Canonical observation rows | 8,426 |
| Observed listing rows | 8,293 |
| No-results status rows | 133 |

## Token and Reliability Results

- Token acquisitions: 1
- Token refreshes: 0
- Browse requests: 3,014
- Retry events: 0
- Rate-limit events: 0
- Temporary failures: 0
- Global stops: 0
- Resume count: 0
- Recovered parts: 0
- Resumed items: 0
- Stop reason: blank, indicating normal completion

One application token was reused in memory for the entire run. The one-second
delay remained stable, and no retry or rate-limit intervention was required.
These results demonstrate this run's behavior; they do not guarantee that a
future source or network condition will avoid refreshes, retries, or limits.

## Checkpoint Integrity and Duplicate Prevention

Checkpoint integrity validation passed for all 3,014 parts. Every deterministic
part path was referenced exactly once by the ledger, with zero missing,
orphaned, or duplicate part references. The generated state contained 8,426
unique observation IDs and 8,293 unique listing URLs, with zero duplicates in
either category.

The checkpoint is minimum safe execution state, not durable market history.

## Aggregate Evidence

All 3,014 searches used ISBN-13. The 2,881 observed books produced 8,293 USD
active listings:

- minimum item asking price: $1.09;
- median item asking price: $18.53; and
- maximum item asking price: $999.51.

Shipping is excluded and currency is not converted or pooled into AbeBooks
ranges. The minimum and maximum are asking-price outliers, not valuation
anchors. No recommendation, valuation, or matching rule changes automatically
because of this run.

### Broad title-plausibility diagnostic

Catalog-title token overlap with listing titles found:

- 8,044 listings shared at least half the catalog-title tokens;
- 7,557 shared at least three quarters;
- 7,085 included all catalog-title tokens; and
- 249 fell below half-token overlap.

This is a coarse diagnostic, not automated match confidence. Match confidence
remains `unknown`. The 249 lower-overlap listings require human title, edition,
and condition review, as do price outliers and other listing-specific evidence.

## Privacy Results

All 8,426 seller fields were blank, and no `match_notes` value referenced a
seller. The manifest, ledger, run summary, and part envelopes contained no
configured Client ID or secret, access token, authorization or response header,
expiration metadata, or raw HTTP response. The privacy scan found no sensitive
checkpoint fields.

## Generated-Artifact Policy

The entire checkpoint under `output/full_library_ebay_baseline_v0_9_0/` is
ignored, untracked, local, and non-durable. It must not be committed. Credentials,
tokens, headers, raw responses, observation parts, and later generated
CSV/XLSX/workbook/report artifacts also remain uncommitted.

## Remaining Work Before Release

PR7 deterministically materialized combined eBay observation CSV/XLSX files
from the validated parts, combined them with full AbeBooks observations, built
the complete multi-source summary, regenerated the source-aware workbook and
HTML report, reconciled counts and ranges, and reviewed lower-overlap and price-
outlier behavior. All generated outputs remain ignored and untracked. See
`docs/FULL_LIBRARY_MULTISOURCE_RECONCILIATION_v0.9.0.md` for the completed
reconciliation.

Final release documentation, privacy checks, and artifact audits follow after
that reconciliation. Sold/completed listings, shipping-inclusive pricing,
currency conversion, automatic match-confidence rules, Libib integration, the
Library Explorer, and monthly refresh orchestration remain deferred.

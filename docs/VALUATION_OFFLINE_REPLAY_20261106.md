# Offline 30-book valuation replay

Completed November 6, 2026 on the authoritative Mini, with no live source requests
and no changes to Library estimates, saved decisions, inventory or purchase data.
The protected canonical files and the active market summary matched their
pre-replay hashes. This is an isolated experimental model; the existing summary
model and workspace rendering behavior are unchanged.

## Pilot outcome

| Measure | Result |
| --- | ---: |
| Distinct pilot catalog records | 30 |
| Saved listing observations supplied | 149 |
| Additional source-status rows | 4 |
| Pilot records without raw observations in the supplied baselines | 2 |
| Records with plausible historical candidate asking prices | 19 |
| Historical candidate listings | 52 |
| Historical rows excluded for weak/insufficient matching evidence | 97 |
| Saved listings within the experimental current-date age window | 0 |
| Verified proposals supported by the saved evidence | 0 |
| Changes published | 0 |

Two explicit replay dates were used: July 20, 2026 to inspect historical behavior,
and November 6, 2026 to assess whether those observations could support a current
refresh. Old data is retained as dated context, not promoted by regenerating a
summary with today's date.

The current and historical runs both require further research for all 30 books.
Historical candidate ranges exist for 19; these are provisional asking-price
comparisons, not replacement estimates. Existing Library values remain intact.
The strict rule outcome identifies required data for the live pilot: independently
returned listing ISBN, binding, and comparable condition, plus target binding and
condition. The pilot manifest does not currently supply those target facts and
the legacy observations do not independently record returned ISBNs. Adding more
rows of the same incomplete shape would not establish verification.

## Experimental rules

`valuation/offline_valuation_review.py` is network-free and preview-only. It is not
called by the live workspace or existing market summary pipeline.

- **Age:** require a valid observation date, not in the future and at most 30 days
  before the selected replay date. Source-status rows are distinct from listings.
- **Identity:** normalize ISBN-10/13 and stable listing URLs. Search URLs do not
  count as listing identities. Never treat the target ISBN copied into an
  observation, or a successful ISBN query, as the returned listing ISBN.
- **Matching:** independently returned matching ISBN or strong title/author
  similarity permits a candidate. Verification additionally requires matching
  ISBN and binding. Incompatible ISBNs/bindings are excluded. Digital, signed,
  bundle and obvious lot/set candidates are held for separate review.
- **Condition:** require explicit comparable target/listing condition for a
  verified range. Unknown conditions stay provisional; no discount is invented.
- **Deduplication:** one source/listing identity contributes once. Keep the newest
  eligible dated version, ignore tracking parameters/rank differences, and hold
  conflicting same-time records rather than choosing arbitrarily. An invalid-price
  newest record does not revive a superseded older price.
- **Amounts:** require supported currency and finite positive prices with at most
  two decimal places. Keep currencies and source diagnostics separate.
- **Ranges:** require at least three distinct verified comparable listings in a
  currency and a highest/lowest ratio below 3. Wide spreads require review;
  there is no undisclosed trimming. An unavailable source cannot suppress a usable
  source. Nonoverlapping eligible source ranges require review; they are not
  averaged. Otherwise prefer the source with more verified comparables, with an
  explicit deterministic tie-break, rather than pooling the sources.
- **Ownership:** a saved manual review protects the range against automatic
  replacement. All outputs are unpublishable previews even when the rules produce
  a proposed range. There is no publication endpoint or production file write.

The 30-day, three-comparable and spread-ratio choices are experimental pilot
parameters, not validated universal valuation rules. Exact condition matching is
intentionally conservative in this first version. Future changes should explicitly
state their assumptions, retain candidate/verified distinctions, and be checked
against reviewed cases rather than tuned simply to increase coverage.

## Tests and verification

30 new tests cover good verified comparables, duplicate/tracking URLs, stale and
future dates, latest-version selection, conflicting duplicate prices, weak and
wrong-edition matches, missing edition/condition facts, unsupported and mixed
currencies, nonfinite/nonpositive/overprecision prices, special copies, source
outages/disagreements, manual-review protection, deterministic input-order handling,
unchanged input files, private outputs, and refusal to overwrite a prior replay or
write output into a canonical data repository.

Full suite: **635 passed on laptop and Mini**. Existing market-summary semantics
remain unchanged. The private HTML report was opened and checked in a browser;
the temporary verification server was stopped afterward.

## Artifacts and reproduction

Private results are retained on the Mini and copied to the laptop under
`output/valuation_review_20261106/offline_replay_v1_final/`:

- `review.html`: saved ranges, current/historical diagnostics and per-book next steps;
- `comparison.csv`: saved values beside legacy replay values and new diagnostics;
- `replay.json`: policy, per-source ranges, per-listing decisions/reasons and input hashes;
- `verification.json`: protected-state hashes, model hash and replay totals.

The pilot and these artifacts remain ignored and are not published to GitHub.
On a copy of the evidence, choose a new output directory for each run:

```bash
.venv/bin/python -m valuation.offline_valuation_review \
  --pilot output/valuation_review_20261106/pilot_candidates.csv \
  --observations output/full_abebooks_market_observations.csv \
                 output/full_ebay_market_observations.csv \
  --as-of 2026-11-06 --historical-as-of 2026-07-20 \
  --output-dir output/valuation_review_20261106/offline_replay_new
```

The model deliberately has no live-request, publication, credential, or networking
options. Interrupted replay can be rerun into a new directory; identical inputs,
paths, policy and dates produce identical report contents. This does not establish
live collector resume or publication rollback, which remain separate pilot gates.

## Next pilot gate

1. Review the private comparison and expected outcomes before adjusting thresholds.
2. Enrich target binding/condition from authoritative existing records where
   available, retaining unknowns rather than inferring physical checks.
3. Establish permitted source access and destination eBay credentials. Design the
   live adapter to preserve independently returned ISBN/binding/condition, listing
   identity, actual observation time and source outcomes.
4. Run a bounded live pilot only after request budgets, source policy, matching
   and expected outcome checks are ready. Show candidate ranges under explicit
   assumptions where verified comparisons remain unavailable; do not silently
   publish them. Publication preview, manual-edit conflict checks and rollback
   still require separate implementation and disposable-state tests.

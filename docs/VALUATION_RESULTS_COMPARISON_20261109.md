# Valuation results compared with current estimates — November 9, 2026

All 2,565 physically inventoried catalog records are represented: the completed
2,435-record run plus the earlier 130-record pilots. The comparison uses the
authoritative Mini workspace's current estimate fields, including manual review
overrides, rather than assuming old cohort snapshots are still the baseline.
Current estimates, purchase history, decisions and actual condition grades are
unchanged. No fresh market requests or estimate publication occurred.

## Findings

| Record-level result | Catalog records |
| --- | ---: |
| All stronger scenarios above the current range | 335 |
| All stronger scenarios below the current range | 23 |
| Direction depends on condition or binding | 65 |
| All comparable stronger scenarios overlap the current range | 391 |
| Stronger scenarios, but no usable current estimate to compare | 383 |
| Only limited or uncertain scenarios | 1,050 |
| No retained used-price scenario | 318 |
| **Total** | **2,565** |

There are 7,046 conditional scenarios across 2,247 records. Of these, 1,698
scenarios across 1,197 records meet the stricter support screen below. The other
1,368 records need stronger market comparisons or have no retained scenario.
Absence of a retained scenario is not a claim that no market listing exists.

Among 814 records with at least one stronger scenario comparable to a usable
current range, **567** meet the large-change review threshold: 309 above-range,
10 below-range, 46 condition/binding-dependent and 202 overlapping-range cases.
An overlap alone does not rule out a large endpoint change. These are review
flags, not recommended replacements or evidence that the market changed by
that amount. The existing baseline can include older AbeBooks observations;
the new scenarios use bounded eBay active-listing samples.

## Comparison rules and attention priorities

Each condition, listing binding and currency remains separate. No representative
grade, midpoint or aggregate replacement library value is selected. Values are
per-copy asking prices excluding shipping, not sale proceeds.

A stronger conditional scenario requires at least three distinct retained
offers, matching independently returned ISBNs, source-record edition support,
known listing binding, observations no more than 30 days old, and a price
spread strictly below threefold. Three listings do not establish three
independent sellers or represent the complete market. Listing binding is not
treated as physical verification of the owner's copy.

The provisional attention threshold is an absolute change of at least 50% at
either endpoint, or USD 25 at either endpoint for USD comparisons. Calculations
use unrounded values and only same-currency usable current ranges. These are
triage thresholds, not value-approval rules. The highest dollar endpoint
differences are surfaced first; thin scenarios do not drive large-change flags.

Start with the 567 large-change records, checking the condition/binding-specific
offers and held evidence. Next consider the 383 records with stronger scenarios
but no usable current estimate. Additional market research, including another
approved source when available, is needed for the limited/no-scenario groups.
Keep actual grading deferred until the books are handled.

## Preserved checks and coverage limits

The 54 focused physical tasks from the whole-batch records adjudication are
carried forward exactly. Fifteen earlier pilot books have identification checks
in their existing reports; these are flagged separately for records
reconciliation before adding any new owner tasks. None of the 2,565 records is
assigned a physical condition grade or a new Action Item status.

The 2,565 records account for 2,723 linked copies. Four inventory entries still
need identification and are outside these catalog-record comparisons; the
completed inventory total remains 2,727 physical books. Four original pilot
records without a retained candidate-review report are explicitly included in
the no-scenario group rather than silently dropped.

The earliest 26-book candidate report grouped by condition/currency without a
binding field. The comparison validates those pooled bounds against retained
offers, then separates them by reported listing binding. This adds eight
scenario rows, producing 7,046 rather than 7,038; no original source report is
modified. The retained holds remain excluded: 166 metadata conflicts, 60
listing-identity holds, 375 target-edition holds, 30 high-outlier holds and 13
above-new-context holds. These counts are listings, not additional owner tasks.

## Private review artifact and reproducibility

`valuation.valuation_comparison` produces a separate read-only comparison using
the existing private-report format. The final artifact is retained on the Mini
and laptop under `output/valuation_review_20261106/results_comparison_20261109_v4/`.
Earlier build attempts are preserved. The report offers record search, category
and attention filters, condition-specific ranges, listing links, existing
physical questions, CSV downloads and inspectable source fingerprints/policy.
Individual book data and evidence remain outside GitHub.

```sh
.venv/bin/python -m valuation.valuation_comparison \
  --project . \
  --job output/valuation_review_20261106/whole_library_v1 \
  --output output/valuation_review_20261106/results_comparison_new_run \
  --as-of 2026-11-09
```

The builder refuses overlapping/missing identities, changed inputs, assigned
grades, publishable scenarios, mismatched evidence bounds/counts and duplicate
offers. It validates all frozen completed reports and pilot input hashes,
reconciles the exact active catalog scope, and checks protected files before
and after generation. The frozen valuation worker and original evidence remain
unchanged.

All **754 tests pass on laptop and Mini**, including ten new comparison tests.
Independent validation rechecked all 7,046 scenario bounds and all endpoint
comparison/flag calculations. Twelve of the largest-change records were traced
into 82 original normalized API observations; that raw-row trace is a sample,
not an exhaustive raw-row audit. Final identification-scope validation still
matches all 162 source flags, with no unreviewed arrivals. Private receipts
confirm canonical files unchanged and zero new source requests.

The in-app browser's security policy blocked the local-file preview. The report
is saved for manual local review; browser rendering and interactive controls
were not visually verified. The calculations and exported comparison data were
verified independently of the HTML presentation. No external hosting or public
publication was introduced.

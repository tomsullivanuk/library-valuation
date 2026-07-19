# Market Intelligence

## Purpose

Market Intelligence is responsible for collecting objective market observations
from external sources.

It does not directly make appraisal claims, final valuation claims, or collector
recommendations. Its role is to gather market evidence that later components can
interpret.

Market Intelligence supports the v0.4.0 Market Validation Spike and future
automated valuation work by preserving externally observed signals in a form
that can be compared, reviewed, and analyzed.

## Design Principles

- Market observations are facts.
- Valuation estimates are derived from observations.
- Recommendations are derived from valuation estimates.
- Preserve market observations as durable data.
- Allow multiple observations per catalog item.
- Keep Market Intelligence independent from Research Assessment.
- Treat generated reports as artifacts, not canonical source-of-truth data.
- Prefer high-confidence observations over broad but noisy matches.

## Architectural Position

Conceptual pipeline:

```text
Amazon History
      |
      v
Catalog Repository
      |
      v
Research Assessment
      |
      v
Market Intelligence
      |
      v
Market Observation Repository
      |
      v
Valuation Estimate
      |
      v
Decision Support
```

Stages:

- Amazon History: user-provided purchase history and source evidence.
- Catalog Repository: durable catalog identity, bibliographic metadata, and
  acquisition facts.
- Research Assessment: generated research-priority scoring based on catalog and
  metadata signals.
- Market Intelligence: external market lookup and evidence collection.
- Market Observation Repository: durable storage for factual external market
  observations.
- Valuation Estimate: derived interpretation of one or more observations.
- Decision Support: later-stage recommendations based on valuation estimates,
  collector goals, and review state.

The pipeline separates facts, observations, estimates, and recommendations.
Catalog data records what the project knows about a book and its acquisition.
Market observations record what external sources showed at a point in time.
Valuation estimates interpret those observations. Recommendations translate
estimates into possible actions.

## Core Concepts

### Market Observation

A Market Observation is a factual external market signal for a catalog item.

Potential fields:

- `observation_id`
- `catalog_id`
- `source`
- `observation_date`
- `lookup_strategy`
- `asking_price`
- `sold_price`
- `currency`
- `condition`
- `edition_notes`
- `match_confidence`
- `raw_reference`

### Valuation Estimate

A Valuation Estimate is a derived interpretation of one or more market
observations.

Potential fields:

- `catalog_id`
- `estimated_value`
- `value_bucket`
- `valuation_confidence`
- `valuation_method`
- `observation_count`
- `valuation_date`

### Recommendation

A Recommendation is a later-stage decision derived from valuation estimates.

Examples:

- `ignore`
- `monitor`
- `research`
- `appraise`
- `insure`

Formal collector decisions such as appraise or insure remain future work. The
v0.5.0 Market Evidence Summary produces narrower review-routing recommendations,
such as manual research or edition review, while leaving durable collector
decisions to the user-owned review workflow.

## Lookup Strategy

Preferred lookup cascade:

1. ISBN
2. ISBN + publisher
3. ISBN + publication year
4. Title + author
5. Manual review

ISBN-first lookup reduces edition ambiguity because it starts with the strongest
available bibliographic identifier. Adding publisher or publication year can
improve confidence when a source returns multiple records for the same ISBN or
when edition-specific matching matters.

Title and author fallback should be treated as lower-confidence because it can
mix editions, formats, reprints, translations, and unrelated books with similar
titles. Manual review remains the appropriate path when automated lookup cannot
produce a confident match.

## Initial Market Sources

Candidate sources for the spike:

- AbeBooks
- ViaLibri
- BookFinder
- eBay sold listings

These are research targets, not production commitments. The spike should learn
which sources provide useful, reviewable evidence before the project commits to
marketplace integrations or automated source clients.

The AbeBooks feasibility spike established that AbeBooks can return usable
listing observations for a small ISBN-first sample in the current environment.
The earlier source-access failure was caused by the local Python environment
lacking default CA certificates; requests now use the installed trusted CA
bundle rather than disabling TLS verification.

The first experimental source command is:

```bash
python3 library_pipeline.py collect-abebooks-observations \
  --output-dir output \
  --limit 100
```

This command reads `output/market_validation_sample.csv` and writes generated
AbeBooks observation rows to `output/market_observations.csv` and
`output/market_observations.xlsx`. If AbeBooks returns no usable listing data or
blocks automated retrieval, the spike records lookup-status rows rather than
working around the source.

Observation coverage can be summarized with:

```bash
python3 library_pipeline.py report-market-observation-coverage \
  --output-dir output
```

This report keeps source diagnostics separate from valuation. It counts lookup
statuses, strategies, match confidence levels, diagnostic codes, and grouped
failure details, including generated search URLs in `raw_reference`.

The Market Validation analysis can be generated with:

```bash
python3 library_pipeline.py analyze-market-validation \
  --output-dir output
```

This analysis consumes the generated sample, sample metadata, and AbeBooks
observations. It stays downstream of Market Intelligence: observations remain
facts, while the analysis reports descriptive evidence about Research Scores and
Research Signals. It does not create valuation estimates or recommendations.

PR9 adds a downstream diagnostic review:

```bash
python3 library_pipeline.py review-research-signal-effectiveness \
  --output-dir output
```

The review classifies signal evidence using transparent sample-relative rules,
surfaces common signal combinations, and records model-calibration notes. These
interpretations remain separate from both market observations and Research
Assessment scoring logic.

The interpretation boundaries and provisional calibration principles derived
from PR8 and PR9 are summarized in
[Market Validation Findings and Calibration Principles](MARKET_VALIDATION_FINDINGS_v0.4.0.md).
They do not change the separation between observations, analysis, valuation,
and recommendations.

Possible Research Assessment refinements are documented separately in the
[Research Assessment Calibration Proposal](RESEARCH_ASSESSMENT_CALIBRATION_PROPOSAL_v0.4.0.md).
That proposal does not change Market Intelligence or reinterpret observations
as valuations.

PR12 expands the evidence base with `generate-expanded-market-validation-sample`
and `collect-expanded-abebooks-observations`. The expanded collector queries
only books added beyond the original sample, reuses existing observation rows,
and preserves the original generated artifacts.

PR13 refreshes downstream analysis with `analyze-expanded-market-validation`.
Market observations remain facts; score-band comparisons, signal
classifications, outlier interpretations, and calibration implications remain
derived analytical artifacts.

PR14 adds `simulate-research-assessment-calibration` as a downstream,
non-production analytical workflow. Scenario scores and rankings are
interpretations of existing signals and observations; they are not market
observations, valuations, or persisted Research Assessments.

PR15 records the resulting decision in
[Calibration Scenario Review and Decision](CALIBRATION_SCENARIO_REVIEW_v0.4.0.md):
v0.4.0 will preserve production Research Assessment scoring. Future design may
separate market likelihood from research effort, while Market Intelligence
continues to supply observations independently from either concept.

Known limitations remain: AbeBooks markup can change, condition text is not yet
normalized, and the spike does not guarantee broad catalog coverage.

### Full-library AbeBooks baseline

Version 0.6.0 adds an opt-in full-library baseline before the first live
second-source adapter. The command reads the current library catalog and
Research Assessments, reuses the existing AbeBooks collector, and writes
distinct generated artifacts:

```bash
.venv/bin/python library_pipeline.py collect-full-library-abebooks-observations \
  --output-dir output \
  --data-dir data \
  --delay 2 \
  --max-results-per-book 3
```

The default outputs are `full_abebooks_market_observations.csv/.xlsx`. A small
`--limit 100` test is recommended first. The command refuses to describe a run
as full-library when catalog items lack Research Assessments, and it remains
separate from monthly import and durable state.

The existing summary command converts the baseline observations into
`full_abebooks_market_evidence_summary.csv/.xlsx`. These are observed AbeBooks
asking-price evidence and review artifacts, not appraisals or realized-sale
estimates.

## Relationship To Market Validation Spike

Market Intelligence supports the Market Validation Spike documented in
[Market Validation Spike](MARKET_VALIDATION_SPIKE.md).

For the spike, Market Intelligence provides external market evidence that can be
compared against Research Score and the triggered research signals behind that
score. The comparison should help determine whether the Research Assessment
model is useful for identifying books that are materially more likely to possess
meaningful market value.

## Market Evidence Summary Schema

`output/market_evidence_summary.csv` and
`output/market_evidence_summary.xlsx` are the v0.5.0 generated per-book Market
Evidence Summary artifacts. They are source-neutral outputs derived from market
observations and catalog context. They are not durable repository records, and
the monthly Amazon import workflow must not read them back as source-of-truth
data.

The summary is designed to make observed asking-price evidence reviewable
without describing the output as an appraisal, fair market value, realized sale
price, pricing guarantee, or definitive valuation. Asking-price-derived ranges
are conservative reference ranges based on seller asking prices and must remain
visibly separate from completed-sale evidence, Research Assessment scoring, and
collector decisions.

The schema, aggregation, classification, range, and review version for this
generated artifact is `0.7.0-pr6`. The source of truth for column order in code is
`valuation.market_evidence_summary.MARKET_EVIDENCE_SUMMARY_FIELDNAMES`.

| Field | Meaning |
| --- | --- |
| `catalog_item_id` | Stable catalog item identifier for the summarized book. |
| `isbn_13` | Catalog ISBN-13 used for identity and review context, when available. |
| `isbn_10` | Catalog ISBN-10 used for identity and review context, when available. |
| `title` | Catalog title shown for human review. |
| `author` | Catalog author or contributor text shown for human review. |
| `observation_count` | Observation rows in the primary calculation set: AbeBooks when present, otherwise the available source rows. |
| `listing_count` | Parsed asking-price listings in the primary calculation set. |
| `status_row_count` | Lookup-status or diagnostic rows in the primary calculation set. |
| `source_count` | Count of distinct market sources represented in the observations. |
| `observed_source_names` | Stable, delimited source names represented in the summary. |
| `evidence_source_mix` | Stable source-composition label such as AbeBooks-only, eBay-only, or both. |
| `market_range_source` | Source used for the core confidence/range/recommendation calculations. |
| `source_price_comparability` | Whether source price summaries use one currency, matching currencies, or non-comparable currencies. |
| `abebooks_listing_count` / `abebooks_status_count` | AbeBooks listing and status rows represented. |
| `abebooks_currency` / `abebooks_min_asking_price` / `abebooks_median_asking_price` / `abebooks_max_asking_price` | Separate AbeBooks asking-price summary; blank numeric fields when its currency is mixed. |
| `ebay_active_listing_count` / `ebay_status_count` | eBay active-listing and status rows represented. |
| `ebay_active_currency` / `ebay_active_min_asking_price` / `ebay_active_median_asking_price` / `ebay_active_max_asking_price` | Separate eBay item asking-price summary; excludes shipping and blanks numeric fields when its currency is mixed. |
| `lookup_strategy` | Stable, delimited lookup strategies used across the observations. |
| `best_match_confidence` | Highest listing match-confidence level available for the catalog item. |
| `high_confidence_listing_count` | Listing count with high match confidence. |
| `medium_confidence_listing_count` | Listing count with medium match confidence. |
| `low_confidence_listing_count` | Listing count with low match confidence. |
| `unknown_confidence_listing_count` | Listing count with missing or unknown match confidence. |
| `currency` | Currency for the asking-price evidence, when a single currency can be stated safely. |
| `min_asking_price` | Lowest observed asking price among eligible listing evidence. |
| `median_asking_price` | Median observed asking price among eligible listing evidence. |
| `max_asking_price` | Highest observed asking price among eligible listing evidence. |
| `trimmed_low_asking_price` | Lower asking-price reference after documented outlier handling. Reserved for later range logic. |
| `trimmed_high_asking_price` | Upper asking-price reference after documented outlier handling. Reserved for later range logic. |
| `evidence_status` | Primary calculation-set availability status: listings observed, no evidence, source unavailable, or no usable query. Source-specific counts remain visible when supplemental evidence differs. |
| `outlier_sensitivity` | Initial deterministic sensitivity category based on listing count and observed asking-price spread. |
| `market_confidence` | Evidence-quality and usability category based on availability, currency consistency, usable prices, match quality, coverage, and outlier sensitivity. It does not classify book value. |
| `likely_low` | Cautious low reference in the asking-price-derived market range prototype, when supported. |
| `likely_mid` | Median-based reference in the asking-price-derived market range prototype, when supported. |
| `likely_high` | Cautious high reference in the asking-price-derived market range prototype, omitted for ambiguous or highly sensitive evidence. |
| `market_range_basis` | Stable method or unavailability reason explaining how the prototype range was handled. |
| `review_recommendation` | Stable next-action category derived primarily from market evidence quality and range support. |
| `review_reason` | Machine-readable reason or reasons supporting the next-action category. |
| `fallback_research_priority` | Existing Research Assessment priority exposed only when market evidence is missing or unavailable. It is not a price input. |
| `research_score` | Existing Research Assessment score copied for review context only. It is not a hidden price input. |
| `research_band` | Existing Research Assessment band copied for review context only. |
| `triggered_signals` | Existing Research Signal codes copied for review context and fallback prioritization. |
| `evidence_generated_at` | Timestamp when the generated summary artifact was produced. |
| `evidence_model_version` | Version of the summary, confidence, or range method used to generate populated evidence fields. |
| `evidence_notes` | Short limitations, warnings, or provenance notes for human review. |

PR3 aggregates source-neutral observation rows with:

```bash
python library_pipeline.py summarize-market-evidence \
  --observations output/market_observations.csv \
  --output-csv output/market_evidence_summary.csv \
  --output-xlsx output/market_evidence_summary.xlsx
```

Listing and source-status rows both contribute to coverage counts, while only
listing rows with parseable prices and currencies contribute to asking-price
statistics. When multiple currencies occur for a book, currency and all price
summary fields remain blank rather than silently combining currencies. The
trimmed reference fields equal observed minimum and maximum in PR3; later work
may introduce documented trimming. These outputs remain generated, non-durable
artifacts and do not change Research Assessment records or monthly import
behavior.

### Market confidence classification

`evidence_status` answers only whether listing evidence was observed or why a
lookup could not provide it. It remains separate from `market_confidence`, which
classifies how usable the observed asking-price evidence is. Neither field is an
appraisal or an assertion of book value.

PR4 applies this precedence:

1. Preserve `source_unavailable`, `no_query`, and `no_market_evidence` outcomes.
2. Classify mixed currencies as `mixed_currency_evidence` and listings without
   usable prices as `price_unavailable_evidence`.
3. Classify low or unknown best matches as `ambiguous_edition_match`, regardless
   of listing volume.
4. Classify one or two otherwise usable listings as `thin_market_evidence`.
5. Use `high_confidence_market_evidence` for at least five listings, including
   at least three high-confidence matches, when outlier sensitivity is not high.
6. Use `moderate_confidence_market_evidence` for at least three usable,
   high- or medium-match listings when outlier sensitivity is not high.
7. Use `unknown_market_confidence` when usable evidence does not satisfy those
   rules, including a larger sample with high outlier sensitivity.

The initial outlier-sensitivity heuristic is `not_applicable` when there are no
listings, `unknown_outlier_sensitivity` when prices cannot be compared, and
`high_outlier_sensitivity` for fewer than three listings. With at least three
usable prices, a maximum-to-minimum ratio of at least 5 is high, a ratio of at
least 3 is `moderate_outlier_sensitivity`, and a smaller ratio is
`low_outlier_sensitivity`. A positive maximum with a zero minimum is high.
These are deterministic starting heuristics, not statistically calibrated
thresholds.

### Conservative market range prototype

PR5 derives cautious numeric references from observed seller asking prices. The
prototype does not estimate actual sale proceeds and is not an appraisal, fair
market value, or definitive valuation. It performs no currency conversion and
does not use Research Score as a price input.

High-confidence evidence uses trimmed low, median, and trimmed high asking-price
references. Moderate-confidence evidence uses the same fields with min/max as
documented fallbacks. Thin evidence provides low and median references, but its
high outlier sensitivity suppresses the high reference. Ambiguous edition
matches also provide only low and median references, never a likely high.

No numeric range is produced for unavailable sources, missing queries, no market
evidence, mixed currencies, unavailable prices, or unknown confidence. In those
cases `market_range_basis` contains a stable `range_not_available_*` reason.
Supported basis values are:

- `high_confidence_observed_asking_prices`
- `moderate_confidence_observed_asking_prices`
- `thin_evidence_observed_asking_prices`
- `thin_evidence_high_outlier_sensitivity_observed_asking_prices`
- `ambiguous_match_observed_asking_prices`
- `ambiguous_match_high_outlier_sensitivity_observed_asking_prices`

### Review recommendation and fallback priority

PR6 makes the market-evidence-first flow actionable in the generated Market
Evidence Summary. It does not change durable Research Assessments, Collector
Reviews, the monthly import, or the existing Collector Workbook generator.

High- and moderate-confidence evidence is recommended for
`review_for_possible_sale` when `likely_mid` is at least 50 or `likely_high` is
at least 75. These are initial review-routing heuristics over asking prices, not
value claims or statistically calibrated sale thresholds. Usable evidence below
those thresholds is `market_evidence_sufficient`.

Ambiguous matches route to `review_edition_or_condition`. Thin, mixed-currency,
price-unavailable, and unknown-confidence evidence routes to
`manual_market_research_needed`; the reason also identifies fragile evidence
when outlier sensitivity is high. A missing usable query or insufficient core
metadata routes to `metadata_cleanup_needed` before fallback research.

When market evidence is missing or unavailable, existing Research Assessment
bands are exposed as `fallback_research_priority`. High and medium priorities
route to the recommendation of the same name. Low or absent priority routes to
`no_action_needed`. Research Score and band never alter an available asking-price
range or trigger a sale recommendation.

## Generated And Future Artifacts

Implemented generated outputs and possible future outputs include:

- `market_validation_sample.csv`
- `market_validation_sample_metadata.csv`
- `market_observations.csv`
- `market_observation_coverage_report.csv`
- `market_validation_analysis.csv`
- `research_signal_effectiveness_review.csv`
- `expanded_market_validation_sample.csv`
- `expanded_market_validation_sample_metadata.csv`
- `expanded_market_observations.csv`
- `expanded_market_observation_coverage_report.csv`
- `expanded_market_validation_analysis.csv`
- `expanded_research_signal_effectiveness_review.csv`
- `calibration_simulation.csv`
- `calibration_simulation_summary.csv`
- `calibration_simulation_candidate_movements.csv`
- `market_evidence_summary.csv`
- `market_evidence_summary.xlsx`
- `full_abebooks_review_workbook.xlsx`
- `full_abebooks_review_report.html`
- `market_values.csv`
- `market_validation_report.md`

`market_validation_sample.csv` and `market_validation_sample.xlsx` are the
first generated inputs for the spike. They select books across Research Score
bands and preserve triggered Research Signals so later Market Intelligence work
can compare individual signals against external market evidence.
`market_validation_sample_metadata.csv` and
`market_validation_sample_metadata.xlsx` preserve band-level sample targets,
available population counts, actual sample counts, seed, timestamp, Research
Assessment model version, and configuration hash for reproducibility.
`market_validation_analysis.csv` and `market_validation_analysis.xlsx` are
generated descriptive analysis artifacts. They should not become canonical
market data or valuation records.
`research_signal_effectiveness_review.csv` and
`research_signal_effectiveness_review.xlsx` are generated PR9 diagnostic
artifacts and are likewise non-canonical.

These are generated artifacts unless and until a durable repository format is
explicitly defined. They should not become canonical source-of-truth data by
accident.

The static review report is a reviewer-facing projection of the full Market
Evidence Summary. It separates recommendation queues with CSS-only tabs and
includes only essential identity, asking-price, research, and acquisition
context. Its AbeBooks range remains an observed asking-price reference—not an
appraisal, fair market value, or realized price. With source-aware input, five
compact displays align it with the workbook: Evidence Sources, eBay Listings,
eBay Price Range, eBay Status, and Source Price Comparability. eBay remains
supplemental, source prices remain separate, and seller identity is not shown.
Legacy AbeBooks-only summaries retain the original report columns.

## v0.7.0 eBay Active-Listing Evidence

Version 0.7.0 implements an isolated eBay Buy Browse API path through sandbox,
source-specific eBay observation/status rows, bounded targeted collection, and
source-aware Market Evidence Summary fields. Production behavior and
representative listings remain unverified. Any future live work stays bounded
to reviewer-priority cohorts—not an automatic full-library run.

eBay item price, shipping, currency, buying option, condition, availability,
match context, and source identifiers should remain separately auditable.
Source-specific measures should precede any combined range. Active listings are
asking-price evidence only and must never be labeled sold/completed evidence,
fair market value, an appraisal, a realized price, or expected proceeds. See
[v0.7.0 Release Plan](RELEASE_PLAN_v0.7.0.md).

### PR2 access-check boundary

The `ebay-access-check` command validates the application-token and one-search
path using explicit `EBAY_CLIENT_ID`, `EBAY_CLIENT_SECRET`,
`EBAY_MARKETPLACE_ID`, and `EBAY_ENVIRONMENT` variables. It accepts one query,
caps results at three, writes no output, and redacts credentials and tokens from
failures. Its safe console snippets are connectivity diagnostics, not market
observations and not inputs to aggregation. Sold/completed listings, observation
normalization, multi-source summaries, and review-artifact changes remain later
PRs.

Sandbox and production status must be reported separately. PR2 uses the sandbox
keyset only. Production was not tested and its keyset remains disabled pending
Marketplace Account Deletion/Closure notification compliance through either
notification subscription or an approved exemption. Sandbox connectivity must
not be interpreted as production entitlement or representative market coverage.

On 2026-07-17, PR2 used sandbox and `EBAY_US`. The initial local TLS failure was
resolved by setting `SSL_CERT_FILE` to the installed certifi CA bundle; verified
HTTPS remained enabled. After correcting an incorrect local secret value, OAuth
application-token acquisition succeeded and one Browse API item-summary request
completed. The query `Springer Handbook of Spacetime` returned zero sandbox
results. That validates sandbox access and request construction, not production
coverage, search quality, or market evidence. No observation or response
artifact was written.

### PR3 reusable client boundary

PR3 adds a reusable active-listings client for one caller-supplied query. It
normalizes mocked Browse item summaries into provisional source-specific,
in-memory results containing item ID, title, item price and currency, item URL,
condition, buying options, item-location country, query, marketplace, and source
label. Seller username is intentionally omitted. It preserves non-USD currencies
and missing fields without converting, estimating, or rejecting them.

At the PR3 boundary these objects are not Market Observations and do not affect
confidence, ranges, recommendations, workbooks, or reports. Query construction
from catalog metadata, reviewed match-confidence rules, shipping normalization,
and generated observation artifacts remain later work. Active listings remain
asking-price evidence only; PR2 sandbox quality is not representative and
production remains gated.

### PR4 observation adapter boundary

PR4 adds `valuation/ebay_observations.py`, a pure, network-free, file-free
adapter. It converts catalog context plus a PR3 search result into rows with the
existing AbeBooks-compatible market-observation field order; it does not change
that canonical row shape. Listing results become `observed` rows, while empty
queries, zero results, and caller-reported safe failures become `no_query`,
`no_results`, and `source_unavailable` status rows respectively.

The adapter records eBay item price only. Currency is preserved without
conversion, shipping is excluded, and buying options are retained as context
without auction/fixed-price interpretation. Item ID, buying options,
marketplace, and item-location country remain in `raw_reference` or
`match_notes`; raw API payloads are neither accepted nor retained. Edition and
match confidence remain `unknown` pending later reviewed rules.

PR4 adds no command, collection workflow, generated observation file, Market
Evidence Summary integration, workbook change, or HTML report change. Active
listings remain asking-price evidence only. Production access remains disabled
and unverified pending the existing compliance gate.

### PR5 targeted collection boundary

`collect-targeted-ebay-observations` turns the PR3 client and PR4 adapter into
an explicit bounded workflow. It requires `--summary`, `--output`, and
`--limit-books`; output must remain under `output/`. The default cohort is
`review_for_possible_sale`. Repeated `--review-recommendation` options may also
include `manual_market_research_needed` and `review_edition_or_condition`.
Candidates are ordered deterministically by queue, asking-price review context,
research score, title, and catalog ID.

Query construction uses ISBN-13, ISBN-10, title plus author, then usable title
alone. Missing queries produce `no_query`, empty searches produce `no_results`,
and a safe client failure produces `source_unavailable` before the run stops to
avoid repeated global authentication failures. The command caps collection at
50 books and 10 results per book and defaults to three results and a one-second
inter-request delay.

The paired `output/targeted_ebay_observations.csv/.xlsx` artifacts retain the
existing observation field order. They contain item asking price only, preserve
currency, exclude shipping, and leave match confidence unknown. They are not
raw responses or durable market history. They become summary inputs only when
explicitly passed to the PR6 command; they remain absent from the current
workbook and HTML report. Sandbox alone has been validated; production remains
disabled and unverified, and sandbox results are not representative.

The first PR5 live smoke used sandbox `EBAY_US`, verified TLS through certifi,
two ISBN-13 queries, and a limit of three results per book. OAuth and both Browse
requests completed, producing two `no_results` rows and ignored CSV/XLSX files.
This validates the sandbox access, adapter, and artifact path only—not production
coverage, listing availability, price quality, or match quality.

### PR6 source-aware summary prototype

`summarize-market-evidence` now accepts repeated `--observations` inputs. It
still produces one generated row per catalog item, but adds separate AbeBooks
and eBay listing/status counts, currencies, and price summaries plus source-mix,
comparability, and range-source labels.

When AbeBooks rows exist, the existing core price, confidence, range, and review
fields remain calculated from AbeBooks only. eBay is supplemental: its active
listing prices are not pooled, cannot independently raise core confidence, and
its `no_results` does not mean global market absence. eBay-only items use the
existing cautious rules and retain unknown match confidence. Mixed currencies
within a source blank that source's numeric price summary; differing currencies
across sources are labeled non-comparable. No conversion or shipping is added.
At the v0.7.0 source-summary boundary, workbook and HTML report integration
remained deferred; v0.8.0 now provides those reviewer projections.

### PR7 local workflow readiness

The local readiness run combined
`output/full_abebooks_market_observations.csv` and
`output/smoke_ebay_observations.csv` through repeated `--observations`. It wrote
ignored `smoke_multisource_market_evidence_summary.csv/.xlsx` files containing
3,014 catalog rows. Source mix was 3,012 AbeBooks-only and 2 AbeBooks-plus-eBay.
The run contained 2 eBay status rows, 0 eBay listings, 2,896 books with priced
AbeBooks evidence, and 0 books with priced eBay evidence. Comparability was
`single_source_currency` for 2,896 rows and `no_priced_listings` for 118 rows.

This confirms the generated multi-source command path and source-specific
`no_results` interpretation. It does not validate production eBay access,
listing availability, prices, or match quality. Operational use still requires
locally sourced ignored credentials, an explicit small targeted collection,
and deliberate repeated-input summary generation. Outputs remain asking-price
evidence, not appraisals or realized-sale estimates. Existing AbeBooks workbook
and HTML projections do not consume the multi-source fields.

### v0.8.0 production targeted smoke

Before production collection, v0.8.0 PR1 removed seller username from the
normalized eBay listing object and eBay observation projection. The shared
25-field schema remains unchanged, but `seller` is blank for eBay rows and
seller identity is not included in `match_notes`.

On 2026-07-18, PR2 ran the existing targeted collector in production against
the first two deterministic `review_for_possible_sale` candidates from the
generated full AbeBooks summary. Both used ISBN-13 queries, with a maximum of
three results per book and a one-second delay. The bounded run completed and
produced four `observed` rows:

- four item prices in USD: 389.30, 333.10, 379.49, and 326.23;
- four item IDs and four listing URLs;
- four conditions and fixed-price buying-option context;
- source `ebay_active_listings` and match confidence `unknown` for every row;
- blank `seller` for every row; and
- no seller identity or seller label in any `match_notes` value.

The paired CSV/XLSX smoke artifacts remain ignored under `output/`; they are
validation evidence, not committed data or durable market history. No raw API
response was retained. This small cohort validates the production targeted
observation path and seller-suppression boundary, not representative coverage,
price quality, edition matching, broader collection, or downstream integration.

### v0.8.0 representative production validation

PR3 expands validation—not product integration—to 100 production books. The
collector ceiling is now 100, with 101 still rejected. The normal multi-queue
selector intentionally preserves review-priority order, so a local ignored
cohort file selected the strongest 34 `review_for_possible_sale`, 33
`manual_market_research_needed`, and 33 `review_edition_or_condition` candidates
using the existing deterministic ordering within each queue. No recommendation
or production-selection semantics changed.

All 100 books had ISBN-13 queries. The run produced 242 rows: 229 `observed`
listings across 87 books and 13 `no_results` rows. There were no `no_query` or
`source_unavailable` rows. Every observed listing had a USD price, condition,
item ID, and listing URL; all 229 item IDs were unique. USD item prices ranged
from 4.43 to 475.87, with a median of 57.87. Shipping remains excluded, so those
figures are evidence-distribution diagnostics rather than valuation ranges.

Observed coverage by input queue was:

- `review_for_possible_sale`: 32 of 34 books, 88 listing rows;
- `manual_market_research_needed`: 24 of 33 books, 51 listing rows; and
- `review_edition_or_condition`: 31 of 33 books, 90 listing rows.

A conservative token-overlap review found that 224 of 229 listing titles shared
at least half of the catalog-title tokens, 202 shared at least three quarters,
and 175 included all catalog-title tokens. The five lower-overlap rows were
largely plausible truncations, translated titles, or format variants, although
a bundle-like result demonstrates that ISBN queries do not remove the need for
reviewed matching. Match confidence therefore remains `unknown`.

Privacy suppression held across the entire artifact: all 242 `seller` values
were blank, no `match_notes` mentioned seller identity, and seller username was
not reintroduced into normalized objects. No raw API response was retained.

The representative multi-source summary contained 3,014 rows: 100
`abebooks_and_ebay_active_listings` and 2,914 `abebooks_only`. It recorded 229
eBay listings and 13 eBay statuses. Price comparability was
`same_currency_separate_source_summaries` for 87 books,
`single_source_currency` for 2,809, and `no_priced_listings` for 118.
`market_range_source` remained `abebooks` for all 3,014 rows, and direct
comparison found no changes to AbeBooks `likely_low`, `likely_mid`,
`likely_high`, `market_confidence`, or `review_recommendation`.

The evidence is useful enough to justify a separately designed reviewer-facing
source-context PR: coverage is high, identity/URL provenance is present, and
title plausibility is generally strong. It is not sufficient to auto-match
editions, pool prices, add shipping, convert currencies, infer sold prices, or
start broader/full-library collection.

### v0.8.0 source-aware reviewer workbook

PR4 projects the existing multi-source summary into the generated reviewer
workbook without changing aggregation semantics. Review Queue, Possible Sale,
Manual Research, and Edition Condition Review retain their existing core fields
and append five compact displays: Evidence Sources, eBay Listings, eBay Price
Range, eBay Status, and Source Price Comparability.

The compact price range presents eBay minimum/median/maximum item prices with
their returned currency. It does not include shipping, convert currency, pool
prices with AbeBooks, or alter `likely_low`, `likely_mid`, `likely_high`, market
confidence, or recommendation. Status text is explicitly source-specific; an
eBay status-only row does not imply global market absence.

Evidence Detail retains source-aware technical fields from the input summary,
including source mix, core range source, comparability, source-specific counts,
currencies, and price summaries. Run Summary adds source-mix, total eBay
listing/status, eBay coverage, core-range-source, and comparability counts only
when the source-aware schema is present. Field Definitions documents the active-
listing, non-appraisal, human-review, seller-suppression, shipping, conversion,
and unknown-match-confidence boundaries.

Legacy AbeBooks-only summary inputs remain supported. They preserve all seven
workbook sheets and existing AbeBooks review behavior, with a conservative
`AbeBooks only` source display and blank eBay details. The generated workbook
remains ignored and non-durable.

### v0.8.0 source-aware HTML report

PR5 conditionally adds the same five compact displays to each HTML reviewer
queue when the input includes multi-source fields. A source-aware evidence
summary reports mixed-source books, books/listings with observed eBay evidence,
and status-only books. The field guide and caveats state that eBay is
supplemental active-listing item-price evidence, shipping is excluded, no
currency conversion or price pooling occurs, match confidence remains unknown,
and human title/edition review is required. Seller identity is not stored or
displayed. AbeBooks-only input omits the new columns and retains the prior
presentation.

### v0.8.0 release boundary

The release boundary is the privacy-hardened, bounded production eBay path plus
source-aware reviewer workbook and HTML projections. AbeBooks remains primary
for mixed-source conservative ranges. eBay remains supplemental active-listing
item-price evidence: it excludes shipping, is not converted or pooled, retains
unknown match confidence, and requires human edition/title review. Seller
identity is not stored or displayed. Production full-library eBay collection,
sold/completed evidence, improved matching heuristics, automated edition
matching, shipping-aware pricing, currency normalization, additional sources,
and richer reviewer workflow remain future work.

### v0.9.0 checkpoint provenance boundary

The full-library design separates minimum resumability state from market
evidence. A versioned immutable manifest records input fingerprint, ordered
candidate hash, source/environment, marketplace, query/observation versions,
result limit, and seller-suppression policy. A versioned ledger records only
sanitized per-item attempts and outcomes. Immutable atomic item parts contain
the canonical 25-field eBay observations. No credentials, tokens, authorization
headers, raw responses, or seller identity belong in any checkpoint file.

Interrupted `in_progress` items adopt a valid deterministic part if the part was
committed before interruption, otherwise they recover to eligible pending state.
Observed, no-results, no-query, terminal source-unavailable, and terminal
internal failures are skipped. This supports later deterministic materialization
and may inform a future monthly freshness design, but it is not yet durable
collection history.

PR3 uses this state through a separate production-only full-library command.
The command preserves the ISBN-13, ISBN-10, title/author, then title query order
and the existing observation adapter. It writes one atomic part per terminal
source outcome, never stores seller identity or raw responses, and reports only
aggregate progress. Rate-limit/temporary failures retry within configured
bounds; authentication-class failures stop the run after a sanitized terminal
status. Final combined observations, summary regeneration, and reviewer
artifacts remain later PRs.

PR4 adds an in-memory token session only to the full-library path. One token is
reused, proactively refreshed, and refreshed once after a Browse 401. Structured
HTTP/network metadata drives credential/global-stop, temporary/rate-limit, and
item-terminal classifications. Retry-after and exponential backoff are capped;
retry budgets reset per invocation while cumulative attempts remain auditable.
Exhausted temporary failures remain eligible on resume. Aggregate token,
request, retry, rate-limit, interruption, resume, and recovered-part metrics are
safe summary data; tokens, headers, raw bodies, and expiration state are not.

### v0.9.0 bounded production resume validation

PR5 ran the full-library path against 20 deterministic production books, then
interrupted it normally after seven completed items. The checkpoint retained
seven valid observed parts, one recoverable partless in-progress item, and
twelve pending items. Resume from the same checkpoint completed all 20 books
without querying any previously completed catalog item again. Integrity checks
accepted 20 unique deterministic parts and 60 canonical observation rows.

All 20 queries used ISBN-13 and produced three listings, for 60 USD observations
with asking prices from $4.04 to $196.07 and a median of $35.37. Every listing
title shared at least half its catalog-title tokens in the broad diagnostic used
for the prior 100-book validation. This supports operational and coarse
plausibility readiness only; match confidence remains unknown and human
edition/condition review remains required.

The initial invocation reused one token across seven Browse requests, and the
resumed invocation reused one token across 13 requests. No refresh, retry,
rate-limit, temporary-failure, or global-stop event occurred. Seller fields and
seller notes remained blank, and checkpoint files contained no credentials,
tokens, headers, expiration metadata, or raw responses. The remaining gate is
the approximately 3,014-book production baseline and its evidence-quality
report; final summaries and reviewer artifacts remain later work.

## Non-Goals

This document does not define or implement:

- Marketplace integrations.
- Scraping logic.
- API clients.
- Valuation algorithms.
- Appraisal methodology.
- Pricing guarantees.
- Investment advice.
- Continuous market monitoring.

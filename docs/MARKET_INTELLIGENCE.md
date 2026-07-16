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
generated artifact is `0.5.0-pr6`. The source of truth for column order in code is
`valuation.market_evidence_summary.MARKET_EVIDENCE_SUMMARY_FIELDNAMES`.

| Field | Meaning |
| --- | --- |
| `catalog_item_id` | Stable catalog item identifier for the summarized book. |
| `isbn_13` | Catalog ISBN-13 used for identity and review context, when available. |
| `isbn_10` | Catalog ISBN-10 used for identity and review context, when available. |
| `title` | Catalog title shown for human review. |
| `author` | Catalog author or contributor text shown for human review. |
| `observation_count` | Total source observation rows considered for the catalog item, including listing and status rows. |
| `listing_count` | Count of observation rows that represent parsed asking-price listings. |
| `status_row_count` | Count of lookup-status or diagnostic rows that do not represent listings. |
| `source_count` | Count of distinct market sources represented in the observations. |
| `observed_source_names` | Stable, delimited source names represented in the summary. |
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
| `evidence_status` | Evidence availability status: listings observed, no evidence, source unavailable, or no usable query. It does not classify evidence quality. |
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

The static AbeBooks review report is a reviewer-facing projection of the full
Market Evidence Summary. It separates recommendation queues with CSS-only tabs
and includes only essential identity, asking-price, research, and acquisition
context. Its one displayed range remains an observed asking-price reference—not
an appraisal, fair market value, or realized price. The latest acquisition year
is shown with a verification prompt for pre-2021 or unknown acquisitions; this
presentation never suppresses market evidence. Detailed market confidence,
outlier sensitivity, and possession-confidence fields remain in the workbook
and evidence artifacts. eBay active listings are the proposed v0.7.0 theme;
multi-source evidence is not part of v0.6.0.

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

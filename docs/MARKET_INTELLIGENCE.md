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

Recommendations are future work. Market Intelligence should provide evidence for
recommendations, not produce recommendations itself.

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

The schema version for this generated artifact is `0.5.0-pr2`. The source of
truth for column order in code is
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
| `evidence_status` | Evidence availability or usability status. Reserved for later classification logic. |
| `outlier_sensitivity` | Indicator of whether asking-price evidence is materially affected by outliers. Reserved for later classification logic. |
| `market_confidence` | Evidence-quality classification based on coverage, match quality, usable listing count, and ambiguity. Reserved for later confidence rules. |
| `likely_low` | Conservative low end of an asking-price-derived market range. Reserved for later range logic. |
| `likely_mid` | Conservative midpoint or reference point of an asking-price-derived market range. Reserved for later range logic. |
| `likely_high` | Conservative high end of an asking-price-derived market range. Reserved for later range logic. |
| `market_range_basis` | Short method or reason text explaining the range basis. Reserved for later range logic. |
| `review_recommendation` | Review disposition such as accept, verify, investigate, or fallback research. Reserved for later recommendation logic. |
| `review_reason` | Explainable reason codes or short reason text supporting the review recommendation. Reserved for later recommendation logic. |
| `fallback_research_priority` | Priority to use when market evidence is missing, thin, ambiguous, or low-confidence. Reserved for later bridge logic. |
| `research_score` | Existing Research Assessment score copied for review context only. It is not a hidden price input. |
| `research_band` | Existing Research Assessment band copied for review context only. |
| `triggered_signals` | Existing Research Signal codes copied for review context and fallback prioritization. |
| `evidence_generated_at` | Timestamp when the generated summary artifact was produced. |
| `evidence_model_version` | Version of the summary, confidence, or range method used to generate populated evidence fields. |
| `evidence_notes` | Short limitations, warnings, or provenance notes for human review. |

PR2 defines the schema only. Later PRs may populate reserved interpretation,
range, confidence, and recommendation fields from source-specific market
observations. This PR does not aggregate `output/market_observations.csv` into
the summary artifact and does not change Research Assessment scores, bands,
signals, persisted assessment records, or monthly import behavior.

## Future Generated Artifacts

Likely future generated outputs include:

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

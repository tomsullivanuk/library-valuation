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

## Relationship To Market Validation Spike

Market Intelligence supports the Market Validation Spike documented in
[Market Validation Spike](MARKET_VALIDATION_SPIKE.md).

For the spike, Market Intelligence provides external market evidence that can be
compared against Research Score and the triggered research signals behind that
score. The comparison should help determine whether the Research Assessment
model is useful for identifying books that are materially more likely to possess
meaningful market value.

## Future Generated Artifacts

Likely future generated outputs include:

- `market_validation_sample.csv`
- `market_observations.csv`
- `market_values.csv`
- `market_validation_report.md`

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

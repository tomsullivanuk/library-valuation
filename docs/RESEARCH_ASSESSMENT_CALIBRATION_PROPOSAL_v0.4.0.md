# Research Assessment Calibration Proposal: v0.4.0

## Purpose

This document proposes possible future refinements to the Research Assessment
model based on the v0.4.0 Market Validation evidence. It translates the PR8
analysis, PR9 signal review, and PR10 interpretation guardrails into options for
review before any scoring change is implemented.

This is a proposal only. PR11 does not modify `config/research_signals.yml`,
scoring code, Research Signal definitions or weights, CLI behavior, generated
artifact schemas, or durable data models. Current point values are included
only to describe the model being reviewed.

## Evidence Base

The proposal uses:

- The PR8 Market Validation Analysis of Research Score bands and AbeBooks
  asking-price observations.
- The PR9 Research Signal Effectiveness Review of individual signals,
  combinations, and candidate misses.
- The interpretation principles and calibration guardrails documented in
  [Market Validation Findings and Calibration Principles](MARKET_VALIDATION_FINDINGS_v0.4.0.md).
- A deterministic validation sample of 65 books rather than the intended 100.
- 189 AbeBooks observation rows, with at least one observation for all 65 books
  in this particular run.

The evidence is directional. It comes from one source, uses asking rather than
sold prices, and contains uneven score-band populations. The `2-3` validation
band has no catalog population, the `6-7` band contains only five books, and
several signals have small samples. Complete AbeBooks coverage in this run does
not establish complete market coverage.

## Current Model Assessment

The model appears directionally useful as a research-priority heuristic. The
highest validation band showed the strongest average and maximum observed asking
prices, indicating that the current signals contain some market-relevant
information. High-score and low-score books were not interchangeable in all
observed measures.

The evidence does not show a true score gradient. Median asking prices were not
monotonic across populated validation bands, and individual false-positive and
false-negative candidates remain. A high Research Score therefore should not be
interpreted as a proportional estimate of market value.

The validation bands also require careful interpretation. The sampling helper
labels every raw Research Score of 8 or greater as `8-10`; scores are not capped
at 10. The production Research Assessment uses different priority thresholds:
`none` at 0, `low` from 1, `medium` from 15, and `high` from 30. The heavy
population in the validation `8-10` band therefore demonstrates compression in
the experimental grouping, not by itself a defect in the production bands.

Some high scores appear to be assembled from signals that express research
friction or possible upside rather than consistent market strength. Conversely,
some low-score books had stronger asking-price evidence than expected, suggesting
that the current model may not represent every market-relevant attribute. These
cases support calibration review but do not identify causal signal effects.

## Signal-by-Signal Calibration Review

### `old_publication_year` (current weight: 12)

- **Current role:** Prioritizes books published before 1950 as possible older or
  collectible material.
- **Observed evidence:** This signal did not appear in the current 65-book PR9
  signal sample, so no signal-level market comparison is available.
- **Interpretation:** Upside-oriented and context-dependent; insufficient sample.
- **Proposed future treatment:** Keep but monitor. Consider splitting age into
  meaningful ranges only after a sample includes enough older books. Do not
  increase or decrease weight from the present evidence.

### `university_press` (current weight: 15)

- **Current role:** Gives the largest current weight to recognized university-
  press publication as a proxy for scholarly or specialist interest.
- **Observed evidence:** Six sampled books carried the signal. Its median asking
  price met or exceeded the sample median, and its maximum reached the strongest
  observed level, although the sample remains small.
- **Interpretation:** Provisionally consistency-oriented with possible upside.
- **Proposed future treatment:** Keep as-is for an initial simulation. Test
  whether its effect remains useful alone and with `scholarly_lc_subject`; more
  data is required before considering an increase.

### `specialist_publisher` (current weight: 10)

- **Current role:** Prioritizes configured specialist or scholarly publishers
  that are not classified as university presses.
- **Observed evidence:** Only one sampled book carried the signal, preventing a
  meaningful consistency assessment.
- **Interpretation:** Context-dependent; insufficient sample.
- **Proposed future treatment:** Keep but monitor and require more data. Review
  publisher-tier coverage before changing weight or splitting publisher types.

### `missing_lcc` (current weight: 8)

- **Current role:** Raises research priority when Library of Congress
  classification is missing and bibliographic review may be useful.
- **Observed evidence:** Six sampled books carried the signal, and its median
  asking price met or exceeded the sample median.
- **Interpretation:** Provisionally consistency-oriented, but conceptually it is
  a metadata-gap signal rather than direct evidence of market demand.
- **Proposed future treatment:** Keep as-is and monitor. Do not increase weight
  until the observed association repeats and can be distinguished from other
  signals or metadata-selection effects.

### `missing_oclc` (current weight: 5)

- **Current role:** Raises research priority when edition matching may be harder
  because an OCLC identifier is absent.
- **Observed evidence:** It was common, appearing on 31 sampled books, but its
  median asking price was below the sample median. High prevalence may limit its
  ability to discriminate market-likely books.
- **Interpretation:** Weak or noisy as a market signal; useful as a research-
  effort indicator.
- **Proposed future treatment:** Consider decreasing its market-priority effect
  or separating research effort from market likelihood. Consider splitting a
  simple missing identifier from broader edition ambiguity.

### `scholarly_lc_subject` (current weight: 10)

- **Current role:** Prioritizes configured LC subject classes associated with
  scholarly research interest.
- **Observed evidence:** Fourteen sampled books carried the signal. It produced
  a very high maximum asking price but a below-sample median and was identified
  as a possible false-positive driver under PR9's sample-relative rules.
- **Interpretation:** Upside-oriented and context-dependent rather than a
  consistent standalone market signal.
- **Proposed future treatment:** Consider splitting by LC class or subject
  family and reducing reliance on the broad standalone signal. Test combinations
  with publisher signals before considering any weight change.

### `multiple_acquisitions` (current weight: 6)

- **Current role:** Treats repeat acquisitions as a reason for review because
  they may indicate duplicates, replacements, or collected works.
- **Observed evidence:** Five sampled books carried the signal, with a median
  below the sample median and a moderate maximum. The acquisition reason is not
  currently represented.
- **Interpretation:** Context-dependent and currently weak or inconclusive.
- **Proposed future treatment:** Keep but monitor. Consider splitting deliberate
  duplicate collecting from replacement copies, quantity artifacts, and repeat
  orders if the acquisition data can support that distinction.

### `low_metadata_confidence` (current weight: 6)

- **Current role:** Raises research priority when metadata resolution is
  incomplete, uncertain, or requires manual review.
- **Observed evidence:** Only three sampled books carried the signal. Their
  median asking price was low, and PR9 classified the signal as a possible
  false-positive driver.
- **Interpretation:** Sparse and noisy as a market signal; useful as a workflow-
  urgency or confidence indicator.
- **Proposed future treatment:** Consider decreasing or removing its direct
  market-priority contribution while preserving its visibility for manual
  review. Split the broad condition into explicit missingness or match-quality
  patterns before assigning future weights.

## Candidate Signal Splits

The following splits are plausible design candidates, not approved signal
definitions:

| Current signal | Candidate split | Reason to investigate |
|---|---|---|
| `scholarly_lc_subject` | LC class or subject family | A broad subject flag may mix consistent subjects with rare upside cases. |
| Publisher signals | University press, configured specialist tier, and unclassified scholarly publisher | Publisher categories have different sample sizes and may carry different consistency. |
| `old_publication_year` | Pre-1900, 1900-1929, and 1930-1949, or evidence-based alternatives | A single pre-1950 threshold treats materially different ages alike. |
| `low_metadata_confidence` | Manual review, low-confidence match, non-match, and incomplete fields | Workflow uncertainty is not one market phenomenon. |
| `missing_oclc` | Identifier absent versus edition ambiguity | Missing data and difficult edition matching should not automatically have the same market interpretation. |
| `multiple_acquisitions` | Duplicate collecting, replacement, quantity, and repeat-order patterns | Acquisition intent determines whether repetition is meaningful. |

Any split would need adequate population counts, deterministic evidence fields,
and an explainable migration from the current signal.

## Candidate Signal Combinations

Compound effects may explain market evidence better than additive standalone
signals:

- `university_press + scholarly_lc_subject`: publisher specialization may make a
  broad scholarly subject signal more credible and reduce subject-only false
  positives.
- `old_publication_year + specialist_publisher`: age may become more informative
  when paired with a specialist publishing context.
- `old_publication_year + low_metadata_confidence`: this may identify difficult
  older editions, but it could also amplify metadata noise and requires manual
  false-positive review.
- `multiple_acquisitions + scholarly_lc_subject`: repeated acquisition in a
  specialist subject may represent deliberate collecting rather than an order
  artifact.
- `university_press + missing_lcc`: the combination may distinguish genuinely
  incomplete scholarly metadata from generic missing classification.

Compound scoring is not proposed for immediate implementation. Exact
combinations can be sparse, and adding interaction points risks double-counting
the same underlying evidence.

## Score Band Recalibration

The experimental score bands were useful for stratified sampling, but they are
not suitable as market-likelihood tiers in their current form. The `2-3` band is
empty, `6-7` is sparse, and all raw scores of 8 or greater are compressed into
`8-10`. These labels obscure variation among books with materially higher raw
scores.

Three interpretations should remain distinct:

- **Research priority:** how strongly current evidence justifies human review.
- **Market-likelihood tier:** a future evidence-based estimate that meaningful
  market signals are present.
- **Review urgency or confidence:** whether missing or uncertain metadata
  requires attention.

The current production bands should be retained until simulation shows a safer
alternative. Future options include recalculating validation quantiles from the
catalog distribution, defining non-overlapping raw-score ranges that cover the
actual score span, or preserving production bands while reporting separate
signal-role and confidence dimensions. Bands should not be relabeled as value
tiers without stronger evidence.

## Proposed Calibration Options

### Option A: Conservative Cleanup

- **Summary:** Keep all signals and weights; clarify band semantics and separate
  market evidence from workflow-confidence language in documentation.
- **Likely benefits:** Lowest regression risk and no overfitting to the sample.
- **Risks:** Known noisy signals and compressed validation bands remain.
- **Implementation complexity:** Low.
- **Validation needs:** Distribution report and documentation review.
- **Suitability for v0.5.0:** Suitable, but offers limited model improvement.

### Option B: Signal Role Rebalancing

- **Summary:** Preserve evidence and explainability while distinguishing
  consistency, upside, and research-effort signals. Simulate reduced standalone
  influence for noisy metadata signals and broad upside signals before selecting
  any weights.
- **Likely benefits:** Addresses false-positive pressure without discarding rare
  upside evidence; makes the score's purpose clearer.
- **Risks:** Role labels and weight changes could still overfit one sample or
  suppress useful edge cases.
- **Implementation complexity:** Moderate.
- **Validation needs:** Before/after score distributions, ranking changes,
  candidate-case review, and repetition against another sample or source when
  feasible.
- **Suitability for v0.5.0:** Suitable after simulation and review.

### Option C: Expanded Model Design

- **Summary:** Split broad signals, add selected compound signals, and redesign
  score bands around separate market-likelihood and review-confidence concepts.
- **Likely benefits:** Better conceptual precision and richer interactions.
- **Risks:** Highest overfitting, migration, double-counting, and explainability
  risk with the current evidence base.
- **Implementation complexity:** High.
- **Validation needs:** Larger samples, additional market evidence, interaction
  analysis, migration design, and extensive before/after testing.
- **Suitability for v0.5.0:** Not recommended without additional validation.

## Recommended Path

The preferred path is **Option B: Signal Role Rebalancing**, beginning with a
simulation rather than an implementation PR.

This approach fits the evidence because the current model appears directionally
useful but mixes different concepts: consistent market evidence, occasional
upside, and research workflow uncertainty. It avoids discarding the existing
model or treating a small sample as authority for final weights. It also keeps
the strongest current property of Research Assessment: every score can be
explained through persisted signals.

The first simulation should leave `university_press` and `missing_lcc` stable as
reference signals; test reduced standalone influence for `missing_oclc`,
`low_metadata_confidence`, and broad `scholarly_lc_subject`; and report the
effect of keeping sparse signals unchanged. These are simulation scenarios, not
approved production changes or final weights.

Signal splits, compound scoring, and production band redesign should be
deferred. After simulation, reviewers should inspect changed rankings and the
known false-positive and false-negative candidates. Additional sold-price or
second-source data would materially strengthen a later implementation decision,
but it is not required to compare hypothetical score distributions safely.

## Proposed Acceptance Criteria for a Future Scoring-Change PR

A future implementation PR should demonstrate that:

- Existing tests remain stable or are intentionally updated with documented
  behavioral reasons.
- Before/after catalog score and production-band distributions are produced.
- Every distribution change is traceable to a reviewed signal or threshold.
- False-positive pressure is reduced in the reviewed candidate set without
  hiding rare upside evidence.
- Known false-negative candidates are better surfaced where supported, or the
  remaining gaps are explicitly documented.
- Research Candidate ranking changes remain explainable at the book and signal
  level.
- Triggered-signal evidence and model/config versioning remain reproducible.
- Generated outputs remain backward compatible, or migration is documented.
- No valuation estimate, value bucket, appraisal claim, or sale recommendation
  is introduced.
- The implementation includes focused unit tests and a reproducible comparison
  report suitable for review.

## Risks and Caveats

- The model could be overfit to 65 sampled books.
- Maximum asking prices could be mistaken for consistent market evidence.
- Rare but meaningful signals could be weakened because their sample is sparse.
- AbeBooks could be treated as complete market truth despite source and listing
  biases.
- Research priority could be confused with market value or valuation confidence.
- Signal splits and interactions could degrade explainability or double-count
  evidence.
- Complexity could grow before the product has enough evidence or workflow need
  to justify it.
- Simulation improvements could reflect the current sample while failing on the
  broader catalog or a future market snapshot.

## Recommended Next PR

The recommended next PR is:

**PR12 — Before/After Calibration Simulation**

PR12 should apply a small set of explicitly hypothetical calibration scenarios
to existing assessments without changing production configuration or persisted
Research Assessment state. It should compare score distributions, priority
bands, Research Candidate rankings, and known candidate misses. The simulation
should provide the evidence needed to decide whether a later v0.5.0 scoring-
change PR is justified or whether another market source should be validated
first.

## Non-Goals

This proposal does not approve or implement new weights, signals, combinations,
bands, valuation logic, market sources, output schemas, or durable state. It
does not treat asking prices as valuations or recommend buying, selling, or
appraising any book.

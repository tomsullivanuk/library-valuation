# Market Validation Findings and Calibration Principles: v0.4.0

## Purpose

This document summarizes the evidence produced by the v0.4.0 Market Validation
work and defines provisional principles for interpreting it before any Research
Assessment model changes are proposed.

It is not a statistical validation paper, an appraisal methodology, or a model
change proposal. Its purpose is to preserve what the experiment currently
supports, identify what remains uncertain, and establish guardrails for later
calibration work.

## Evidence Base

The current evidence comes from a deterministic, stratified sample of 65 books.
The intended target was 100 books, but the catalog distribution could not
support 20 books in every score band:

| Research Score band | Sampled books |
|---|---:|
| `0-1` | 20 |
| `2-3` | 0 |
| `4-5` | 20 |
| `6-7` | 5 |
| `8-10` | 20 |

The AbeBooks spike produced 189 observed listing rows and found at least one
listing for all 65 sampled books. This is complete coverage for this sample and
run, not evidence that AbeBooks will cover the broader catalog consistently.

The PR8 Market Validation Analysis compared score bands and triggered Research
Signals using observation coverage and observed asking-price summaries. The PR9
Research Signal Effectiveness Review then examined seven triggered signals,
signal combinations, sample-relative classifications, and candidate false
positives and false negatives.

All prices in this evidence base are AbeBooks asking prices. They are market
observations, not completed-sale prices, valuation estimates, or appraisals.
The sample size, uneven score distribution, and single-source design materially
limit the strength and generality of any conclusions.

## What the Evidence Supports

The following findings are provisionally and directionally supported:

- The Research Assessment model appears to contain useful market information.
  The highest score band showed the strongest average and maximum observed
  AbeBooks asking-price evidence in this sample.
- The score does not behave as a clean linear gradient. Band medians were not
  monotonic, so higher scores should not be interpreted as proportionally higher
  market value.
- Individual Research Signals differ in apparent usefulness. Some showed more
  consistent asking-price behavior, while others were sparse, noisy, or
  dependent on a few high-priced observations.
- `university_press` and `missing_lcc` met or exceeded the sample median asking
  price in the PR9 descriptive review, making them candidates for further study
  as consistency signals.
- `scholarly_lc_subject` produced a high maximum asking price but a below-sample
  median, suggesting possible upside in particular cases rather than consistent
  market strength.
- False-positive and false-negative candidates exist. These examples provide
  useful diagnostic cases for reviewing signal interactions and possible gaps.

These findings describe this sample and source. They should be treated as leads
for calibration research, not settled properties of the model.

## What the Evidence Does Not Yet Support

The current experiment does not support:

- Appraisal-quality or sale-price valuation.
- Definitive Research Signal weights.
- Automated changes to Research Score calculations.
- Claims of statistical significance or causal relationships.
- Broad conclusions about all rare, collectible, scholarly, or used books.
- Treating AbeBooks as a complete or representative market by itself.
- Treating a maximum asking price as proof that a book possesses that value.
- Assuming complete observation coverage will repeat across other samples,
  sources, or collection dates.

## Median vs Maximum Interpretation

Highly skewed asking prices require different metrics to answer different
questions:

| Metric | Interpretation |
|---|---|
| Median asking price | Consistency or the typical observed market signal |
| Average asking price | Broad price level, but sensitive to outliers |
| Maximum asking price | Possible upside, unusual edition, mismatch, or special case |
| Observation coverage | Whether the source found market evidence for sampled books |
| Sample count | A constraint on the reliability of every comparison |
| False-positive candidates | Possible over-weighted, noisy, or context-dependent signals |
| False-negative candidates | Possible missing signals, underweighted evidence, or special cases |

A high maximum asking price is a lead for bibliographic and market review. It is
not valuation evidence by itself. Edition matching, condition, seller behavior,
listing age, and outlier pricing can all produce a high asking price without a
corresponding realized market value.

## Provisional Signal Interpretation Categories

Later calibration work may use the following descriptive categories:

- `consistent_market_signal`: repeated evidence near or above the sample's
  typical market level, supported by adequate coverage and sample size.
- `upside_market_signal`: evidence of occasional high asking prices without
  consistently elevated typical prices.
- `context_dependent_signal`: usefulness appears conditional on another signal,
  bibliographic attribute, edition, or market context.
- `weak_or_noisy_signal`: observed evidence does not clearly distinguish books
  from the sample baseline.
- `insufficient_sample`: too few books or observations support interpretation.
- `possible_false_positive_driver`: a signal appears frequently in high-score
  books with weak observed market evidence.
- `possible_false_negative_gap`: stronger market evidence appears where the
  current model supplies little or no corresponding Research Signal support.

These labels are analytical vocabulary only. They are not production model
states, score inputs, valuation buckets, or recommendations.

## Calibration Guardrails

Before changing Research Assessment weights or signal definitions, future work
should:

- Review median and maximum asking-price behavior separately.
- Consider signal sample size and observation coverage alongside price metrics.
- Inspect representative false-positive and false-negative books directly.
- Treat sparse signals as unresolved rather than weak or strong.
- Avoid strengthening a signal solely because of one or two maximum prices.
- Preserve the model's explainability and persisted triggered-signal evidence.
- Examine signal combinations as well as isolated signals.
- Check whether apparent findings repeat in another sample or market source when
  feasible.
- Keep observations, analytical interpretations, model changes, and valuation
  estimates as separate architectural concerns.

## Implications for Future Model Calibration

The evidence suggests several directions worth evaluating without selecting a
final change:

- Some signals may eventually warrant higher or lower weights.
- Broad signals may need to be split into more specific bibliographic or market
  contexts.
- Signal combinations may be more informative than individual signals.
- Current score bands may need recalibration because the catalog population is
  concentrated at the high end and leaves one band unused.
- A future model may need to distinguish signals of consistent market evidence
  from signals of unusual upside.
- False-negative examples may reveal missing evidence that the current Research
  Assessment model does not represent.

Any proposal should state the evidence for each change, its expected effect on
score distribution, and how the change would remain explainable. PR10 makes no
specific weight or scoring recommendation.

## Recommended Next Step

The recommended next PR is:

**PR11 — Research Assessment Calibration Proposal**

PR11's proposed refinements, alternatives, and acceptance criteria are recorded
in the [Research Assessment Calibration Proposal](RESEARCH_ASSESSMENT_CALIBRATION_PROPOSAL_v0.4.0.md).
The proposal recommends a before/after simulation before any scoring change is
implemented.

## Expanded Evidence Refresh

PR13 refreshes these findings using 205 sampled books and 596 AbeBooks
observation rows. All 205 books had observations, with no source or diagnostic
failures in the expanded run.

The `8-10` validation band, which contains every raw score of 8 or greater, now
has the strongest median and average asking-price evidence. Score-band medians
remain non-monotonic, however, and all populated bands remain sensitive to high
maximum-price outliers. The low-score band also contains the largest observed
maximum, reinforcing that maxima are investigation leads rather than proof of
value.

Signal conclusions are more stable with two notable changes:

- `multiple_acquisitions` strengthened from weak or inconclusive to moderate.
- `scholarly_lc_subject` strengthened from a possible false-positive driver to
  moderate, while remaining outlier-sensitive.
- `university_press` and `missing_lcc` remain moderate signals.
- `missing_oclc` remains weak, and `low_metadata_confidence` remains a possible
  false-positive driver.
- `specialist_publisher` remains too sparse to classify.

Because PR12 intentionally prioritized sparse signals and combinations, signal
percentages in the expanded sample should not be interpreted as catalog
prevalence. The larger evidence base supports a before/after calibration
simulation, not immediate production scoring changes.

## Non-Goals

This document does not change application code, CLI behavior, generated artifact
schemas, Research Score logic, Research Signal definitions or weights, market
sources, valuation estimates, or value buckets. It creates no durable market or
valuation data.

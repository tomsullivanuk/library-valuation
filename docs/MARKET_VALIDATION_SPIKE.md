# Market Validation Spike

## Purpose

This spike exists to determine whether Research Score contains predictive
information about externally observed market value.

The Research Assessment model is not itself a valuation model. It ranks books by
signals that suggest research priority, ambiguity, scarcity, or potential
collector interest. The v0.4.0 validation question is whether those scores are
also useful evidence for deciding which books are materially more likely to have
meaningful market value.

## Hypothesis

Research Score is positively associated with externally observed market value,
such that books with higher Research Scores are significantly more likely to
possess meaningful market value than books with lower Research Scores.

## Objectives

- Validate the usefulness of the current Research Assessment model.
- Determine whether additional investment in automated valuation is justified.
- Identify strengths and weaknesses of the current scoring model.
- Establish an evidence-based direction for later releases.

## Non-Goals

This spike does not:

- Build a production valuation engine.
- Scrape marketplaces.
- Modify Research Score weights.
- Perform detailed bibliographic research.
- Produce appraisal-quality valuations.

## Experimental Design

Use stratified sampling across Research Score bands so the experiment evaluates
the full scoring range instead of only the most promising books.

Suggested score bands:

- 0-1
- 2-3
- 4-5
- 6-7
- 8-10

Sample approximately 20 books per band, for about 100 books total. The exact
sample size may be adjusted based on the actual catalog distribution. If a band
contains fewer than 20 eligible books, include all available books in that band
and record the limitation in the analysis.

Stratified sampling avoids bias toward only high-scoring books. A top-score-only
sample could show whether some high-scoring books are valuable, but it would not
show whether higher Research Scores are more informative than lower Research
Scores. Sampling across bands allows comparison of market outcomes throughout
the model's range.

## Data to Collect

For each sampled book, collect the following fields in a planning workbook or
temporary research artifact:

- `catalog_id`
- `title`
- `author`
- `ISBN`
- `Research Score`
- `score band`
- `estimated market value`
- `value bucket`
- `valuation source`
- `valuation confidence`
- `notes`

This is a planning document only. It does not define a new durable schema,
change existing data models, or require implementation work.

The v0.4.0 sample-generation command creates the initial input dataset:

```bash
python3 library_pipeline.py generate-market-validation-sample \
  --output-dir output \
  --sample-size-per-band 20 \
  --seed 42
```

It writes `output/market_validation_sample.csv` and
`output/market_validation_sample.xlsx`, targeting 20 books per score band and
100 books total when enough catalog records are available. It also writes
`output/market_validation_sample_metadata.csv` and
`output/market_validation_sample_metadata.xlsx` to preserve target counts,
available population counts, actual sample counts, seed, timestamp, Research
Assessment model version, and configuration hash. These generated artifacts
include catalog identifiers, bibliographic context, Research Score bands, and
triggered Research Signals. They intentionally do not include valuation fields.

The market-observation workflow can then collect a bounded AbeBooks evidence set:

```bash
python3 library_pipeline.py collect-abebooks-observations \
  --output-dir output \
  --limit 100
```

This produces generated `market_observations` artifacts containing observations
or lookup-status rows. These are facts about external lookup attempts, not value
estimates.

The AbeBooks feasibility spike showed that bounded ISBN-first lookup can produce
real observations with title, author, price, currency, condition, seller, URL,
and match-confidence fields. This is enough evidence to keep AbeBooks as a
candidate observation source while treating the parser and source coverage as
experimental. PR7 prepares the analysis-scale dataset for PR8; it does not
perform correlation analysis, estimate value, or change Research Score weights.

Coverage and source-access diagnostics can be summarized with:

```bash
python3 library_pipeline.py report-market-observation-coverage \
  --output-dir output
```

The coverage report shows whether the observation run produced listings, no
results, unavailable-source rows, or no-query rows. It also preserves grouped
diagnostic details and lookup URLs for manual inspection.

PR8 adds the generated analysis command:

```bash
python3 library_pipeline.py analyze-market-validation \
  --output-dir output
```

This produces `output/market_validation_analysis.csv` and
`output/market_validation_analysis.xlsx`. The analysis reports Research Score
distribution, validation dataset characteristics, score-band market indicators,
Research Signal indicators, and relative false-positive/false-negative
candidates. It uses AbeBooks asking prices only as observed market signals.

## Proposed Analysis

Analyze the sampled books using measures that can show whether Research Score
has practical predictive value:

- Observation coverage by score band.
- Median, average, and maximum observed asking price by score band.
- Triggered Research Signal coverage and asking-price summaries.
- Identification of notable relative false positives and false negatives.

Book-market signals are expected to be highly skewed. Later rank-based measures
may be useful because one unusually expensive listing could dominate averages
and make a weak model look stronger than it is. PR8 keeps the first analysis
transparent and descriptive rather than fitting a statistical model.

Initial PR8 findings:

- Current Research Scores are heavily concentrated in the `8-10` band.
- The validation sample has no `2-3` books and only five `6-7` books because the
  catalog population does not contain enough records in those bands.
- AbeBooks observation coverage was complete for the generated sample.
- The `8-10` band showed the highest average and maximum observed asking prices,
  but low-score false-negative candidates also appeared.
- `scholarly_lc_subject` and `university_press` were associated with the
  strongest maximum observed asking prices in this sample.

PR9 reviews why those aggregate patterns appear:

```bash
python3 library_pipeline.py review-research-signal-effectiveness \
  --output-dir output
```

The generated review reports per-signal price distributions and coverage,
sample-relative classifications, common signal combinations, candidate misses,
and calibration notes. Initial results show that maximum prices alone can
overstate a signal's consistency: `scholarly_lc_subject` has a high maximum but
a below-sample median asking price. These findings are diagnostic and do not
change signal definitions or weights.

The combined evidence, limitations, and calibration guardrails are synthesized
in [Market Validation Findings and Calibration Principles](MARKET_VALIDATION_FINDINGS_v0.4.0.md).
That document should guide PR11 proposals before any model change is implemented.
The resulting [Research Assessment Calibration Proposal](RESEARCH_ASSESSMENT_CALIBRATION_PROPOSAL_v0.4.0.md)
recommends simulation of signal-role rebalancing before production scoring is
changed.

PR12 expands the original 65-book sample before that simulation. The deterministic
workflow preserves all original books, targets 140 additional candidates,
balances available score bands, and prioritizes sparse signals and candidate
signal combinations. Exhausted bands remain visible in expanded metadata.

## Success Criteria

Qualitative success means the evidence shows that higher Research Score bands
consistently contain books with stronger observed market signals. In PR8 those
signals are AbeBooks asking prices and observation coverage, not valuation
estimates.

This spike should avoid arbitrary statistical thresholds at this stage. The
first goal is to learn whether the signal is directionally useful enough to
justify follow-on valuation work, and where the current model appears strong or
weak.

## Future Work

Likely follow-on work includes:

- Sample generation.
- Valuation workbook.
- Valuation import.
- Reporting.
- Automated valuation research.
- Model refinement.

# Calibration Scenario Review and Decision: v0.4.0

## Purpose

This document reviews the PR14 Research Assessment calibration simulation and
records the resulting v0.4.0 release decision. It is a decision record, not an
implementation plan, and it does not approve changes to production scoring.

## Evidence Reviewed

The decision uses the full v0.4.0 validation-and-simulation sequence:

- PR11 proposed signal-role rebalancing while requiring simulation before any
  production change.
- PR12 expanded the AbeBooks-backed validation dataset to 205 books and 596
  observation rows, with at least one observation for every sampled book.
- PR13 refreshed score-band, signal-effectiveness, outlier-sensitivity, and
  false-positive/false-negative analysis against the expanded evidence.
- PR14 simulated the persisted baseline, conservative signal-role rebalancing,
  and market-likelihood emphasis across all 205 books.

The evidence remains descriptive and source-limited. AbeBooks asking prices are
market observations, not completed sales, valuation estimates, or appraisals.

## Simulation Results Summary

PR14 produced 615 per-book scenario rows, 75 summary rows, and nine candidate
movement rows across three scenarios:

- **Current persisted baseline:** Preserved the existing production scores and
  bands as the comparison point.
- **Conservative signal-role rebalancing:** Lowered the average score from
  10.99 to 10.12 and the median from 5 to 3. It moved 31 books up, 107 down,
  and eight across production band thresholds.
- **Market-likelihood emphasis:** Raised the average score to 11.17 while
  lowering the median to 1. It moved 61 books up, 77 down, and ten across
  production band thresholds.

Both alternatives changed score distributions, but neither changed top-50
membership. Top-50 median asking price remained $10.20, average asking price
remained $22.13, false-positive references remained at 16, and
outlier-sensitive books remained at six. Each alternative moved three known
false-positive references down, but neither moved a known false-negative
reference up. Band crossings therefore did not produce a demonstrably better
practical candidate set.

## Decision

**Do not implement production Research Assessment scoring changes in v0.4.0.**

The simulated alternatives did not improve top-candidate membership, market
metrics, false-negative surfacing, or false-positive representation. Changing
production weights now would add behavioral and maintenance complexity without
demonstrated benefit. The supporting evidence is also limited to asking prices
from one market source, and the current single score appears to mix market
likelihood with research effort. Current scoring is therefore safer and more
honest to preserve while the conceptual model is reconsidered.

## Interpretation

PR14 supports several conclusions:

- The current Research Assessment contains useful market signal, especially in
  the strongest score band, but it is not a clean linear market-likelihood
  gradient.
- Simple signal reweighting does not resolve the observed candidate problems.
- Metadata-gap signals may usefully identify research work even when they are
  weak indicators of external market interest.
- Market likelihood and research effort may need separate representations.
- Maximum asking prices remain useful investigation leads, but they are not
  proof of realizable value.

The result does not establish that the current weights are optimal. It shows
that the tested replacements have not earned a production change.

## Rejected Options

### Option A: Implement Conservative Rebalancing Now

Rejected because it changed many scores and crossed production bands without
improving top-50 membership or the top candidate market profile.

### Option B: Implement Market-Likelihood Emphasis Now

Rejected because stronger score movement did not improve top-50 membership,
false-negative surfacing, false-positive representation, or market metrics.

### Option C: Continue Tuning Weights in v0.4.0

Deferred because repeated tuning against the same 205-book sample would
increase overfitting risk without adding independent evidence.

### Option D: Add Another Market Source Before Any Decision

Reasonable future work, especially for sold-price evidence, but not required to
close v0.4.0. The release can record the limits of its single-source evidence
without extending the experiment indefinitely.

## Recommended Path

v0.4.0 should stop short of production calibration changes. It should preserve:

- current production Research Assessment scoring;
- current Research Signal definitions and weights;
- current persisted Research Assessments; and
- the existing distinction between observations, analysis, and decisions.

The release should ship its sample generation, market observation, diagnostics,
expanded analysis, signal review, and simulation capabilities as reusable
research infrastructure.

## Future Design Direction

The most promising future direction is to separate market-likelihood and
research-effort concepts, potentially as:

- `market_likelihood_score`: How likely is this book to show meaningful
  external market interest?
- `research_effort_score`: How much manual review, edition resolution, or
  metadata cleanup does this book need?

Equivalent names or a non-score representation may ultimately be preferable.
The important design change is conceptual separation, not the immediate
addition of fields. This is future model-design work and is not approved for
v0.4.0.

## Implications for v0.4.0 Release Scope

v0.4.0 is successful without a production scoring change. It delivered:

- deterministic market validation sampling;
- bounded AbeBooks observation collection and access diagnostics;
- coverage reporting and expanded validation evidence;
- score-band and Research Signal effectiveness analysis;
- calibration findings, principles, and a reviewed proposal;
- before/after scenario simulation; and
- an evidence-based decision not to change scoring prematurely.

Choosing not to ship an unsupported model change is a valid product and
research outcome.

## Recommended v0.5.0 Backlog Items

- Design a market-likelihood and research-effort split.
- Evaluate another market source and investigate completed-sale evidence.
- Improve the candidate review UI or generated workbook.
- Refine calibration scenarios only after independent evidence or a revised
  model design is available.
- Validate model behavior against future monthly imports.
- Revisit score bands after the score's purpose and dimensions are clarified.

## Recommended Next PR

The recommended next PR is:

**PR16 — v0.4.0 Release Readiness Review**

PR16 should verify documentation, generated-artifact policy, commands, tests,
and release scope. It should not reopen production calibration unless new
evidence changes this decision.

## Non-Goals

This decision record does not change scoring logic, configuration, Research
Signals, weights, persisted assessments, commands, simulation scenarios,
market sources, valuation logic, durable data, or generated artifact schemas.

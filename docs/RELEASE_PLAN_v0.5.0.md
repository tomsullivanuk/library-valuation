# Library Valuation v0.5.0 Release Plan

## 1. Release Title and Theme

**v0.5.0 — Market Evidence First**

Version 0.5.0 establishes a market-evidence-first valuation foundation. It does
not produce formal appraisals or claim to determine fair market value.

### Release Objective

Establish a market-evidence-first valuation foundation by aggregating
source-specific market observations into per-book evidence summaries,
classifying evidence quality, and producing cautious asking-price-derived market
ranges and review recommendations without changing durable catalog,
acquisition, or Research Assessment records.

## 2. Background and Motivation

Version 0.4.0 tested whether the existing Research Assessment model could act as
a useful proxy for external market signals. Its expanded validation run included
205 books and produced 596 AbeBooks observation rows. All 205 sampled books had
observations, and the run recorded no source or diagnostic failures.

The experiment supports several conclusions:

- Bounded, ISBN-first AbeBooks collection is feasible in the current
  environment.
- The Research Assessment model appears to contain some useful signal.
- Score-band results remain non-monotonic and sensitive to asking-price
  outliers.
- Two simple calibration scenarios changed scores but did not improve the
  practical top-50 candidate set.
- Production Research Assessment signals, weights, bands, scoring, and
  persisted assessments should remain unchanged.

These results weaken the earlier assumption that market evidence would be
unavailable for most books and therefore had to be predicted primarily through
a Research Score. The new working assumption is:

> Use empirical market lookup where possible. Use Research Signals where market
> evidence is missing, thin, ambiguous, or low-confidence.

The 205-book result is evidence from one intentionally constructed sample and
one source, not proof of stable catalog-wide coverage. Version 0.5.0 therefore
builds a cautious evidence foundation rather than promoting AbeBooks asking
prices into definitive valuation claims.

## 3. Strategic Decision

When sufficiently relevant market evidence is available, it becomes the primary
evidence for an asking-price-derived estimate. Research Score is not the primary
estimate of a book's worth in that case.

The system should answer three separate questions:

| Question | Primary evidence | Proposed output |
| --- | --- | --- |
| What is this book probably worth? | Matched market observations; eventually completed-sale evidence | Conservative market range or asking-price-derived estimate |
| How confident are we? | Source coverage, match confidence, usable listing count, recency, and edition or condition ambiguity | Market confidence with reasons |
| Should a human review it? | Missing or thin evidence, conflicting evidence, metadata gaps, unusual Research Signals, and ambiguity | Review recommendation and fallback research priority |

Research Signals remain useful for fallback research priority, metadata cleanup,
manual-review routing, and explanations of uncertainty. They must not be
presented as observed prices or silently blended into a market estimate.

## 4. Goals

- Define a source-neutral, per-book market evidence summary contract.
- Aggregate factual observations without losing source, match, currency,
  listing, or collection provenance.
- Classify market confidence using explainable evidence-quality rules.
- Prototype conservative market ranges from observed asking-price evidence.
- Separate the market range, confidence, and review recommendation so each can
  change independently and be explained.
- Refresh Research Candidates and the Collector Workbook to foreground market
  evidence when usable and Research Signals when evidence needs review.
- Preserve the monthly Amazon import workflow and all existing durable catalog,
  acquisition, Research Assessment, and Collector Review behavior.
- Keep the work incremental, reviewable, and protected by fixture-driven tests.

## 5. Non-Goals

Version 0.5.0 will not:

- Produce appraisals, fair market value, realized sale prices, pricing
  guarantees, or definitive valuations.
- Claim that an asking price is the price a book can realize in a sale.
- Build an insurance, tax, donation, investment, or dealer-pricing methodology.
- Automatically recommend selling, insuring, donating, or disposing of a book.
- Solve edition, printing, condition, dust-jacket, signature, association-copy,
  or provenance identification comprehensively.
- Make Research Assessment scoring changes merely to fit the v0.4.0 sample.
- Casually rewrite existing persisted Research Assessments.
- Make generated workbooks or market summaries canonical durable data.
- Turn AbeBooks-specific parsing or assumptions into the domain model.
- Require multiple production market sources or completed-sale data to ship the
  foundation, though the design must leave room for both.
- Introduce a database, continuous monitoring, or a web application.

## 6. Terminology

| Term | Meaning in v0.5.0 |
| --- | --- |
| **Market observation** | A factual, source-specific listing or lookup result captured with provenance. It is not an estimate or recommendation. |
| **Observed asking-price evidence** | Asking prices from matched active listings. These prices are seller requests, not completed-sale results. |
| **Market evidence summary** | A derived per-book summary of usable observations, exclusions, match quality, counts, distribution, and ambiguity. |
| **Market confidence** | An explainable classification of how safely the evidence can support an asking-price-derived estimate. It describes evidence quality, not certainty of a future sale. |
| **Conservative market range** | A cautious range derived from usable asking-price evidence after documented filtering and outlier handling. It is not an appraisal or fair market value. |
| **Asking-price-derived estimate** | A derived reference point based on observed asking prices and accompanied by confidence and limitations. |
| **Review recommendation** | An explainable instruction to accept, verify, or investigate evidence; it is separate from estimated price. |
| **Fallback research priority** | The priority assigned when market evidence is absent or inadequate, using Research Signals and evidence gaps. |
| **Research effort score** | A possible future measure of the expected need or benefit of human research. It is distinct from market likelihood and is not introduced as a production score by this plan. |
| **Research Assessment** | The existing durable score, band, signals, and rationale for research prioritization. It remains separate from market evidence and valuation outputs. |

Code, schemas, reports, and user-facing copy should prefer these terms. In
particular, asking-price-derived outputs must not be labeled as appraisals, fair
market value, realized sale prices, or definitive valuations.

## 7. Target Architecture

```text
Durable Catalog Item
        |
        v
Market Evidence Collection
  source adapters + factual observations + lookup diagnostics
        |
        v
Market Evidence Summary
  usable/excluded observations + provenance + distribution + ambiguity
        |
        v
Market Confidence
  coverage + match quality + listing count + edition/condition uncertainty
        |
        v
Conservative Market Range
  cautious asking-price-derived output + method/version + limitations
        |
        v
Review Recommendation
  accept / verify / investigate + reason codes + fallback research priority
        |
        v
Research Candidates and Collector Workbook
  generated, collector-facing views
```

### Layer Boundaries

1. **Catalog Item** supplies stable identity and bibliographic context. Market
   work references `catalog_item_id`; it does not redefine catalog identity.
2. **Market Evidence Collection** records source facts and diagnostics.
   AbeBooks lookup, parsing, and source-specific normalization remain behind an
   adapter boundary.
3. **Market Evidence Summary** groups observations per catalog item, records
   inclusion and exclusion reasons, and preserves enough provenance to audit the
   result.
4. **Market Confidence** evaluates the evidence independently of the estimated
   price. Confidence rules must expose reason codes and relevant counts.
5. **Conservative Market Range** consumes only eligible evidence under a
   versioned, documented method. Research Score must not be used as a hidden
   price input.
6. **Review Recommendation** combines evidence gaps, ambiguity, conflicting
   evidence, metadata gaps, and Research Signals to direct human attention.
7. **Collector Outputs** render the derived results. They remain reproducible
   artifacts rather than sources of truth.

### Data-Lifecycle Constraints

- Preserve monthly Amazon import behavior.
- Preserve durable catalog and acquisition data and stable
  `catalog_item_id` values.
- Do not casually rewrite existing Research Assessments; any future migration
  or reassessment requires an explicit design and user-controlled workflow.
- Keep generated market artifacts under `output/` and separate from durable
  data unless a later PR explicitly designs, versions, and migrates a durable
  market repository.
- Maintain explainability through source references, method versions, reason
  codes, observation counts, exclusion reasons, and uncertainty notes.
- Keep source-specific AbeBooks collection and parsing logic isolated from
  source-neutral evidence, confidence, range, and recommendation contracts.
- Avoid overfitting thresholds or range rules to the v0.4.0 validation sample.
- Continue using incremental, reviewable PRs.

## 8. Proposed Generated Artifacts

Names are provisional until PR2 defines schemas and compatibility rules.

| Artifact | Purpose |
| --- | --- |
| `output/market_evidence_summaries.csv` / `.xlsx` | One source-neutral evidence summary per catalog item, including usable and excluded counts, price statistics, source coverage, match quality, and ambiguity flags. |
| `output/market_confidence.csv` / `.xlsx` | Confidence classification, reason codes, rule/method version, and supporting measures. This may be folded into the summary artifact if the boundary remains explicit. |
| `output/conservative_market_ranges.csv` / `.xlsx` | Asking-price-derived low/reference/high outputs, currency, method version, evidence cutoff, confidence, and limitations. |
| `output/review_recommendations.csv` / `.xlsx` | Review disposition, reasons, fallback research priority, and evidence or metadata gaps. |
| `output/research_candidates.csv` / `.xlsx` | Refreshed generated candidate view that distinguishes market evidence from fallback Research Signals. |
| `output/collector_workbook.xlsx` | Refreshed collector-facing workbook with market summary, confidence, range, and review context kept visibly distinct. |

Existing observation artifacts may remain inputs while their replacement or
generalization is designed. Generated outputs must identify their generation
time and applicable schema or method version, and must not be read back as
durable truth by the monthly workflow.

## 9. Proposed PR Sequence

Implementation status: PR1 through PR6 are complete. PR7 aligns release-facing
documentation and records final acceptance evidence. The implemented summary
model version is `0.5.0-pr6`; no durable schema or monthly-import change was
introduced.

### PR1 — Market-Evidence-First Design Brief

Status: complete.

Create this release plan and establish terminology, scope, boundaries, risks,
and sequencing. No application behavior or durable schema changes.

### PR2 — Market Evidence Summary Schema

Status: complete.

Define the source-neutral contracts for evidence summaries, provenance,
exclusions, ambiguity, confidence inputs, currencies, and method versions.
Decide whether v0.5.0 artifacts remain wholly generated or whether any durable
observation repository is justified; no persistence change should occur by
accident.

### PR3 — Market Evidence Aggregation

Status: complete.

Aggregate source-specific observations into deterministic per-book summaries.
Preserve raw evidence references, reject or flag incompatible observations, and
isolate AbeBooks-specific behavior behind the source boundary.

### PR4 — Market Confidence Classification

Status: complete.

Introduce explainable confidence levels and reason codes based on match quality,
usable listing count, source coverage, and known ambiguity. Confidence should be
testable independently from price calculations.

### PR5 — Conservative Market Range Prototype

Status: complete.

Produce a cautious, versioned asking-price-derived range for evidence that meets
explicit eligibility rules. Show exclusions, currency assumptions, sample size,
outlier handling, confidence, and limitations; route inadequate evidence to
review instead of manufacturing precision.

### PR6 — Research Candidate / Collector Workbook Refresh

Status: complete in the generated Market Evidence Summary. The existing monthly
Collector Workbook generator remains unchanged.

Update generated collector outputs so market range, market confidence, and
review recommendation are distinct. Use Research Signals as fallback and review
context rather than a substitute price when usable market evidence exists.

### PR7 — Documentation, Release Notes, and Acceptance Test Refresh

Status: in release-readiness review.

Align architecture, roadmap, backlog, README, release notes, and release
checklist with the implemented behavior, then complete acceptance testing. PR7
may be folded into PR6 if the implementation and documentation changes remain
small and reviewable; keep it separate if doing so makes final terminology,
limitations, or acceptance evidence easier to audit.

Each PR should preserve the monthly workflow and durable state, include tests
proportional to its behavior, and avoid pulling later-PR decisions forward
without review.

## 10. Acceptance Criteria

Version 0.5.0 is ready when:

- The standard monthly Amazon import behaves as it did in v0.4.0 and preserves
  durable catalog, acquisition, Research Assessment, and Collector Review data.
- Source-specific observations can be aggregated deterministically into a
  per-book, source-neutral market evidence summary.
- Each included or excluded observation remains auditable through provenance
  and explicit reason fields.
- Market confidence is produced separately from price and includes explainable
  reasons based on match quality, counts, coverage, and ambiguity.
- Eligible books receive a cautious conservative market range with currency,
  observation count, evidence date/cutoff, method version, and limitations.
- Missing, thin, conflicting, ambiguous, or low-confidence evidence produces an
  explicit review recommendation rather than false precision.
- Research Signals support fallback research priority and review explanations
  without being presented as observed market prices.
- AbeBooks-specific logic remains isolated from source-neutral aggregation,
  confidence, range, and recommendation interfaces.
- Generated market artifacts remain separate from durable data unless an
  explicit reviewed persistence design says otherwise.
- Collector-facing artifacts clearly distinguish observed asking-price
  evidence, derived ranges, confidence, and recommendations.
- Documentation never labels asking-price-derived outputs as appraisals, fair
  market value, realized sale prices, or definitive valuations.
- Tests cover empty evidence, one-listing and small-listing cases, outliers,
  duplicate observations, mismatches, ambiguous editions, mixed currencies,
  source failures, and deterministic regeneration.
- Thresholds and rules are evaluated beyond the v0.4.0 sample where feasible,
  or their sample limitations are documented explicitly.
- Release documentation and acceptance evidence agree with actual behavior.

## 11. Architectural Risks and Mitigations

| Risk | Mitigation |
| --- | --- |
| AbeBooks coverage creates false confidence. | Treat coverage as sample- and run-specific; report lookup coverage separately from match quality and evidence confidence; retain diagnostics and add other sources when feasible. |
| Asking prices overstate realizable value. | Label them as observed asking-price evidence; use cautious statistics and limitations; avoid sale-price language; add completed-sale evidence as a distinct future evidence type. |
| Edition, printing, condition, jacket, signature, or provenance ambiguity distorts estimates. | Preserve listing text and match evidence, add explicit ambiguity flags and exclusions, lower confidence, and route material uncertainty to human review. |
| Small listing counts are outlier-sensitive. | Define minimum evidence rules, show counts and robust statistics, cap confidence, avoid range generation when evidence is inadequate, and test pathological distributions. |
| AbeBooks assumptions leak into source-neutral architecture. | Use source adapters and normalized contracts; prohibit AbeBooks fields from becoming core domain requirements; test aggregation with source-neutral fixtures and a second-source-shaped fixture. |
| Generated artifacts are mistaken for durable data. | Keep them under `output/`, label generation and method versions, document regeneration, and ensure the monthly pipeline never reads them as canonical input. |
| Research Assessment terminology becomes confusing after the pivot. | Reserve Research Assessment for the existing research-priority model; consistently name market evidence, confidence, range, review recommendation, and fallback research priority as separate concepts. |
| The release attempts formal valuation or appraisal too soon. | Enforce non-goals and PR boundaries; ship an asking-price evidence foundation; defer formal appraisal, completed-sale modeling, and automated decisions. |
| Rules overfit the 205-book validation sample. | Use the sample for regression and design evidence, not universal threshold tuning; test synthetic edge cases and future monthly cohorts; version methods and record limitations. |
| Currency, shipping, taxes, duplicates, stale listings, or source changes corrupt comparisons. | Preserve raw values and currency; avoid silent conversion; define shipping and duplicate policies; record collection time; fail visibly when source parsing changes. |
| A derived estimate becomes irreproducible after rules change. | Record schema, aggregation, confidence, and range method versions plus evidence cutoff and source references in generated rows. |

## 12. Open Questions

- What minimum usable listing count should permit a range, and how should the
  threshold vary with match quality or price dispersion?
- Should market confidence use named levels, reason codes, or both, and what
  wording avoids implying sale certainty?
- Which robust statistics and outlier rules best support a conservative range
  for small samples?
- Should shipping be excluded, included, or reported separately when sources
  expose it inconsistently?
- How should mixed currencies be handled: exclude, partition, or convert using
  a dated and reproducible exchange-rate source?
- What constitutes a duplicate listing across collection runs, sellers, and
  sources?
- How should listing age and observation freshness affect confidence?
- Which edition, binding, condition, jacket, signature, and provenance fields
  can be normalized reliably, and which must remain review flags?
- Should confidence and range live in separate generated artifacts or one
  denormalized collector-facing artifact backed by separate internal models?
- Are raw market observations ready to become durable historical evidence, or
  should all v0.5.0 market outputs remain generated until retention, refresh,
  licensing, and migration policies are designed?
- Which second source or completed-sale source would most effectively test the
  source-neutral boundary after AbeBooks?
- How should the existing Research Candidates ordering combine review urgency,
  fallback research priority, market confidence, and possible upside without
  collapsing them into another opaque score?
- Should `research effort score` become a formal future model, or are explicit
  review reason codes and ordering rules sufficient?

These questions should be resolved in the PR where they first affect a schema or
observable behavior. Decisions should be documented with alternatives,
limitations, and migration impact rather than embedded silently in code.

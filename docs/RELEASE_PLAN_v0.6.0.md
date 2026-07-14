# Library Valuation v0.6.0 Release Plan

## 1. Release Title and Theme

**v0.6.0 — Multi-Source Market Evidence**

Version 0.6.0 expands the market-evidence-first foundation beyond AbeBooks. It
does not produce formal appraisals, claim fair market value, or assume that all
external signals are interchangeable.

### Release Objective

Expand the market-evidence-first foundation beyond AbeBooks by evaluating
low-friction market sources, integrating the easiest useful additional source
through a source-adapter pattern, and updating generated Market Evidence
Summaries to distinguish single-source evidence, source diversity, and
cross-source agreement or conflict without changing durable catalog,
acquisition, or Research Assessment records.

## 2. Background From v0.5.0

Version 0.5.0 established the following generated, source-neutral pipeline:

```text
Raw market observations
        |
        v
Market Evidence Summary
        |
        v
Evidence availability and status
        |
        v
Market confidence and outlier sensitivity
        |
        v
Conservative asking-price-derived range
        |
        v
Review recommendation or fallback research priority
```

The release made observed market evidence primary when it is usable and kept
Research Signals as fallback, uncertainty, metadata-cleanup, and
review-prioritization context. It also preserved important boundaries:

- Market Evidence Summaries are generated artifacts, not durable records.
- Asking-price-derived ranges are not appraisals or realized-sale estimates.
- Production Research Assessment signals, weights, bands, scoring, and
  persisted assessments did not change.
- Monthly Amazon import behavior did not change.
- AbeBooks lookup and parsing remained isolated from source-neutral summary
  logic.

That foundation can already count distinct sources, but the implemented
confidence and range rules have only been exercised with AbeBooks evidence.
Version 0.6.0 should add source diversity before those rules are tuned further.

## 3. Empirical Finding From the Expanded Summary Review

After v0.5.0, the summary workflow was run against the expanded v0.4.0
observation set:

```text
input:  output/expanded_market_observations.csv
output: output/expanded_market_evidence_summary.csv/.xlsx
rows:   205 Market Evidence Summary rows
```

The workbook behaved coherently, but every market observation came from
AbeBooks. The review therefore demonstrates that the transformation works for
one source; it does not demonstrate independent corroboration, source diversity,
or stable behavior when sources disagree.

AbeBooks remains useful observed asking-price evidence. Its broad coverage in
this sample must not be interpreted as complete market coverage or allowed to
create false confidence. In particular, one marketplace cannot answer whether
other active listings, sold/completed evidence, retail/list-price signals, or
availability signals confirm or challenge its results.

## 4. Strategic Decision: Expand Beyond AbeBooks

Version 0.6.0 will use **easiest reliable integration first** as its source
selection principle. The release will begin with a bounded empirical spike,
select one useful low-friction source, and integrate that source behind an
adapter boundary. It will not select a source solely because it is theoretically
ideal, nor attempt several production integrations at once.

The primary product question is:

> Does broader market evidence confirm or challenge the AbeBooks signal?

The answer must preserve evidence-type distinctions. A metadata/availability
signal can strengthen identity or show discoverability, but it cannot confirm an
asking-price range. A retail/list-price signal is not a used-market asking price.
Sold/completed evidence may better reflect market-clearing behavior, but it is
still not a formal appraisal and may have access or matching limitations.

If the easiest reliable source is metadata-only, v0.6.0 may integrate it as
metadata/availability support while continuing the search for a second price
source. The release must not claim multi-source price agreement merely because
two different kinds of evidence exist.

## 5. Goals

- Evaluate candidate sources empirically for access practicality, reliability,
  evidence value, and schema fit.
- Select and integrate the easiest useful additional source through a
  source-specific adapter.
- Normalize source output into a source-neutral observation contract without
  erasing source provenance or evidence type.
- Distinguish single-source evidence from genuine source diversity.
- Summarize cross-source agreement, conflict, and non-comparability with
  explainable reasons.
- Distinguish asking-price, sold/completed, retail/list-price,
  metadata/availability, and other signals before aggregation.
- Update market confidence so source diversity can add information without
  automatically or mechanically increasing confidence.
- Preserve cautious range behavior and prevent incompatible evidence types or
  currencies from being averaged blindly.
- Keep generated artifacts reproducible, versioned, auditable, and separate
  from durable project data.
- Continue incremental, reviewable PRs with fixture-driven tests.

## 6. Non-Goals

Version 0.6.0 will not:

- Produce an appraisal, fair market value, realized sale price estimate,
  definitive valuation, pricing guarantee, or guaranteed sale proceeds.
- Integrate every candidate source or require an ideal sold/completed source to
  ship.
- Treat metadata, availability, retail/list price, active asking price, and
  sold/completed evidence as equivalent.
- Tune recommendation or range thresholds prematurely against the AbeBooks-only
  validation sample.
- Rewrite existing Research Assessments or change Research Signal scoring,
  weights, bands, or production configuration.
- Change monthly Amazon import behavior, durable catalog or acquisition data,
  or Collector Review records.
- Make generated market artifacts durable by accident or introduce a database.
- Solve edition, printing, condition, dust-jacket, signature, association-copy,
  or provenance matching comprehensively.
- Build a generic scraping platform, continuous market monitor, or broad
  marketplace crawler.
- Make source availability a hard production dependency for the monthly
  workflow.
- Hard-code AbeBooks or the newly selected source into source-neutral
  confidence, range, or recommendation rules.

## 7. Terminology

| Term | Meaning in v0.6.0 |
| --- | --- |
| **Market source adapter** | Source-specific lookup, parsing, diagnostics, and initial normalization behind a stable boundary. |
| **Market observation** | A factual, source-specific result captured with source, evidence type, lookup, match, collection, and raw-reference provenance. |
| **Observed asking-price evidence** | Seller asking prices from matched active listings; these are not completed-sale results. |
| **Sold/completed listing evidence** | A recorded price or status associated with a completed marketplace listing, subject to source and match limitations; it is not a formal appraisal. |
| **Retail/list-price signal** | A current or stated retail/list price that supplies context but is not automatically comparable to secondary-market asking or sold evidence. |
| **Metadata/availability signal** | Evidence about identity, discoverability, edition metadata, or availability without a directly comparable market price. |
| **Evidence type** | The semantic category of an observation, such as `asking_price`, `sold_price`, `retail_price`, `availability`, or `metadata_only`. |
| **Source diversity** | The number and composition of independent sources contributing usable evidence, reported by evidence type. It is not automatically a confidence increase. |
| **Cross-source agreement** | Comparable observations from independent sources that are directionally consistent under a documented rule. |
| **Cross-source conflict** | Comparable observations from independent sources that materially differ or imply incompatible conclusions under a documented rule. |
| **Non-comparable evidence** | Observations that must not be compared directly because evidence type, currency, match quality, edition, condition, timing, or another material property differs. |
| **Market Evidence Summary** | A generated per-book summary of source coverage, usable and excluded evidence, evidence-type composition, distributions, ambiguity, agreement, and conflict. |
| **Market confidence** | An explainable classification of evidence quality and usability, not certainty of a future sale or a book's value. |
| **Conservative market range** | A cautious range derived only from eligible, comparable price evidence under a documented method. |
| **Asking-price-derived estimate** | A derived reference based on observed asking prices and accompanied by source, confidence, and limitation context. |
| **Review recommendation** | An explainable next action for accepting, verifying, or investigating evidence. |
| **Fallback research priority** | Existing Research Assessment priority exposed when market evidence is absent or inadequate; it is not a price input. |

Code, schemas, docs, and user-facing outputs should prefer these terms. They
must avoid labeling outputs as appraisals, fair market value, realized sale
price estimates, or definitive valuations.

## 8. Source Evaluation Criteria

PR2 should compare a small, plausible candidate set rather than exhaustively
research every marketplace. Initial candidates may include Google Books, eBay
active listings, eBay sold/completed listings, Biblio, BookFinder, ViaLibri,
Alibris, Amazon used/list-price signals, and other low-friction public or
semi-public sources.

Each candidate should be assessed with recorded evidence under these criteria:

| Area | Questions to answer |
| --- | --- |
| Evidence type | Does the source provide asking price, sold price, retail price, availability, metadata only, or more than one clearly distinguishable type? |
| Integration mode | Is access through a public API, authenticated API, web-page parsing, manual/exported input, or a third-party service? |
| Lookup support | Does it support ISBN, title/author, and a controlled fallback search? |
| Authentication and cost | Are an account, API key, approval, paid plan, or per-query fees required? |
| Operational constraints | What rate limits, quotas, terms, robots guidance, licensing restrictions, geographic constraints, or retention rules apply? |
| Reliability | Is the endpoint stable, documented, consistently structured, and testable? Is HTML brittle or client-rendered? |
| Price detail | Are price, currency, shipping, sale status, and sold/completed date available and semantically clear? |
| Listing detail | Are seller, condition, edition, binding, listing URL, and availability exposed? |
| Match quality | Can ISBN or metadata support a confidence classification? Can false matches be retained or rejected visibly? |
| Schema fit | Can the result become a market observation row? Which source-neutral fields are missing, and which extensions are justified? |
| Testability | Can deterministic fixtures be captured lawfully without making routine tests depend on live network access? |
| Failure behavior | Can rate limits, unavailable sources, no results, parse changes, and partial responses be distinguished? |
| Maintenance burden | How likely is the integration to require frequent repairs or manual credentials? |

The spike should recommend a source using an explicit decision record. Access
practicality and reliability are the first filter; evidence usefulness and
architectural fit break ties. A source that cannot be used consistently and
appropriately should not be selected merely because its data would be valuable.

## 9. Target Architecture

```text
Durable Catalog Item
        |
        v
Market Source Adapters
  isolated lookup + parsing + diagnostics
        |
        v
Source-Specific Observation Rows
  raw source semantics + provenance
        |
        v
Source-Neutral Market Observations
  normalized evidence type + match + currency + status
        |
        v
Generated Market Evidence Summary
  source coverage + evidence-type composition + comparable groups
        |
        v
Cross-Source Agreement / Conflict
  agreement + conflict + non-comparability + reasons
        |
        v
Market Confidence
  quality + diversity + ambiguity + fragility
        |
        v
Conservative Market Range
  eligible comparable price evidence only
        |
        v
Review Recommendation
  verify / investigate / fallback research priority
```

### Layer Boundaries

1. **Catalog Item** supplies identity and bibliographic context without being
   reshaped around any marketplace.
2. **Source Adapters** own authentication, lookup syntax, rate limiting,
   source-specific parsing, raw fields, and diagnostic mapping. AbeBooks and the
   new source must remain separate adapters.
3. **Source-Specific Rows** retain enough raw semantics and references to audit
   what each source actually returned.
4. **Source-Neutral Observations** express common concepts without pretending
   all source fields have direct equivalents. Unsupported fields remain blank
   or source-specific; their absence must not be guessed.
5. **Market Evidence Summary** groups by catalog item and evidence type,
   preserves per-source counts, and identifies eligible comparable groups.
6. **Agreement / Conflict** compares only eligible groups and exposes method
   versions, reason codes, supporting sources, and non-comparability reasons.
7. **Market Confidence** consumes source-neutral measures. No source name may
   directly grant confidence; diversity is one input alongside match quality,
   evidence type, sample size, dispersion, currency, and ambiguity.
8. **Conservative Market Range** must not average incompatible evidence types,
   editions, conditions, or currencies. Asking and sold evidence remain
   separately visible even if a later method uses both.
9. **Review Recommendation** treats conflict as actionable information rather
   than hiding it in a blended midpoint.

### Data-Lifecycle Constraints

- Preserve monthly Amazon import behavior.
- Preserve durable catalog and acquisition data and stable identifiers.
- Do not rewrite existing Research Assessments or change Research Signal
  scoring, weights, or bands.
- Keep generated market artifacts separate from durable data unless a later,
  explicit design addresses retention, licensing, refresh, migration, and
  deletion.
- Maintain explainability through source references, collection timestamps,
  evidence types, match confidence, exclusions, reason codes, and method
  versions.
- Keep AbeBooks logic isolated and keep every new source's logic isolated.
- Do not hard-code a new source into source-neutral confidence, range, or
  recommendation logic.
- Avoid overfitting to the v0.4.0/v0.5.0 validation sample.
- Avoid tuning recommendation thresholds before source breadth improves.
- Respect source access constraints, rate limits, terms, licensing, and data
  retention requirements.
- Keep live network access outside deterministic unit tests.
- Continue incremental, reviewable PRs.

## 10. Proposed Generated Artifacts and Schema Implications

Names and exact columns remain provisional until the spike and schema PRs.

| Artifact | Purpose |
| --- | --- |
| `output/source_integration_spike.md` | Generated or checked-in spike evidence, candidate comparison, access findings, prototype results, and recommendation. The PR should decide the appropriate location for the durable decision record. |
| `output/<source>_market_observations.csv` / `.xlsx` | Optional source-specific diagnostic output retaining the selected source's raw semantics. |
| `output/market_observations.csv` / `.xlsx` | Normalized, source-neutral observations from one or more adapters, with provenance and evidence type. |
| `output/market_evidence_summary.csv` / `.xlsx` | Extended per-book summary with source diversity, evidence-type composition, and cross-source agreement, conflict, or non-comparability. |

All runtime artifacts under `output/` remain generated and non-durable. A spike
decision brief may instead belong under `docs/` if it must be retained in
version control.

### Observation Schema Implications

PR2 and PR4 should inspect the implemented observation fields before changing
them. Likely source-neutral additions or clarifications include:

- a canonical `evidence_type` that distinguishes asking price, sold price,
  retail price, availability, and metadata-only evidence;
- source-native listing or result identifiers for deduplication and audit;
- explicit listing status and sold/completed date where available;
- separate item price, shipping price, and currency fields without inferred
  totals;
- collection timestamp, lookup strategy, query value, and adapter/schema
  version;
- source URL or raw reference subject to source terms;
- normalized match confidence plus edition, condition, binding, jacket,
  signature, and provenance ambiguity flags where supported;
- stable status rows for no result, no usable query, authentication failure,
  rate limit, source unavailable, and parse failure.

Source-specific fields should not be promoted into the common contract unless
another layer needs their semantics. Lossless raw payload retention is not an
automatic goal; terms, privacy, size, stability, and reproducibility must be
considered explicitly.

### Summary Schema Implications

Likely extensions include:

- source counts overall and by evidence type;
- stable source names and usable-observation counts by source;
- `source_diversity_status`, distinguishing single source, multiple comparable
  sources, multiple non-comparable sources, and no usable sources;
- separate asking-price, sold-price, retail-price, and availability measures;
- sources included in each comparable group;
- `cross_source_status`, distinguishing agreement, conflict, insufficient
  comparable evidence, and not applicable;
- agreement/conflict reason codes, method version, and supporting dispersion or
  overlap measures;
- explicit exclusions and non-comparability reasons;
- confidence reason codes that explain the effect of diversity or conflict.

Wide per-evidence-type columns may be acceptable for the generated collector
summary, but the internal model should remain structured so adding another
evidence type does not require source-specific aggregation branches. Existing
v0.5.0 field compatibility, ordering, and version behavior must be decided
explicitly rather than changed silently.

## 11. Proposed PR Sequence

### PR1 — Multi-Source Market Evidence Design Brief

Create this release plan and establish objective, terminology, boundaries,
evaluation criteria, architecture, sequencing, risks, and acceptance criteria.
Documentation only; no production behavior or durable schema changes.

### PR2 — Bounded Source Integration Spike

Empirically answer:

> Which source can we reliably query, parse, normalize, and test with the least
> operational complexity?

Compare a bounded candidate set using representative ISBN and title/author
queries, document access and terms constraints, and build only the smallest
prototypes needed to test assumptions. Recommend one of:

- integrate a second price-evidence source;
- integrate a metadata/availability source with accurately limited claims;
- use a manual/exported observation path when automated access is impractical;
- defer integration if no source meets minimum reliability and appropriateness.

PR2 must not wire a source into the production workflow unless the path is
exceptionally straightforward and keeping it in the spike improves reviewability.

### PR3 — Add the Easiest Useful Second Source Adapter

Implement the selected source behind an isolated adapter with bounded queries,
rate-limit handling, failure diagnostics, captured fixtures, and clear evidence
semantics. Keep it opt-in and independent of the monthly Amazon import. If PR2
selects metadata-only evidence, name and test the adapter accordingly; do not
present it as a second market-price source.

### PR4 — Normalize the Multi-Source Observation Schema

Define or extend the source-neutral observation contract, normalize AbeBooks
and the new adapter through the same boundary, preserve evidence type and
provenance, and establish compatibility/version rules. Include synthetic
second-source fixtures even if live access is unavailable in tests.

PR3 and PR4 may be reversed if the spike shows that a contract change is needed
before the adapter can be implemented cleanly. That decision should be recorded
in PR2.

### PR5 — Cross-Source Agreement / Conflict Summary

Extend the generated Market Evidence Summary to report source diversity,
evidence-type composition, comparable groups, agreement, conflict, and
non-comparability. Keep each source's contribution auditable. Prefer explicit
conflict over a misleading averaged range.

### PR6 — Update Market Confidence for Source Diversity

Make confidence consume source-neutral diversity and conflict measures.
Multiple sources must not automatically raise confidence: weak matches,
duplicated/meta-search listings, incompatible evidence types, mixed currencies,
or material conflict may leave confidence unchanged or reduce it. Avoid broad
threshold retuning in this release.

### PR7 — Documentation, Release Notes, and Acceptance Test Refresh

Align README, architecture, data model, Market Intelligence, roadmap, backlog,
release notes, readiness evidence, and checklist with implemented behavior. Run
acceptance tests across single-source, multi-source agreement, multi-source
conflict, non-comparable evidence, source failure, and compatibility cases.

Each PR should preserve generated/durable boundaries, remain independently
reviewable, and include tests proportional to behavior.

## 12. Acceptance Criteria

Version 0.6.0 is ready when:

- The source spike records a reproducible candidate comparison and a justified
  easiest-useful-source decision.
- At least one additional useful source or explicit manual/exported source path
  is integrated through an isolated adapter. If it is metadata-only, all docs
  and outputs state that limitation and do not claim price corroboration.
- AbeBooks and the added source can produce source-neutral observation rows
  without source-specific logic leaking into aggregation.
- Every observation preserves source, evidence type, lookup and collection
  provenance, match context, and applicable price/status semantics.
- Generated summaries distinguish single-source evidence, multiple comparable
  sources, multiple non-comparable sources, and absent usable evidence.
- Comparable cross-source evidence receives an explainable agreement or
  conflict status with stable reasons and a method version.
- Incompatible evidence types, mixed currencies, and materially ambiguous
  matches are not silently combined.
- Market confidence remains separate from price, exposes reasons, and does not
  increase merely because a second source exists.
- Conservative ranges use only documented eligible evidence and retain clear
  asking-price, sold/completed, and retail/list-price distinctions.
- Conflicting evidence produces visible review guidance rather than false
  precision.
- Source unavailability, rate limits, authentication failures, no results, and
  parse failures are visible and do not corrupt other source results.
- Deterministic tests do not require live network access and cover source
  agreement, conflict, duplication, non-comparability, and source failure.
- The standard monthly Amazon import behaves as it did in v0.5.0.
- Durable catalog, acquisition, Research Assessment, and Collector Review data
  remain unchanged.
- Production Research Signal scoring, weights, bands, and configuration remain
  unchanged.
- Generated market artifacts remain separate from durable data.
- Documentation uses non-appraisal terminology consistently and agrees with
  actual implementation.
- Source access, rate limits, terms, licensing, and retention constraints are
  documented and respected.

## 13. Architectural Risks and Mitigations

| Risk | Mitigation |
| --- | --- |
| Single-source evidence creates false confidence. | Report source diversity explicitly, cap claims for one-source evidence, and avoid treating listing volume from one marketplace as independent corroboration. |
| Additional sources return noisy or conflicting matches. | Prefer ISBN-first lookup, preserve match confidence and raw references, keep rejected evidence visible, and route material ambiguity or conflict to review. |
| Sold/completed evidence is difficult to access reliably. | Evaluate access empirically, respect authentication and terms, support a bounded manual/export path if appropriate, and do not make sold evidence a release prerequisite. |
| Scraping is brittle or inappropriate. | Prefer documented APIs and exports; review terms and robots guidance; isolate parsers; use fixtures and parse-failure diagnostics; reject sources whose access is not appropriate or maintainable. |
| API authentication adds operational friction. | Score credentials, approval, quotas, cost, secret handling, and renewal in the spike; keep optional adapters out of the monthly workflow; document setup and failure behavior. |
| Different evidence types are mixed blindly. | Require canonical evidence types, group comparable evidence before statistics, preserve separate measures, and make non-comparability explicit. |
| Currencies differ across sources. | Preserve original currency, partition comparisons by currency, and do not convert without a dated, reproducible, explicitly designed method. |
| Edition, condition, jacket, signature, and provenance ambiguity remains material. | Retain available listing detail and ambiguity flags, lower match confidence, exclude weak comparables, and recommend human review. |
| Cross-source averaging hides important disagreement. | Make conflict a first-class output, show source-specific measures, and suppress or qualify ranges when disagreement is material. |
| Meta-search sources duplicate underlying marketplace listings. | Capture origin and stable identifiers where possible, define within- and cross-source deduplication rules, and do not count duplicated listings as independent diversity. |
| Source-specific parsing leaks into source-neutral aggregation. | Enforce adapter contracts, normalize before aggregation, prohibit source-name branches in confidence/range logic, and test the same rules with multiple source fixtures. |
| A second source is present but adds no independent price evidence. | Report diversity by evidence type and use metadata/availability only for the claims it supports. |
| Live source changes make results or tests irreproducible. | Use captured lawful fixtures for deterministic tests, version adapters and summary methods, timestamp live collections, and report source failures explicitly. |
| The release becomes too ambitious. | Select one integration path, bound lookup and schema changes, defer additional adapters, and keep PRs decision-gated and independently reviewable. |
| Rules overfit the 205-row expanded sample. | Use that sample as regression evidence only, add synthetic conflict and edge cases, evaluate future cohorts, and avoid threshold tuning until source breadth improves. |
| Generated evidence becomes accidental durable state. | Keep artifacts under `output/`, prevent monthly workflows from reading them as truth, and require a separate reviewed design for history, licensing, refresh, and migration. |

## 14. Open Questions

- Which candidates provide lawful, stable, low-cost access in the current
  environment, and which require credentials or approval?
- What minimum result quality and operational reliability must a source meet to
  be selected by PR2?
- If the easiest source is Google Books or another metadata-oriented API, is
  metadata/availability support sufficient for v0.6.0, or should the release
  also require a manual/exported price-evidence path?
- Can eBay active or sold/completed evidence be accessed reliably at the scale
  and cadence this project needs?
- Do BookFinder, ViaLibri, Biblio, Alibris, or other meta-search results expose
  stable, appropriately accessible data, and can underlying duplicates be
  identified?
- Should the normalized contract use one `evidence_type` field, retain the
  existing `observation_type`, or introduce a compatibility mapping?
- How should active, sold, unsold, unavailable, and unknown listing statuses be
  represented consistently?
- What constitutes an independent source when a meta-search result originates
  from a marketplace already collected directly?
- Which observations are comparable across sources, and which edition,
  condition, date, shipping, or seller differences require partitioning?
- What transparent method should classify agreement or conflict for small,
  skewed samples without inventing statistical precision?
- Should conflict suppress a range, lower confidence, widen review guidance, or
  some combination of these?
- How should sold/completed evidence influence a range while remaining visibly
  separate from asking-price evidence?
- Should metadata/availability signals affect match confidence, market
  confidence, review recommendations, or only contextual fields?
- How should cross-source duplicates and repeated collection runs be detected?
- Should existing v0.5.0 summary columns remain stable with additive fields, or
  should v0.6.0 introduce an explicitly versioned replacement schema?
- What source response data may be retained in fixtures or generated artifacts
  under applicable terms and licensing constraints?
- When, if ever, should observations become durable historical evidence rather
  than generated artifacts?

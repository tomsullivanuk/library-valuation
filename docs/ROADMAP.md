# Roadmap

This roadmap translates the project vision and architecture into incremental
implementation work. The intent is to grow from the current Amazon/Open Library
catalog pipeline into a reproducible valuation and decision-support system
without losing the source-of-truth discipline described in the architecture.

## Sprint 0: Completed Setup

Sprint 0 established the project foundation.

Completed outcomes:

- Repository created for the Library Valuation project.
- `README.md` documents the current Amazon catalog pipeline and Open Library
  enrichment cascade.
- `VISION.md` defines the mission, design philosophy, and long-term direction.
- `docs/ARCHITECTURE.md` documents the source-of-truth principle, current data
  flow, future architecture, generated artifact policy, and expected module
  boundaries.
- Current pipeline extracts likely physical-book purchases from Amazon exports.
- ISBN-10 values are validated and converted to ISBN-13.
- Privacy-sensitive Amazon fields are excluded from extracted book rows.
- Open Library enrichment and fallback resolution are available.
- CSV and XLSX outputs are generated for browsing and review.
- Tests cover the core ISBN, extraction, enrichment, output, and catalog-join
  behavior currently in place.

Exit condition:

- The project has a working catalog-generation baseline and enough written
  architecture to guide future changes.

## Sprint 1: Repository Structure and Valuation Foundation

Sprint 1 should prepare the codebase for valuation work while keeping behavior
stable.

Goals:

- Introduce a clearer repository structure without changing the public workflow.
- Establish durable boundaries between catalog facts, market observations,
  valuation estimates, and decisions.
- Add schema documentation for the normalized catalog and future valuation data.
- Keep generated workbooks as outputs, not canonical data.

Likely work:

- Split the current single-file pipeline only where the boundary is obvious and
  useful.
- Create modules for ISBN utilities, Amazon import, Open Library access, cache
  handling, catalog assembly, and artifact writing.
- Define initial data contracts for:
  - catalog records;
  - market observations;
  - valuation estimates;
  - decision recommendations.
- Add fixture-driven tests around any moved behavior.
- Document how new generated artifacts should be named, stored, and regenerated.

Exit condition:

- The codebase has clear module boundaries for catalog work, and valuation data
  can be added without mixing facts, estimates, and recommendations in one flat
  table.

## v0.2.0: Incremental Full-History Imports

Version 0.2.0 should make the monthly Amazon workflow incremental without using
generated workbooks as source data.

Goals:

- Treat each Amazon download as a full-history source file, not a delta.
- Introduce durable CSV state under `data/`.
- Use `catalog_item_id` as the permanent internal catalog identity.
- Preserve durable `catalog_item_id` values across runs by loading existing
  catalog state before assigning IDs.
- Never derive `catalog_item_id` values from Amazon row order, catalog sort
  order, output row order, or other run-local positions.
- Treat ISBN-13 and ISBN-10 as preferred matching attributes, not canonical
  identity.
- Keep catalog items and acquisitions clearly separated.
- Preserve existing Research Assessments for known catalog items.
- Assess only newly discovered catalog items by default.
- Keep Research Assessments separate from future market valuation.

Durable files:

- `data/import_manifest.csv`: import audit log with file hash, counts, pipeline
  version, schema version, and latest-file marker.
- `data/catalog_items.csv`: one row per distinct catalog item/book identity.
- `data/acquisitions.csv`: one row per purchase or acquisition event.
- `data/research_priority_assessments.csv`: durable assessments linked by
  `catalog_item_id`.

Cache layout:

- `cache/openlibrary/isbn.json`
- `cache/openlibrary/search.json`

Default command:

```bash
python3 library_pipeline.py update-library
```

Future re-evaluation options:

```text
--reevaluate new
--reevaluate stale
--reevaluate all
```

Exit condition:

- A monthly run from the latest full Amazon CSV or ZIP export rebuilds acquisitions, reconciles
  them to durable catalog items, evaluates only new catalog items by default,
  preserves prior assessments, records an import-manifest audit row, and
  regenerates output artifacts from `input/`, `data/`, `cache/`, and `config/`.

Implementation status:

- Done: directory conventions and centralized path handling.
- Done: durable `catalog_item_id` reuse from `data/catalog_items.csv`.
- Done: `catalog_item_id` values in generated metadata and catalog outputs.
- Done: `data/acquisitions.csv` rebuilt from the current full-history Amazon
  export and linked to durable catalog items.
- Done: `data/import_manifest.csv` append-only audit log.
- Done: persistent Research Assessments in
  `data/research_priority_assessments.csv`.
- Done: latest `.csv`/`.zip` discovery in `input/amazon`.
- Done: Amazon ZIP and compatible `Retail.OrderHistory.1` package support.
- Done: Open Library caches default to `cache/openlibrary/`.
- Done: release polish for friendly expected CLI errors and optional macOS
  completion/failure notification.
- Follow-up: because existing nonblank catalog fields are preserved, improved
  external metadata will need an explicit refresh, override, or staleness policy.
- Follow-up: acquisition IDs are deterministic hashes of available Amazon
  evidence until a richer source-item layer exposes true source line IDs.
- Not yet done: explicit `--reevaluate` modes.

## Sprint 2: Research Assessments

Sprint 2 should add Research Assessments that identify which books deserve
human research first. A Research Assessment aggregates deterministic Research
Signals into a priority score, band, and explanation. It is a prioritization
tool, not a valuation estimate.

Goals:

- Rank books by expected research value using available catalog evidence.
- Surface books likely to require manual attention.
- Keep the scoring logic transparent and adjustable.

Possible score inputs:

- Presence or absence of LCC, Dewey, LCCN, OCLC, and subjects.
- Subject area or classification signals associated with scholarly value.
- Publication age or edition ambiguity.
- Duplicate purchase or multi-volume signals.
- Title-search fallback confidence.
- Missing or weak bibliographic resolution.
- Product-name clues that indicate sets, rare editions, imports, or specialized
  academic works.

Likely durable assessment fields:

- A `research_priority_score`.
- A `research_priority_band`, such as high, medium, low, or manual review.
- Compact Research Signal codes and summaries.
- Human-readable Research Signal explanations.

Exit condition:

- The catalog can produce reproducible Research Candidates that direct human
  time toward books with the highest expected payoff or uncertainty.

Implementation status:

- Done: deterministic Research Signals.
- Done: generated Research Assessments in the preserved durable
  `data/research_priority_assessments.csv` path.
- Done: generated `output/research_candidates.csv` and `.xlsx` views that rank
  high, medium, and low Research Assessments for collector attention.
- Done: durable `data/collector_reviews.csv` state for collector-owned review
  workflow fields and notes.
- Not yet done: reviewed-item filtering or priority override behavior.

## v0.3.0: Collector Review State And Generated Workbook

Version 0.3.0 introduces collector-owned review state and a generated workbook
designed for research planning, without making the workbook the source of
truth.

Goals:

- Produce a professional Collector Workbook from normalized data.
- Separate catalog facts, Research Assessments, Collector Reviews, and generated
  outputs.
- Make review efficient for the highest-priority books.

Likely workbook sections:

- Catalog overview.
- Research Candidates sorted by priority.
- Current Acquisitions.
- Reviewed Items.
- Metadata Gaps.
- Collector Reviews.
- Summary dashboard metrics.

Policy:

- The workbook is generated.
- Manual workbook edits are not durable unless imported through a documented
  workflow.
- Any import workflow must preserve provenance and avoid overwriting catalog
  facts with opinions.

Exit condition:

- A user can regenerate a Collector Workbook from project data and use it to
  guide review without hand-editing the canonical catalog.

## v0.4.0: Market Validation Spike

Version 0.4.0 is a documentation-first research experiment rather than a
valuation implementation effort. It validates whether the existing Research
Assessment model identifies books that are materially more likely to show
meaningful external market signals.

Plan:

- Use the subsystem architecture in
  [Market Intelligence](MARKET_INTELLIGENCE.md).
- Use the experimental design in
  [Market Validation Spike](MARKET_VALIDATION_SPIKE.md).
- Sample books across Research Score bands instead of only high-scoring
  candidates using `generate-market-validation-sample`, targeting 100 books
  across five score bands when the catalog distribution supports it.
- Collect lightweight AbeBooks market observations with
  `collect-abebooks-observations`.
- Treat AbeBooks as feasible for small ISBN-first observation runs, while
  keeping the integration experimental.
- Report observation coverage and source-access diagnostics with
  `report-market-observation-coverage`.
- Interpret externally observed market evidence in PR8 with
  `analyze-market-validation`.
- Review individual signal effectiveness and model calibration in PR9 with
  `review-research-signal-effectiveness`.
- Synthesize interpretation limits and calibration guardrails in
  [Market Validation Findings](MARKET_VALIDATION_FINDINGS_v0.4.0.md).
- Review calibration alternatives and future acceptance criteria in the
  [Research Assessment Calibration Proposal](RESEARCH_ASSESSMENT_CALIBRATION_PROPOSAL_v0.4.0.md).
- Analyze whether higher Research Scores are associated with stronger observed
  asking-price signals and higher observation coverage.
- Use the results to decide whether automated valuation, valuation import, or
  model refinement should come next.

PR8 findings:

- Current Research Scores are heavily concentrated in the `8-10` band.
- The validation sample reached 65 books because the `2-3` band is empty and
  the `6-7` band has only five available books.
- AbeBooks returned observations for all sampled books.
- Higher-score books showed stronger maximum observed asking prices, but
  low-score false-negative candidates remain important follow-up evidence.

PR9 findings:

- Signal effectiveness is mixed when judged by medians rather than maxima.
- `university_press` and `missing_lcc` meet the sample median, while several
  other signals remain weak, inconsistent, or too sparse to classify.
- The observed score-band medians do not form a monotonic gradient.
- Candidate model changes remain future work; PR9 does not alter scoring.

PR10 records the provisional findings and calibration principles without
changing the model. The recommended next step is PR11, a reviewed Research
Assessment Calibration Proposal that defines specific refinements before any
scoring implementation.

PR11 recommends signal-role rebalancing as the preferred direction, subject to
a before/after simulation. PR12 expands the original validation evidence first:
it preserves 65 existing books, selects 140 additional candidates across
available bands, records exhausted-band deficits, and supports bounded AbeBooks
collection without replacing prior artifacts. PR13 should compare hypothetical
evidence with the original 65-book findings. The refreshed results retain a
non-monotonic median pattern but strengthen the `8+` band and two previously
uncertain signals. PR14 should compare hypothetical score distributions,
priority bands, candidate rankings, and known candidate misses without changing
production configuration or persisted assessments.

PR14 simulation result:

- Conservative and market-likelihood scenarios alter many scores and several
  production bands.
- Neither scenario changes top-50 membership or its observed asking-price
  profile.
- Three false-positive references move down under each scenario, but no false-
  negative references move up.
- Outlier-sensitive top-50 representation remains unchanged.

PR15 records the decision not to implement production scoring changes in
v0.4.0. The simulated alternatives behaved differently but did not improve the
practical top candidate set. Current scoring, signals, weights, and persisted
assessments remain unchanged. A future model-design effort should investigate
separate market-likelihood and research-effort concepts.

PR16 confirms release readiness and closes the research spike without reopening
calibration absent new evidence. The release is ready for final commit, tagging,
and publication using `docs/RELEASE_NOTES_v0.4.0.md`.

Exit condition:

- The project has evidence about whether Research Score contains predictive
  information about market value, and follow-on valuation work is grounded in
  that evidence.

## Later: Top-25 Market Research Workflow

After the Market Validation Spike, the project may create a focused workflow
for researching the highest-priority books first.

Goals:

- Select the top 25 Research Candidates.
- Capture comparable market evidence in a structured way.
- Produce initial valuation estimates backed by observed data.
- Preserve source URLs, capture dates, condition notes, and confidence.

Market sources may include:

- AbeBooks.
- eBay completed sales.
- Bookfinder.
- Amazon Used.
- Other reputable secondary-market sources.

Likely work:

- Define the market-observation schema.
- Add a structured input path for manual market research.
- Add validation for required evidence fields.
- Generate a top-25 research workbook or worksheet.
- Produce first-pass retail and dealer-value estimates from captured evidence.
- Keep heuristic scoring separate from evidence-based valuation.

Exit condition:

- The project can guide focused research on the top 25 books and turn that
  research into transparent, evidence-backed valuation estimates.

## Later

Later work should build on the catalog, research, and valuation foundations
rather than replacing them.

Dealer prospectus:

- Generate professional summaries for dealers or specialist buyers.
- Group books by subject, collection, author, or classification range.
- Include evidence-backed highlights and clear condition caveats.
- Keep dealer-facing outputs generated from normalized project data.

Automated pricing:

- Add structured integrations or assisted workflows for market data collection.
- Track source, date, condition, listing type, and sale status.
- Distinguish asking prices from completed sales.
- Compute valuation estimates with confidence and rationale.
- Support recalculation when pricing strategy or market data changes.

Collection analytics:

- Analyze subject concentration by LCC, Dewey, author, publisher, or period.
- Identify collection-level sale opportunities.
- Highlight duplicate, incomplete, or multi-volume sets.
- Produce estate, donation, retention, and family-review reports.

Long-term exit condition:

- The system helps users make informed selling, donating, and retention
  decisions from reproducible data, transparent evidence, and generated
  decision-support artifacts.

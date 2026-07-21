# Library Valuation

Library Valuation turns Amazon Order History exports into a durable,
privacy-conscious collector workflow. It helps identify which books are worth
researching first, explains why they surfaced, and generates collector-facing
review artifacts without making generated spreadsheets the source of truth.

## Current Finding

In the May 2026 sample export, Amazon's `ASIN` field mostly split cleanly:

- `B...` values are usually Amazon catalog ASINs for ordinary products and
  Kindle-related items.
- Non-`B` 10-character values are ISBN-10-like identifiers. These are the best
  first pass for physical books.

The project should treat non-`B` ISBN-looking ASINs as book candidates, validate
their check digits, convert them to ISBN-13, and then enrich them through
bibliographic APIs.

Known limitation: June 2026 acceptance testing found at least one likely
physical book with a modern `B0...` ASIN. Improving detection for those ASINs is
deferred to the backlog.

## Recommended Enrichment Cascade

1. **Open Library by ISBN**
   - Best first API because it accepts ISBN-10 or ISBN-13.
   - It can return title, author, publisher, LCCN, OCLC identifiers, Dewey, and
     `lc_classifications` when present.

2. **Library of Congress**
   - Use as a cross-check and as a source for LoC-held/digitized items.
   - The public `loc.gov` JSON API does not expose every catalog record, so do
     not expect full coverage from it alone.

3. **OCLC / WorldCat**
   - Likely the best paid/credentialed source when Open Library lacks an LCC.
   - Store OCLC numbers from Open Library now so we can use them later if API
     access is available.

4. **Manual Review**
   - Some books will not resolve cleanly, especially older, obscure, imported,
     marketplace, multi-volume, or duplicate ISBN records.
   - Keep unresolved rows with title and ISBN so they can be searched manually.

## Privacy

The extraction step intentionally excludes billing address, shipping address,
tracking number, payment method, gift fields, and other personal columns.

## Project Docs

- `docs/ARCHITECTURE.md`: source-of-truth rules and system boundaries.
- `docs/DATA_MODEL.md`: durable CSV layouts and future valuation model.
- `docs/ROADMAP.md`: release direction and implementation sequence.
- `docs/BACKLOG.md`: lightweight product backlog for future releases.
- `docs/RELEASE_PLAN_v0.9.0.md`: completed resumable full-library eBay release
  plan.
- `docs/RELEASE_PLAN_v0.10.0.md`: Libib physical-inventory release boundary,
  PR sequence, and acceptance contract.
- `docs/LIBIB_INVENTORY_DESIGN.md`: tentative durable inventory entities,
  copy semantics, matching, reconciliation, and idempotency design.
- `docs/RELEASE_READINESS_v0.9.0.md`: final v0.9.0 release gate and audit.
- `docs/RELEASE_NOTES_v0.9.0.md`: user-facing v0.9.0 release summary.
- `docs/FULL_LIBRARY_EBAY_BASELINE_v0.9.0.md`: completed production baseline,
  integrity, evidence-quality, and privacy results.
- `docs/FULL_LIBRARY_MULTISOURCE_RECONCILIATION_v0.9.0.md`: deterministic
  materialization, full source reconciliation, and reviewer-artifact QA.
- `docs/MARKET_INTELLIGENCE.md`: v0.5.0 market-evidence-first architecture,
  generated summary schema, confidence, range, and review rules.
- `docs/MARKET_VALIDATION_SPIKE.md`: v0.4.0 plan for validating whether
  Research Score predicts market value.
- `docs/MARKET_VALIDATION_FINDINGS_v0.4.0.md`: provisional findings and
  calibration guardrails from the v0.4.0 experiment.
- `docs/RESEARCH_ASSESSMENT_CALIBRATION_PROPOSAL_v0.4.0.md`: proposed future
  model refinements and simulation requirements; no scoring changes.
- `docs/CALIBRATION_SCENARIO_REVIEW_v0.4.0.md`: PR15 decision to preserve
  production scoring in v0.4.0 and defer model redesign.
- `docs/RELEASE_READINESS_v0.4.0.md`: verified v0.4.0 release scope, commands,
  generated artifacts, limitations, and remaining release steps.
- `docs/RELEASE_NOTES_v0.4.0.md`: concise user-facing v0.4.0 release summary.
- `docs/RELEASE_NOTES_v0.5.0.md`: concise user-facing v0.5.0 release summary.
- `docs/RELEASE_READINESS_v0.5.0.md`: v0.5.0 scope, acceptance evidence, and
  remaining release steps.
- `docs/RELEASE_CHECKLIST.md`: release-readiness checklist.

## Developer Setup

Create and activate the project virtual environment, then install dependencies:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Before committing, run the compile check and tests:

```bash
python -m compileall .
pytest
```

To include coverage reporting:

```bash
pytest --cov
```

## Creating a Release

Use the release helper with a semantic version:

```bash
./release.sh 0.3.0
```

The script requires a clean working tree, runs compile checks, runs the pytest
suite, creates an annotated Git tag, pushes the current branch, and pushes the
tag.

Creating the GitHub Release remains a manual step. Use `CHANGELOG.md` for the
release notes.

## Usage

Monthly update from a fresh full Amazon export saved under `input/amazon/`:

```bash
python3 library_pipeline.py update-library
```

You can still provide an explicit Amazon export when needed:

```bash
python3 library_pipeline.py update-library \
  --amazon-input "/path/to/Your Orders.zip"
```

Supported Amazon inputs are `Order History.csv`, `Your Orders.zip`, and
extracted export directories. On macOS, successful and expected failed monthly
updates show a desktop notification when run from an interactive terminal and
`osascript` is available.

Preview one approved Libib audit through the complete inventory workflow:

```bash
python3 library_pipeline.py update-inventory \
  --source input/libib/study/library_20260720_013144.csv \
  --audit-scope "Study" \
  --audit-completeness partial_scope
```

Preview is the default. It runs against temporary copies of `data/`, leaves
durable repositories unchanged, and generates
`output/inventory_audit_summary.csv` and
`output/inventory_review_workbook.xlsx`. Identical source content, durable
starting state, audit area, scope, and completeness produce identical preview
IDs, completion output, and artifact bytes. After reviewing the summary and queues,
repeat the same command with `--publish` to authorize durable publication.
The source must be inside an explicit audit-area folder below
`--libib-input-dir` (default `input/libib`); the command never discovers files
recursively. Libib inventory can create a catalog identity and holding when the
approved evidence is sufficient, but it never creates acquisition history.

This writes:

- `book_purchases.csv` / `book_purchases.xlsx`: one row per Amazon book line item
- `book_metadata.csv` / `book_metadata.xlsx`: one row per unique ISBN-13
- `library_catalog.csv` / `library_catalog.xlsx`: purchase rows joined to metadata for Excel browsing
- `research_candidates.csv` / `research_candidates.xlsx`: generated Research
  Candidates in priority order
- `collector_workbook.xlsx`: generated collector dashboard workbook

The update workflow reuses `cache/openlibrary/isbn.json` and
`cache/openlibrary/search.json`, so ISBNs and title searches that already
have answers are not requested again.

### v0.3.0 Monthly Workflow

Version 0.3.0 adds the collector-facing research workflow on top of the durable
monthly state introduced in v0.2.0.

The user periodically downloads a full Amazon Order History CSV or ZIP package,
saves it under `input/amazon/`, and runs:

```bash
python3 library_pipeline.py update-library
```

Default behavior:

- Load previous durable catalog state.
- Find the latest full Amazon `.csv` or `.zip` export in `input/amazon`.
- Rebuild current acquisitions from the latest full-history file.
- Reconcile acquisitions to catalog items using ISBN-first matching.
- Update catalog metadata.
- Generate deterministic Research Signals.
- Generate or reuse system-owned Research Assessments.
- Generate Research Candidates.
- Preserve collector-owned Collector Reviews.
- Regenerate generated outputs, including `research_candidates.csv`,
  `research_candidates.xlsx`, and `collector_workbook.xlsx`.

The standard directory flags remain available for non-default workspaces:

```text
--input-dir input
--data-dir data
--cache-dir cache
--output-dir output
```

Durable state should live outside generated outputs:

```text
input/amazon/                         full Amazon Order History CSV downloads
data/import_manifest.csv              import audit log
data/catalog_items.csv                one row per catalog item identity
data/acquisitions.csv                 one row per purchase/acquisition event
data/research_priority_assessments.csv latest Research Assessments
data/collector_reviews.csv            collector-owned review workflow state
cache/openlibrary/isbn.json           Open Library ISBN lookup cache
cache/openlibrary/search.json         Open Library title-search cache
output/                               generated CSV, XLSX, and reports only
```

`catalog_item_id` is the permanent internal identity for catalog records.
ISBN-13 remains the preferred matching attribute, followed by ISBN-10, source
fingerprint, and normalized title/author fallback. Other durable files should
reference `catalog_item_id`. Existing `catalog_item_id` values are loaded from
`data/catalog_items.csv` and reused across runs; they must not be regenerated
from Amazon row order, catalog sort order, or output row order.

Generated Excel and CSV files under `output/` are not source data. They should
be reproducible from `input/`, `data/`, `cache/`, `config/`, and code.

Research Assessments are separate from market valuation. A Research Assessment
answers whether a book should be researched and why; a future market valuation
layer should answer what the book is likely worth.

v0.4.0 adds a Market Validation Spike to test whether higher Research Scores
are associated with stronger observed market signals before building valuation
workflow features. The completed experiment preserves production scoring and
treats AbeBooks asking prices as observations, not valuations.

Generate the deterministic analysis-scale input dataset for that spike after a
successful monthly update:

```bash
python3 library_pipeline.py generate-market-validation-sample \
  --output-dir output \
  --sample-size-per-band 20 \
  --seed 42
```

This writes `market_validation_sample.csv` and
`market_validation_sample.xlsx` under `output/`, targeting 100 books across five
Research Score bands when the catalog distribution supports it. It also writes
`market_validation_sample_metadata.csv` and
`market_validation_sample_metadata.xlsx` with band-level population counts,
actual sample counts, seed, timestamp, Research Assessment model version, and
configuration hash. The sample includes Research Score bands and triggered
Research Signals, but no valuation or marketplace fields.

Collect bounded AbeBooks observations for the analysis sample:

```bash
python3 library_pipeline.py collect-abebooks-observations \
  --output-dir output \
  --limit 100
```

This writes `market_observations.csv` and `market_observations.xlsx` under
`output/`. These rows are lightweight market observations or lookup-status
records, not valuations or recommendations.

The AbeBooks feasibility spike confirmed that small, bounded ISBN-first runs can
return real listing observations in the current environment when Python uses a
valid CA bundle. The collector remains experimental and should not be treated as
a production marketplace integration. PR7 prepares the generated data needed for
PR8 analysis; it does not draw valuation conclusions.

Summarize observation coverage and source-access diagnostics:

```bash
python3 library_pipeline.py report-market-observation-coverage \
  --output-dir output
```

This writes `market_observation_coverage_report.csv` and
`market_observation_coverage_report.xlsx` under `output/`. The report describes
lookup coverage, failure diagnostics, and generated search URLs; it does not
estimate value.

Analyze Research Score, triggered Research Signals, and observed AbeBooks asking
prices:

```bash
python3 library_pipeline.py analyze-market-validation \
  --output-dir output
```

This writes `market_validation_analysis.csv` and
`market_validation_analysis.xlsx` under `output/`. The analysis compares score
bands, signals, observation coverage, and asking-price summaries. Asking prices
remain market observations, not valuations or appraisal conclusions.

Review individual Research Signal effectiveness and model calibration:

```bash
python3 library_pipeline.py review-research-signal-effectiveness \
  --output-dir output
```

This writes `research_signal_effectiveness_review.csv` and
`research_signal_effectiveness_review.xlsx` under `output/`. The generated
review uses sample-relative classifications, signal combinations, and relative
false-positive/false-negative candidates without changing Research Score logic.
The resulting evidence and its interpretation limits are summarized in
[Market Validation Findings](docs/MARKET_VALIDATION_FINDINGS_v0.4.0.md).
Possible future refinements are evaluated in the
[Research Assessment Calibration Proposal](docs/RESEARCH_ASSESSMENT_CALIBRATION_PROPOSAL_v0.4.0.md).

Expand the validation evidence base while preserving the original sample:

```bash
python3 library_pipeline.py generate-expanded-market-validation-sample \
  --output-dir output \
  --additional-candidate-target 140 \
  --seed 42
```

This writes an expanded sample and metadata as paired CSV/XLSX artifacts. To
reuse existing observations and collect only newly selected books, run:

```bash
python3 library_pipeline.py collect-expanded-abebooks-observations \
  --output-dir output \
  --limit 140
```

The expanded collector remains bounded and writes
`expanded_market_observations.csv` and `.xlsx` without replacing the original
sample or observation artifacts.

Refresh coverage, score-band analysis, and Research Signal effectiveness using
the expanded evidence:

```bash
python3 library_pipeline.py analyze-expanded-market-validation \
  --output-dir output
```

This writes paired CSV/XLSX artifacts for expanded validation analysis, signal
effectiveness, and observation coverage. It compares the 205-book evidence base
with the original 65-book results without changing Research Assessment scoring.

Simulate hypothetical Research Assessment calibration scenarios:

```bash
python3 library_pipeline.py simulate-research-assessment-calibration \
  --output-dir output \
  --top-n 50
```

The simulation compares the persisted baseline with conservative rebalancing
and market-likelihood emphasis. It writes per-book, summary, and candidate-
movement artifacts without changing production configuration or assessments.
The resulting [Calibration Scenario Review](docs/CALIBRATION_SCENARIO_REVIEW_v0.4.0.md)
records the decision not to change production scoring in v0.4.0. A future model
may separate market likelihood from research effort, but that redesign is not
part of this release.

### v0.5.0 Market-Evidence-First Workflow

Version 0.5.0 turns generated market observations into a source-neutral,
per-book Market Evidence Summary. Market observations are primary evidence when
usable. Existing Research Signals remain fallback, uncertainty,
metadata-cleanup, and review-prioritization context; they are not price inputs.

After collecting `output/market_observations.csv`, run:

```bash
python3 library_pipeline.py summarize-market-evidence \
  --observations output/market_observations.csv \
  --output-csv output/market_evidence_summary.csv \
  --output-xlsx output/market_evidence_summary.xlsx
```

The input contains source-specific listing and status rows. The generated
summary contains one row per catalog item with coverage, match quality, asking-
price statistics, market confidence, outlier sensitivity, a cautious range,
and review guidance. Both artifacts are generated output and are not read back
as durable truth by the monthly import.

The range is derived from observed seller asking prices. It is not an
appraisal, fair market value, realized sale price, definitive valuation, or
guarantee of sale proceeds. Mixed currencies are not converted or combined.

### v0.6.0 Full AbeBooks Baseline & Review Artifacts

Before adding another live marketplace, v0.6.0 establishes an AbeBooks-only
directional baseline for the full assessed catalog. First refresh the catalog
and Research Assessments from the current Amazon input:

```bash
.venv/bin/python library_pipeline.py update-library \
  --amazon-input input/amazon \
  --output-dir output
```

Then start with a bounded test:

```bash
.venv/bin/python library_pipeline.py collect-full-library-abebooks-observations \
  --output-dir output \
  --data-dir data \
  --output output/full_abebooks_market_observations_test.csv \
  --limit 100 \
  --delay 2 \
  --max-results-per-book 3
```

Inspect the test CSV/XLSX and source diagnostics before starting a full run.
The full run may query more than 3,000 books and can take several hours. Do not
remove the delay or run concurrent collectors. Use a distinct output name to
preserve the test artifact if it matters.

```bash
.venv/bin/python library_pipeline.py collect-full-library-abebooks-observations \
  --output-dir output \
  --data-dir data \
  --delay 2 \
  --max-results-per-book 3

.venv/bin/python library_pipeline.py summarize-market-evidence \
  --observations output/full_abebooks_market_observations.csv \
  --output-csv output/full_abebooks_market_evidence_summary.csv \
  --output-xlsx output/full_abebooks_market_evidence_summary.xlsx

.venv/bin/python library_pipeline.py build-abebooks-review-workbook \
  --summary output/full_abebooks_market_evidence_summary.csv \
  --output-xlsx output/full_abebooks_review_workbook.xlsx \
  --data-dir data

.venv/bin/python library_pipeline.py build-abebooks-review-report \
  --summary output/full_abebooks_market_evidence_summary.csv \
  --output-html output/full_abebooks_review_report.html \
  --data-dir data
```

The collector writes `full_abebooks_market_observations.csv/.xlsx` by default;
it does not replace `market_observations.csv/.xlsx`. Repeating the command with
the same `--output` replaces that generated CSV/XLSX pair. The workflow is not
resumable, so retain completed outputs before rerunning if they matter.

The summary workbook supports filtering and pivoting by
`review_recommendation`, `market_confidence`, `outlier_sensitivity`, and
`evidence_status`. The baseline is observed AbeBooks asking-price evidence and
review guidance, not an appraisal, fair market value, or realized sale estimate.

The generated review workbook adds a prioritized human review queue, focused
sale/research/edition tabs, acquisition-date possession context, full evidence
detail, run counts, and field definitions. Books whose latest acquisition is
before 2021 are flagged for physical verification. The workbook does not alter
the canonical evidence summary or durable catalog and acquisition data.

When the input is a source-aware multi-source summary, the same workbook adds
compact `Evidence Sources`, `eBay Listings`, `eBay Price Range`, `eBay Status`,
and `Source Price Comparability` columns to its reviewer queues. Evidence Detail
retains the source-specific audit fields, and Run Summary reports source mix,
eBay listing/status totals, core range source, and comparability. AbeBooks
remains the core range source for mixed rows; eBay remains supplemental active-
listing item-price evidence with shipping excluded, no conversion, unknown
match confidence, and no stored seller identity. Legacy AbeBooks-only summaries
remain supported.

The generated static HTML report is a simpler, self-contained sharing view. It
uses tabbed review queues, queue-specific guidance, a single human-readable
AbeBooks range, acquisition-year possession prompts, and a field guide with the
report sort order. With a source-aware summary, its tables mirror the workbook's
five compact source displays and its summary/guidance explain the supplemental
eBay boundary. AbeBooks remains the core mixed-source range; eBay item prices
exclude shipping, are not converted or pooled, retain unknown match confidence,
and require human title/edition review. Seller identity is not stored or shown.
Legacy AbeBooks-only reports retain their existing columns and presentation.
Re-running the command replaces the requested HTML output; the report is
generated, ignored data.

All files produced under `output/` by this workflow are generated artifacts and
remain ignored/untracked. AbeBooks asking prices are not appraisals, fair market
value, realized sale prices, or expected sale proceeds. Edition, condition,
dust jacket, signature, seller credibility, and physical possession may
materially affect value. eBay and other market sources are not included in
v0.6.0; eBay active-listing integration is planned for v0.7.0.

### v0.7.0 eBay Active Listings Integration

Version 0.7.0 introduces eBay incrementally as a second source of active-listing
asking-price evidence. It includes isolated credential/access handling, a Browse
API client, normalized eBay observations, bounded reviewer-priority collection,
and repeated-input multi-source summaries. A two-book production smoke run has
validated the bounded observation path; broader collection remains gated.

Active eBay listings are not sold prices, fair market value, appraisals,
realized sale prices, or expected proceeds. Credentials and tokens must remain
in environment variables or local ignored configuration, and all eBay outputs
remain generated under `output/`. See
[`docs/RELEASE_PLAN_v0.7.0.md`](docs/RELEASE_PLAN_v0.7.0.md).

The PR2 developer access check requires an explicit environment and performs
only one bounded active-listing search without writing an output file:

```bash
export EBAY_CLIENT_ID="..."
export EBAY_CLIENT_SECRET="..."
export EBAY_MARKETPLACE_ID="EBAY_US"
export EBAY_ENVIRONMENT="production"  # or sandbox

.venv/bin/python library_pipeline.py ebay-access-check \
  --query "Springer Handbook of Spacetime" \
  --limit 3
```

Do not commit credentials, tokens, `.env` files, or authorization headers. The
command obtains an OAuth application token through the client-credentials flow,
runs one Browse API item-summary search, and prints only environment,
marketplace, success/count fields, and up to three title/price/currency snippets.
It does not create eBay observations, update market evidence, collect the full
library, or provide sold/completed evidence.

Sandbox and production must use their corresponding local keysets. On
2026-07-18, the production keyset acquired an application token and completed a
bounded Browse access check after a local Production Client ID typo was fixed.
The earlier `invalid_client` response was a local configuration error, not a
code, TLS, compliance, or Production Cert ID failure.

The local Python 3.14 environment had no active default CA file. Pointing
`SSL_CERT_FILE` to the installed certifi bundle restored verified HTTPS without
disabling validation. With the corrected local sandbox keyset, the 2026-07-17
bounded check acquired an application token and completed one Browse API search
for `Springer Handbook of Spacetime`. Sandbox returned zero results, which is
acceptable for access validation and says nothing about production result
quality. The CA override is local troubleshooting, not required project runtime
behavior.

PR5 adds an explicit targeted collector for generated eBay observation rows.
The summary, output, and bounded book limit are required; the default queue is
`review_for_possible_sale`, and additional supported queues can be included by
repeating `--review-recommendation`:

```bash
.venv/bin/python library_pipeline.py collect-targeted-ebay-observations \
  --summary output/full_abebooks_market_evidence_summary.csv \
  --output output/targeted_ebay_observations.csv \
  --limit-books 10 \
  --max-results-per-book 3 \
  --delay 1
```

The command requires the same four eBay environment variables as the access
check. It writes paired CSV/XLSX files under the ignored `output/` boundary and
overwrites that generated pair on an intentional rerun. Queries use ISBN-13,
then ISBN-10, then title plus author, then a usable title alone. Books without a
safe query receive `no_query`; zero results receive `no_results`; the first safe
client failure receives `source_unavailable` and stops the run to avoid repeated
authentication attempts.

This collector is capped at 100 books and 10 results per book; both command
defaults and examples are smaller. Item price and returned currency are
preserved, shipping is excluded, and match confidence remains unknown. PR5 does
not automatically feed these rows into downstream artifacts. A 2026-07-18
production smoke run used two books, at most three results per book, and a
one-second delay. It produced four observed rows with item prices, currencies,
conditions, item IDs, and listing URLs. Seller identity was not normalized;
every eBay `seller` field was blank and no `match_notes` contained seller
identity. See [`docs/RELEASE_READINESS_v0.8.0.md`](docs/RELEASE_READINESS_v0.8.0.md).
This small run does not authorize broader or full-library collection.

The v0.9.0 full-library command is a separate production-only, resumable path:

```bash
.venv/bin/python library_pipeline.py collect-full-library-ebay-observations \
  --summary output/full_abebooks_market_evidence_summary.csv \
  --output-dir output/full_library_ebay \
  --checkpoint output/full_library_ebay \
  --delay 1 \
  --max-results-per-book 3 \
  --max-retries 2 \
  --retry-delay 5 \
  --max-retry-delay 60 \
  --confirm-production
```

It requires `EBAY_ENVIRONMENT=production` and explicit confirmation. Compatible
state resumes by default; `--restart` archives the existing checkpoint as a
sibling before creating a new run. State is written atomically after every
transition, and concise progress plus `run_summary.json` contain no listing
details. PR3 writes only ignored manifest, ledger, and per-item JSON parts; final
combined CSV/XLSX and reviewer regeneration remain later work. Active listings
remain supplemental item asking prices with blank sellers, excluded shipping,
no currency conversion, and unknown match confidence.

For long runs, the command reuses one application token in memory, refreshes it
before expiration, and refreshes once after a rejected bearer token. Credential
or repeated bearer-authentication failures stop globally. Temporary network,
rate-limit, and selected 5xx failures use per-invocation bounded exponential
backoff; a safe server retry-after value is honored subject to the configured
cap. Exhausted temporary failures remain retryable for a later resume. Normal
interruption writes a safe summary and leaves the current item recoverable.

The v0.9.0 PR6 production baseline completed all 3,014 assessed books in one
invocation: 2,881 books produced 8,293 observed listings and 133 produced
source-specific no-results rows. Checkpoint integrity, duplicate prevention,
and seller/privacy scans passed. PR7 subsequently completed final combined
observations and reviewer-artifact regeneration; see
[`docs/FULL_LIBRARY_EBAY_BASELINE_v0.9.0.md`](docs/FULL_LIBRARY_EBAY_BASELINE_v0.9.0.md).

PR7 adds the network-free `materialize-full-library-ebay-observations` command.
It validates completed checkpoint state and writes canonical eBay CSV/XLSX
files in deterministic ledger order. The complete local workflow reconciled
8,426 eBay rows plus 8,311 AbeBooks rows into a 3,014-book source-aware summary,
workbook, and HTML report with no AbeBooks core-semantic changes. Generated
artifacts remain ignored; see
[`docs/FULL_LIBRARY_MULTISOURCE_RECONCILIATION_v0.9.0.md`](docs/FULL_LIBRARY_MULTISOURCE_RECONCILIATION_v0.9.0.md).

v0.8.0 PR3 completed a representative but still bounded 100-book production
validation across three review queues. A deterministic ignored cohort contained
34 `review_for_possible_sale`, 33 `manual_market_research_needed`, and 33
`review_edition_or_condition` books. The run produced 229 observed listings for
87 books and 13 `no_results` rows. All 242 rows had blank `seller`, no
`match_notes` mentioned seller identity, and all match confidence remained
`unknown`. Results support later design of concise reviewer-facing eBay context,
which is now available in the generated workbook and HTML report; broader
collection is not enabled. See
[`docs/PRODUCTION_EBAY_VALIDATION_v0.8.0.md`](docs/PRODUCTION_EBAY_VALIDATION_v0.8.0.md).

PR6 extends `summarize-market-evidence` so `--observations` can be repeated for
an explicit prototype combining AbeBooks and targeted eBay observation files:

```bash
.venv/bin/python library_pipeline.py summarize-market-evidence \
  --observations output/full_abebooks_market_observations.csv \
  --observations output/targeted_ebay_observations.csv \
  --output-csv output/multisource_market_evidence_summary.csv \
  --output-xlsx output/multisource_market_evidence_summary.xlsx
```

The result remains one row per catalog item. Source-specific counts, statuses,
currencies, and minimum/median/maximum asking prices remain separate. When
AbeBooks evidence exists, the established overall range, confidence, and review
recommendation remain AbeBooks-based; eBay is supplemental and cannot upgrade
or erase them. For eBay-only items the core fields cautiously summarize that
source, with match confidence still unknown. Cross-source or within-source
currency differences are labeled and never converted or pooled. Shipping is
excluded. PR6 does not update the workbook or HTML report.

The tiny post-PR5 sandbox smoke test used two ISBN-13 queries through verified
TLS and completed OAuth plus both Browse requests. It produced two ignored
`no_results` rows and paired CSV/XLSX output. This validates the sandbox request
and artifact path only—not production access, listing coverage, prices, or match
quality.

The v0.7.0 operational sequence is:

1. Store sandbox credentials in ignored `.env` and source them into the current
   shell; the application never commits or prints them.
2. Optionally run `ebay-access-check` for one bounded connectivity check.
3. Run `collect-targeted-ebay-observations` with an explicit small
   `--limit-books`.
4. Pass the AbeBooks and eBay observation CSVs as repeated `--observations`
   inputs to `summarize-market-evidence`.
5. Review eBay only as supplemental active-listing asking-price evidence.

The PR7 local readiness run combined the full AbeBooks observations with the
two-row sandbox smoke artifact and produced 3,014 summary rows: 3,012
`abebooks_only` and 2 `abebooks_and_ebay_active_listings`. The two eBay rows were
`no_results` statuses, not global market absence. Generated files remained
ignored. The summary is not an appraisal. At the v0.7.0 release boundary,
workbook/HTML integration remained deferred; v0.8.0 now provides those
projections. See
[`docs/RELEASE_READINESS_v0.7.0.md`](docs/RELEASE_READINESS_v0.7.0.md).

Extract candidate books from an Amazon order-history CSV. This writes both
`book_candidates.csv` and `book_candidates.xlsx`:

```bash
python3 library_pipeline.py extract \
  --input "/path/to/Order History.csv" \
  --output output/book_candidates.csv
```

Summarize an Amazon order-history CSV:

```bash
python3 library_pipeline.py summarize \
  --input "/path/to/Order History.csv"
```

Enrich candidates with Open Library. This writes both
`book_enriched_openlibrary.csv` and `book_enriched_openlibrary.xlsx`:

```bash
python3 library_pipeline.py enrich-openlibrary \
  --input output/book_candidates.csv \
  --output output/book_enriched_openlibrary.csv
```

The enrichment command uses a local JSON cache in
`output/openlibrary_cache.json` by default.

Analyze enrichment coverage:

```bash
python3 library_pipeline.py analyze-enrichment \
  --input output/book_enriched_openlibrary.csv
```

Resolve rows that Open Library did not find by exact ISBN:

```bash
python3 library_pipeline.py resolve-missing \
  --input output/book_enriched_openlibrary.csv \
  --output output/book_resolved_openlibrary.csv
```

This keeps already matched rows intact, retries missing rows by the original
ISBN-10, then searches Open Library by title. The output includes
`resolution_source`, `resolution_confidence`, `resolution_notes`, and
`resolved_query`.

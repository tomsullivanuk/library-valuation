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
- `docs/MARKET_INTELLIGENCE.md`: v0.4.0 architecture for external market
  observations and future valuation evidence.
- `docs/MARKET_VALIDATION_SPIKE.md`: v0.4.0 plan for validating whether
  Research Score predicts market value.
- `docs/MARKET_VALIDATION_FINDINGS_v0.4.0.md`: provisional findings and
  calibration guardrails from the v0.4.0 experiment.
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

For v0.4.0, the next valuation step is a documentation-first Market Validation
Spike to test whether higher Research Scores are associated with higher observed
market values before building valuation workflow features.

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

# Amazon Library Classification Project

This project turns an Amazon order-history CSV into a privacy-conscious book list
that can be enriched with Library of Congress Classification (LCC) data.

## Current Finding

In the May 2026 sample export, Amazon's `ASIN` field splits cleanly:

- `B...` values are Amazon catalog ASINs for ordinary products and Kindle-related
  items.
- Non-`B` 10-character values are ISBN-10-like identifiers. These are the best
  first pass for physical books.

The project should treat non-`B` ISBN-looking ASINs as book candidates, validate
their check digits, convert them to ISBN-13, and then enrich them through
bibliographic APIs.

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

4. **Manual Review Queue**
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
./release.sh 0.2.0
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

The update workflow reuses `cache/openlibrary/isbn.json` and
`cache/openlibrary/search.json`, so ISBNs and title searches that already
have answers are not requested again.

### v0.2.0 Monthly Workflow

Version 0.2.0 introduces durable monthly state while preserving generated CSV
and XLSX reports as disposable outputs.

The current implementation maintains durable `catalog_item_id` values in
`data/catalog_items.csv` and includes those IDs in generated metadata and
catalog outputs.

It also rebuilds `data/acquisitions.csv` from the provided full Amazon export on
each `update-library` run. Acquisition IDs are deterministic `AMZ-...` hashes
derived from available Amazon purchase evidence.

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
- Load existing research priority assessments.
- Assess only newly discovered catalog items by default.
- Preserve prior assessments for known catalog items.
- Regenerate output files.

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
data/research_priority_assessments.csv
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

Research priority is separate from market valuation. Research priority answers
whether a book should be researched; a future market valuation layer should
answer what the book is likely worth.

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

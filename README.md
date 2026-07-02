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

## Usage

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

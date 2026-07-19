# Library Valuation v0.8.0 Representative Production eBay Validation

## Decision

**Production eBay active-listing evidence is useful enough to justify a later,
separately scoped reviewer-facing source-context design.**

It is not reliable enough for automatic edition matching, price pooling,
shipping-inclusive pricing, sold-price inference, or unattended broader
collection. Existing workbooks, HTML reports, AbeBooks behavior, Research
Assessments, and review recommendations remain unchanged.

## Scope and Method

PR3 validates 100 books in production, not the full library. The cohort contains:

- 34 `review_for_possible_sale` books;
- 33 `manual_market_research_needed` books; and
- 33 `review_edition_or_condition` books.

The full generated AbeBooks summary contained enough candidates in every queue.
Because the normal selector preserves review-priority ordering, an ignored local
cohort file applied the existing deterministic ordering separately within each
queue. This balanced validation without changing recommendation logic.

The collector used production `EBAY_US`, ISBN-13 queries, at most three results
per book, and a one-second inter-request delay. Its explicit book ceiling was
raised from 50 to 100; inputs above 100 remain rejected.

## Generated Observation Results

The ignored CSV/XLSX pair contained the same 25 fields and 242 data rows. File
sizes were 176,348 bytes for CSV and 85,281 bytes for XLSX.

| Measure | Result |
|---|---:|
| Unique catalog books | 100 |
| Books with observed listings | 87 |
| Books with `no_results` only | 13 |
| Observed listing rows | 229 |
| `no_results` rows | 13 |
| `no_query` rows | 0 |
| `source_unavailable` rows | 0 |
| Priced rows | 229 |
| Listing URLs | 229 |
| Unique item IDs | 229 |
| Blank seller fields | 242 |
| Nonblank seller fields | 0 |
| Notes containing `seller` | 0 |

All rows used source `ebay_active_listings` and strategy `isbn13`. Every observed
row was USD-priced; the 13 status rows had blank currency. USD item prices had a
minimum of 4.43, median of 57.87, and maximum of 475.87. Shipping is excluded,
so these values describe the sample only.

## Cohort Coverage

| Review queue | Books | Books with listings | Listing rows |
|---|---:|---:|---:|
| `review_for_possible_sale` | 34 | 32 | 88 |
| `manual_market_research_needed` | 33 | 24 | 51 |
| `review_edition_or_condition` | 33 | 31 | 90 |

The manual-research cohort had the lowest observed coverage. That supports
showing absence/status context in later reviewer artifacts rather than treating
all queues as equally well covered.

## Evidence-Quality Review

Every observed row had a listing title. A conservative comparison of normalized
catalog-title tokens with listing-title tokens found:

- 175 of 229 rows included all catalog-title tokens;
- 202 included at least 75%;
- 224 included at least 50%; and
- 5 included fewer than 50%.

The five lower-overlap results were mostly plausible truncations, translated
titles, or media/format variants. One bundle-like title shows that an ISBN-13
query can still return evidence requiring reviewer judgment. The sample supports
displaying title, condition, price/currency, item ID/URL, buying options, and
location context to reviewers; it does not support changing match confidence
from `unknown` without separately reviewed rules.

## Multi-Source Summary Results

The ignored multi-source CSV/XLSX pair contained the same 53 fields and 3,014
data rows. File sizes were 1,536,944 bytes for CSV and 785,946 bytes for XLSX.

| Measure | Result |
|---|---:|
| `abebooks_and_ebay_active_listings` books | 100 |
| `abebooks_only` books | 2,914 |
| Total eBay active listings | 229 |
| Total eBay status rows | 13 |
| Books with eBay listings | 87 |
| Books with eBay `no_results` | 13 |
| `same_currency_separate_source_summaries` | 87 |
| `single_source_currency` | 2,809 |
| `no_priced_listings` | 118 |
| `market_range_source=abebooks` | 3,014 |

The generated summary was compared with the full AbeBooks baseline for
`likely_low`, `likely_mid`, `likely_high`, `market_confidence`, and
`review_recommendation`. No catalog row changed. This confirms eBay remains
supplemental and does not alter established AbeBooks core-range semantics.

## Privacy and Artifact Controls

- Seller username remains absent from normalized eBay listing objects.
- All 242 observation `seller` values are blank.
- No `match_notes` contains seller identity or a seller label.
- No raw API response was retained.
- Credentials, tokens, and authorization headers remained local.
- The balanced cohort, observation CSV/XLSX, and multi-source summary CSV/XLSX
  remain ignored under `output/` and are non-durable validation artifacts.

## Remaining Gates

PR4 implements the first reviewer-facing source-context projection in the
generated workbook. It adds compact source mix, eBay listing count, eBay price
range, source-specific status, and price-comparability columns while retaining
technical source fields in Evidence Detail. Run Summary and Field Definitions
make the supplemental boundary explicit. The workbook stores no seller identity
and does not change ranges, confidence, recommendations, or durable state.

PR5 mirrors those compact displays in the static HTML reviewer queues and adds
source-aware counts, field guidance, and caveats. It uses the same display
helpers as the workbook, keeps AbeBooks as the mixed-source core range, and does
not display seller identity. AbeBooks-only HTML input remains backward
compatible.

Before any broader production cadence, separately review effective call limits,
operational scheduling, overwrite/resume behavior, and the reviewer artifacts
in human use. Shipping, conversion, sold/completed evidence, automatic matching,
and full-library collection remain out of scope.

# Library Valuation v0.6.0 Source Integration Spike

## 1. Purpose

This bounded PR2 spike evaluates practical ways to add a second market or
quasi-market signal after the AbeBooks-only v0.5.0 release. It answers:

> Which source can we reliably query, parse, normalize, and test with the least
> operational complexity?

The spike recommends a PR3 implementation path. It does not integrate a live
source, alter production behavior, or treat every external signal as
price-confirming evidence.

## 2. Background

Version 0.5.0 turns source-specific observation rows into a generated,
source-neutral Market Evidence Summary. Review of 205 rows generated from
`output/expanded_market_observations.csv` showed coherent summary behavior but
also showed that all observations came from AbeBooks.

The spike originally proposed adding source breadth before range, confidence,
or review thresholds were tuned. Release review instead chose to establish the
full AbeBooks baseline in v0.6.0 and defer live source breadth to v0.7.0. The
desired future architecture remains:

```text
MarketSourceAdapter
        |
        v
Source-specific observation rows
        |
        v
Source-neutral market_observations.csv
        |
        v
market_evidence_summary.csv
```

The existing observation schema already preserves source, lookup strategy,
query, result rank, asking price, currency, condition, seller, listing URL,
match confidence, diagnostics, notes, and raw reference. It is shaped around
active asking-price listings and needs an explicit evidence-type extension
before sold, retail, availability, or metadata-only observations can coexist
safely.

## 3. Sources Evaluated

The spike evaluated a bounded shortlist:

- Google Books API.
- eBay Browse API for active listings.
- eBay Marketplace Insights for sold/completed evidence.
- Biblio Inventory API.
- viaLibri Search Link API.
- BookFinder consumer search.
- Alibris consumer search.
- Amazon retail and used-offer APIs.
- Validated manual/exported market observations.

The review used repository contracts, official source documentation available
on 2026-07-14, and one bounded Google Books ISBN request. It did not crawl
marketplaces, bypass authentication, or test undocumented endpoints.

## 4. Evaluation Criteria

Each candidate was evaluated for:

- **Evidence type:** asking price, sold price, retail price, availability, or
  metadata only.
- **Integration mode:** public API, authenticated API, page parsing,
  manual/exported input, or third-party service.
- **Lookup support:** ISBN, title/author, and controlled fallback search.
- **Operational friction:** credentials, approval, quotas, cost, source terms,
  HTML brittleness, and user setup.
- **Data quality:** price, currency, condition, seller, listing URL,
  sold/completed date, and match-confidence potential.
- **Schema fit:** ability to produce source-neutral observation rows and coexist
  with AbeBooks without source-specific aggregation rules.
- **Testability and failure behavior:** deterministic fixtures, visible source
  failures, and no live-network requirement for unit tests.

The decision gives access practicality and reliability the first veto. Among
usable paths, real asking-price or sold/completed evidence is more valuable than
metadata-only support.

## 5. Findings by Source

### Summary

| Candidate | Evidence type | Access pattern | Friction | Price detail | Decision |
| --- | --- | --- | --- | --- | --- |
| Validated manual/export | Declared asking, sold/completed, or retail evidence | Local file | Low | As supplied and validated | Recommend for PR3 |
| Google Books | Metadata/availability; occasional retail/list-price signal | Documented JSON API | Low to moderate; API key/quota behavior | Retail/e-book fields only when present | Defer as non-market support |
| eBay active listings | Observed asking-price evidence | Authenticated Browse API | Moderate to high; developer credentials and production approval | Strong | Preferred later live adapter |
| eBay sold/completed | Sold/completed listing evidence | Restricted Marketplace Insights API | High; closed to new users | Strong in principle | Defer |
| Biblio | Observed asking-price evidence | Affiliate/bookseller JSON API | Moderate to high; account and requested API key | Strong | Defer pending access verification |
| viaLibri | Meta-search asking-price discovery | User-facing search-link API | High for automation; automated search prohibited | Potentially useful to a human | Manual reference only |
| BookFinder | Meta-search asking-price discovery | Consumer web search | High for automation; no documented public result API found | Visible in search UI | Defer |
| Alibris | Observed asking-price evidence | Consumer web search | High for automation; no documented public result API found | Useful listing detail in HTML | Defer |
| Amazon | Retail and used-offer signals | Authenticated Creators API | High; Associates enrollment, sales eligibility, and credentials | Strong retail/offer fields | Defer |

### Google Books API

Google Books has the cleanest documented response shape in the shortlist. Its
Volumes API supports public read-only searches, including structured ISBN,
title, author, publisher, identifiers, volume links, and country-dependent sale
information. The response may include `saleability`, `listPrice`,
`retailPrice`, and a buy link. These fields describe Google eBookstore sale
context; they do not represent used-book asking prices or independent
confirmation of AbeBooks evidence.

Google's documentation says public-data requests identify the application with
an API key or OAuth token. A single bounded, unauthenticated ISBN request from
this environment returned HTTP 429. No retry loop was run. The result confirms
that PR3 should not assume reliable anonymous access, even though volume reads
do not require user authorization.

Google Books would fit a metadata/availability adapter well and could expose a
retail/list-price signal where present. It is not recommended first because:

- it would not answer the release's primary cross-market price question;
- the repository already enriches bibliographic metadata through Open Library;
- price fields are country-dependent and oriented toward the eBookstore; and
- reliable operation should use an API key and explicit quota/error handling.

Sources: [Using the Google Books API](https://developers.google.com/books/docs/v1/using)
and the [Volume resource](https://developers.google.com/books/docs/v1/reference/volumes).

### eBay Active Listings

The eBay Browse API is the strongest future live price source evaluated. It can
search active purchasable items by keyword or GTIN and returns structured item
data. Its documented resources include price, condition refinements, seller and
shipping detail, availability/end date, item identifiers, and web URLs. An ISBN
can potentially be sent as a GTIN, with title/author keyword search as a
fallback.

Browse API searches can use an application access token, but that still
requires eBay developer application credentials. eBay also documents a
production-access review for Buy APIs. No authenticated request was attempted
because PR2 must not introduce or request secrets.

Schema fit is strong for observed asking-price evidence, but implementation
would need token management, marketplace selection, pagination and rate-limit
handling, ISBN/GTIN result validation, auction-versus-fixed-price semantics,
shipping treatment, and deterministic captured fixtures. It is the preferred
later live adapter once Tom chooses to establish and maintain the required
developer access.

Sources: [eBay Browse API](https://developer.ebay.com/api-docs/buy/static/api-browse.html),
[OAuth credentials](https://developer.ebay.com/api-docs/static/oauth-credentials.html),
and [Buy API requirements](https://developer.ebay.com/api-docs/buy/buy-requirements.html).

### eBay Sold/Completed Listings

Sold/completed data would be more useful than active asking prices for observing
market-clearing behavior. However, eBay states that the Marketplace Insights
API is restricted and not open to new users. That prevents it from being the
easiest reliable next source. Consumer-page parsing is not an equivalent stable
API path and was not attempted.

The source remains a future option if access conditions change or an approved,
appropriately licensed export becomes available. Sold/completed evidence must
remain distinct from asking-price evidence and still must not be described as a
formal appraisal.

Source: [eBay Buy API marketplace support](https://developer.ebay.com/api-docs/buy/static/ref-marketplace-supported.html).

### Biblio

Biblio documents a JSON Inventory API with ISBN, title, author, publisher,
condition, signed, jacket, format, price, currency, seller, and other useful
search and result fields. That is an excellent conceptual fit for observed
asking-price rows and edition/condition review.

The API is not public. Biblio says it is reserved for affiliates and booksellers
and requires an account plus an emailed API-key request. The documentation also
labels the API beta and was last updated in 2015. PR2 could not verify current
response behavior without credentials, so recommending it first would shift
access uncertainty into PR3.

Biblio should be reconsidered if Tom already qualifies for, or wants to request,
affiliate access and Biblio confirms current terms, quotas, and permitted data
retention.

Sources: [Biblio Inventory API documentation](https://www.biblio.com/blog/2013/01/biblio-inventory-api-documentation/)
and the [Biblio affiliate program](https://www.biblio.com/affiliate-program).

### viaLibri

viaLibri documents a Search Link API that supports author, title, publisher,
ISBN in an all-text query, price bounds, currency, and sorting. It is intended
to open user-facing searches, not return machine-readable observation results.
Users must log in, and viaLibri explicitly says the API must not be used for
automated searches and that automated access will be blocked.

This makes viaLibri useful as a generated manual-research link, not as an
automated PR3 collector. A future review workflow could store the search URL as
a reference while requiring a human to enter selected comparable evidence.

Source: [viaLibri Search Link API](https://www.vialibri.net/content/search-link-api).

### BookFinder

BookFinder offers useful consumer-facing title, author, and ISBN meta-search and
can expose new and used listings. The bounded official-site review did not find
a documented public results API or supported automated integration path. Its
HTML combines and redirects to underlying marketplaces, which also creates
cross-source duplication and provenance questions.

BookFinder is deferred rather than treated as scrapeable by default. It can be
used manually, with the underlying marketplace retained as the evidence source
when a specific listing is recorded.

Source: [BookFinder search](https://www.bookfinder.com/).

### Alibris

Alibris supports consumer ISBN and title/author searches. Search results can
show asking price, condition, seller, edition/publisher detail, availability,
shipping options, and an Alibris listing identifier. Those fields fit active
asking-price observations well.

The bounded review found user-facing search documentation but no documented
public consumer inventory API. A production adapter would therefore depend on
HTML parsing and a separate terms review. Because the data is useful but the
access pattern is brittle and not clearly supported for automation, Alibris is
deferred.

Source: [Alibris search help](https://www.alibris.com/help/searching).

### Amazon Retail and Used Offers

Amazon can expose retail and offer data, including condition and price, through
affiliate APIs. However, Product Advertising API 5.0 was deprecated on
2026-05-15 in favor of Creators API. Amazon documents Creators API prerequisites
that include Associates enrollment, API registration and credentials, and at
least 10 qualifying sales in the preceding 30 days.

That eligibility and credential burden is substantially higher than a local
import path. Amazon price semantics also need careful separation among retail,
new, and used offers. The existing monthly Amazon order-history import must not
be coupled to marketplace-price access.

Sources: [Amazon Creators API prerequisites](https://affiliate-program.amazon.com/creatorsapi/docs/)
and the deprecated [PA-API request parameters](https://webservices.amazon.com/paapi5/documentation/common-request-parameters.html).

### Validated Manual/Exported Observations

A validated local import is the only evaluated path with all of these
properties today:

- no secrets, developer approval, live quota, or scraping dependency;
- ability to carry actual asking-price or sold/completed evidence;
- deterministic fixtures and tests;
- explicit source and evidence-type provenance;
- compatibility with bounded human research using eBay, Biblio, Alibris,
  BookFinder, viaLibri, auction exports, or dealer records; and
- no runtime dependency for the monthly Amazon workflow.

The tradeoff is manual effort and inconsistent source exports. PR3 should
control that risk with a narrow canonical import template and validation rather
than trying to parse many marketplace-specific export formats immediately.

## 6. Prototype Results

No prototype code was added.

One safe live probe was performed against the documented Google Books Volumes
endpoint using ISBN `9780735605589`, `maxResults=3`, no credentials, and a
20-second timeout. It returned HTTP 429. The request was not retried. This is
useful operational evidence: anonymous access cannot be assumed reliable from
the current environment, and an API-key-based implementation would need quota
and error handling.

All other findings came from official documentation and repository inspection.
No marketplace pages were crawled or parsed in bulk.

## 7. Recommended First Source

**Recommend a validated manual/exported market-observation adapter for PR3.**

The adapter should import a small source-neutral CSV whose rows name the actual
underlying source and evidence type. It is an ingestion path, not a synthetic
marketplace. A row recorded from eBay should retain `source=ebay`; a Biblio row
should retain `source=biblio`. The adapter must never use `manual` or `import` as
a substitute for the true evidence source.

Recommended evidence types:

- observed asking-price evidence;
- sold/completed listing evidence;
- retail/list-price signal; and
- metadata/availability signal.

PR3 should initially accept only asking-price rows for normalization into the
current aggregation input. Sold/completed, retail, availability, and
metadata-only inputs should remain deferred until later schema and aggregation
work can preserve and interpret them safely. They must never populate the
existing `asking_price` field ambiguously.

## 8. Why This Path Was Chosen

The manual/exported path is the easiest reliable integration because it:

- adds genuine independent price evidence when the user records or exports it;
- avoids unsupported scraping and inaccessible APIs;
- requires no secrets, affiliate status, production approval, or sales quota;
- fits deterministic, fixture-driven testing;
- lets the architecture and evidence semantics stabilize before a live adapter;
- preserves the actual source for source-diversity analysis; and
- keeps source collection optional and outside `update-library`.

It does not provide automation, and its reliability depends on validation and
human selection. That is an acceptable bounded tradeoff for PR3. It creates a
stable seam through which eBay or Biblio can later flow without redesigning the
summary layer.

The preferred first **live** marketplace remains eBay active listings because
its official API provides the best combination of structured asking-price data,
GTIN/keyword lookup, match context, and listing provenance. It should follow
only after developer credentials and production access are explicitly accepted
as an operational dependency.

## 9. Why Other Sources Were Deferred

- **Google Books:** stable schema but metadata/eBook retail context rather than
  used-market confirmation; API-key and quota behavior must be designed.
- **eBay active:** excellent data, but credentials and production approval make
  it higher-friction than PR3's no-secret target.
- **eBay sold/completed:** the relevant official API is closed to new users.
- **Biblio:** strong schema fit, but affiliate/bookseller access, manual key
  approval, and old beta documentation prevent unauthenticated verification.
- **viaLibri:** its search-link API explicitly prohibits automated searching.
- **BookFinder:** no documented public machine-results API was found, and
  meta-search duplicates complicate provenance.
- **Alibris:** useful HTML listing detail, but no documented public consumer
  inventory API was found; parsing would be brittle and needs a terms review.
- **Amazon:** Associates eligibility, credentials, recent-sales requirements,
  and an API transition create high operational friction.

## 10. Schema Implications

PR2 does not change schemas. PR3 and PR4 should consider these additions:

| Field | Purpose |
| --- | --- |
| `evidence_type` | Required semantic category: `asking_price`, `sold_price`, `retail_price`, `availability`, or `metadata_only`. |
| `source_listing_id` | Source-native listing or record identifier for audit and deduplication. |
| `source_record_date` | Date associated with the source record, distinct from collection time. |
| `sold_date` | Completed/sold date when the source supplies one. |
| `availability_status` | Active, sold, unsold, unavailable, unknown, or another controlled value. |
| `retail_price` | Retail/list-price signal kept separate from asking and sold prices. |
| `sold_price` | Completed-listing price kept separate from asking price. |
| `price_type` | Optional source-price qualifier only if `evidence_type` is not sufficiently precise. |
| `source_match_url` | Search or match URL when different from the individual listing URL. |
| `source_confidence` | Source-provided confidence only; it must remain separate from project match confidence. |

The minimum PR3 import should also require or derive:

- `catalog_id`;
- actual `source` name;
- `observation_date`;
- `evidence_type`;
- at least one of `listing_url`, `source_listing_id`, or a reviewable
  `raw_reference`;
- currency for any price;
- the price field corresponding to the evidence type; and
- match confidence and notes sufficient to explain the catalog link.

Condition, seller, listing title/author, ISBNs, edition notes, shipping, and
source record date should be supported when available. Blank optional fields
must remain blank rather than inferred.

The current Market Evidence Summary consumes `asking_price` without an evidence
type. Until PR4 and PR5 explicitly update aggregation, PR3 should emit only
validated asking-price rows into the existing observation file. Sold,
retail, availability, and metadata-only inputs should be rejected with a stable
deferred-evidence diagnostic rather than normalized into the current artifact.
They must not enter existing asking-price statistics by accident.

## 11. Operational Implications

- PR3 requires a documented CSV template and an opt-in command or library entry
  point; it must not run during monthly Amazon import.
- Input validation should fail with row-level reasons for unknown evidence
  types, missing currency, price/type mismatch, invalid dates, missing source,
  or absent provenance.
- The workflow should write generated normalized observations under `output/`
  and must not create durable market history.
- Imported rows should use deterministic observation IDs based on actual source,
  source identifier/reference, catalog item, evidence type, and relevant date.
- Duplicate rows within one import should be rejected or reported. Cross-source
  duplicates should remain reviewable until a documented rule exists.
- Unit tests should use tiny hand-authored fixtures and require no network.
- Documentation should explain that manual selection can introduce bias and
  that source diversity counts underlying sources, not file count.
- A later eBay adapter would add secret management, token refresh, production
  approval, quotas, marketplace/country configuration, and live diagnostics.

## 12. Risks and Mitigations

| Risk | Mitigation |
| --- | --- |
| Manual selection bias overstates interesting prices. | Require provenance and match notes; show source-specific counts; do not interpret a small imported set as complete market coverage. |
| A manual import is counted as an independent source. | Require the actual marketplace or evidence origin in `source`; treat import method separately from source identity. |
| Sold, retail, or metadata signals enter asking-price statistics. | Require `evidence_type`, separate price fields, and keep non-asking rows away from existing aggregation until later PRs add explicit handling. |
| Export formats vary by marketplace. | Define one canonical project template first; defer source-specific export parsers. |
| Human transcription introduces errors. | Validate types, dates, currencies, URLs/references, and required fields; emit row-level diagnostics. |
| The same listing appears through a marketplace and meta-search source. | Preserve underlying source and listing ID/URL; add explicit deduplication rules before source-diversity scoring. |
| A future live source becomes unavailable. | Keep adapters optional, emit status rows, use fixtures in tests, and never make the monthly workflow depend on a market source. |
| Google retail fields are mistaken for used-market confirmation. | Label them retail/list-price signals and exclude them from asking-price agreement. |
| Credentialed APIs create hidden user burden. | Require an explicit operational decision before adding secrets, approval, or affiliate eligibility to the project. |
| Source terms limit retention or display. | Review terms before each live adapter and retain only fields and fixtures permitted for the intended use. |

## 13. Recommended PR3 Implementation Plan

The original spike recommended a validated manual/exported observation adapter
as the lowest-friction second-source path. Product review subsequently chose to
measure the full-library AbeBooks baseline before implementing any second-source
adapter. The source recommendation remains useful, but it is deferred until the
baseline quantifies the practical review queue and evidence gaps.

Revised PR3 should be titled **Full-Library AbeBooks Baseline Workflow** and
remain bounded:

1. Reuse the existing AbeBooks collector and source-neutral Market Evidence
   Summary without changing their semantics.
2. Select every assessed catalog item, while retaining a `--limit` option for a
   safer bounded test.
3. Default to a conservative delay and document that a 3,000-book run can take
   several hours.
4. Write distinct `full_abebooks_market_observations.csv/.xlsx` outputs rather
   than replacing validation-sample observations.
5. Summarize those rows into distinct full-baseline Market Evidence Summary
   outputs.
6. Review counts by recommendation, confidence, outlier sensitivity, and
   evidence status before deciding where eBay evidence is most needed.
7. Prove that monthly import, durable records, Research Assessments, AbeBooks
   parsing, and confidence/range/review logic remain unchanged.

PR3 should not add eBay credentials, change the core AbeBooks parser, change
durable data, or teach the summary layer to compare evidence types. Those remain
later, reviewable changes.

## 14. Release Closeout

Version 0.6.0 completed the full-library AbeBooks baseline, review workbook, and
static review report without adding a second live source. The spike's eBay
findings remain the recommended next direction, now positioned as
**v0.7.0 — eBay Active Listings Integration**. v0.6.0 makes no multi-source or
completed-sale claim.

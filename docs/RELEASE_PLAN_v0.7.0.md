# Library Valuation v0.7.0 Release Plan

## 1. Release Title and Theme

**v0.7.0 — eBay Active Listings Integration**

Version 0.7.0 adds eBay active-listing evidence incrementally alongside the
existing AbeBooks baseline. eBay evidence is seller asking-price evidence only.
It is not sold/completed evidence, an appraisal, fair market value, a realized
sale price, or expected sale proceeds.

## 2. Release Objective

Validate eBay developer access, build an isolated Browse API client and
source-specific observation adapter, collect a bounded reviewer-priority cohort,
and then extend generated summaries and review artifacts without changing
durable catalog, acquisition, Research Assessment, or monthly import behavior.

The release is successful only if source provenance and evidence limitations
remain visible from API response through reviewer output.

## 3. Starting Point

v0.6.0 provides:

- durable catalog and acquisition repositories;
- Research Assessments used only as fallback priority context;
- AbeBooks observation collection and a full-library baseline;
- source-neutral Market Evidence Summary aggregation;
- conservative asking-price-derived ranges and review recommendations;
- reviewer-facing Excel and static HTML artifacts; and
- a strict generated-output versus durable-data boundary.

v0.7.0 must preserve those behaviors while introducing the first credentialed
market source.

## 4. Current API Direction, Subject to PR2 Verification

The first candidate is the eBay Buy Browse API
`GET /buy/browse/v1/item_summary/search`. Official eBay documentation says the
Browse API can search active items by keyword, GTIN, category, product, and
filters. Browse methods require an Application access token obtained through
the OAuth client-credentials grant flow. The search endpoint supports a sandbox
host, but sandbox behavior and available data must be tested rather than assumed
to represent production search quality.

The implementation spike must verify the exact scope shown for the project's
keyset, production eligibility, marketplace support, response fields, and terms
before code is promoted beyond a fixture-backed client.

Authoritative references:

- [Browse API overview](https://developer.ebay.com/api-docs/buy/api-browse.html)
- [Browse API developer page](https://developer.ebay.com/develop/api/buy/browse_api)
- [OAuth token types](https://developer.ebay.com/api-docs/static/oauth-token-types.html)
- [Authorization guide](https://www.developer.ebay.com/develop/guides-v2/authorization)
- [Buy API marketplace support](https://developer.ebay.com/api-docs/buy/ref-marketplace-supported.html)
- [Buy API field filters](https://developer.ebay.com/api-docs/buy/static/ref-buy-browse-filters.html)
- [API call limits](https://developer.ebay.com/develop/get-started/api-call-limits)

As of planning, eBay documents a default Browse API allowance of 5,000 calls per
day for most methods. This is not a design guarantee; PR2 must record the actual
limits and any application-growth or production-approval requirements for the
configured keyset.

## 5. Scope

### In scope

- Credential and environment setup documentation.
- Application-token acquisition and safe in-memory caching.
- Sandbox and production endpoint separation.
- Bounded active-listing item-summary searches.
- ISBN/GTIN-first and title/author fallback query experiments.
- Marketplace, category, buying-option, location, and delivery filters where
  supported and empirically useful.
- An isolated source adapter that produces normalized eBay observation/status
  rows while preserving raw eBay provenance.
- A targeted collection workflow for a reviewed cohort.
- Source-specific eBay measures and multi-source review context.
- Updated generated workbook and static HTML review artifacts.
- Fixture-backed deterministic tests and redaction tests.

### Non-goals

- Sold or completed eBay listings unless a separate spike proves accessible,
  lawful, reliable API capability; even then they remain a later evidence type.
- Treating active listings as completed-sale evidence or valuation.
- Automatic full-library eBay collection in the initial release path.
- Changes to Research Assessment scoring, signals, weights, or bands.
- Changes to the monthly Amazon import or durable schemas.
- Currency conversion or automatic international price comparison.
- A JavaScript-heavy or interactively sortable report.
- A realized-sale pricing model or appraisal workflow.

## 6. Credential and Secret Handling

Credentials must come from environment variables or an explicitly documented,
local, gitignored configuration file. Proposed environment variables, subject
to PR2 confirmation, are:

- `EBAY_CLIENT_ID`
- `EBAY_CLIENT_SECRET`
- `EBAY_MARKETPLACE_ID` (initially expected to be `EBAY_US`)
- `EBAY_ENVIRONMENT` (`sandbox` or `production`)

Access tokens should be minted from the client ID/secret, cached only as needed,
and refreshed before expiration. The implementation must not require a user
authorization-code flow unless the selected endpoint is proven to require one.

Never commit or persist in generated artifacts:

- client IDs or client secrets;
- application or user access tokens;
- refresh tokens;
- `.env` files;
- authorization headers; or
- raw request/response dumps containing credentials.

Tests must prove that secrets and tokens are absent from logs, exception text,
diagnostics, fixtures, CSV/XLSX output, and report output. Errors should identify
the failing environment, operation, HTTP status, and sanitized eBay error code
without echoing headers, credentials, or token responses.

## 7. Architectural Decisions

### 7.1 Observations before combined summaries

Do not integrate eBay directly into Market Evidence Summary in the client PR.
First write and review source-specific eBay observation/status rows. Only after
the adapter contract and fixtures are stable should PR6 build a combined,
source-neutral input and extend summary semantics.

This sequencing prevents authentication, parsing, matching, and cross-source
interpretation from becoming one unreviewable change.

### 7.2 Incremental cohort before full library

Use three gates:

1. A 5–10 book smoke test spanning strong ISBNs, title/author fallback, no
   results, ambiguous editions, and source failure.
2. A bounded targeted cohort drawn from `review_for_possible_sale` plus a
   stratified sample of `manual_market_research_needed` and
   `review_edition_or_condition` rows.
3. Consider broader collection only after coverage, match quality, call cost,
   pacing, duplication, and reviewer usefulness are measured.

Do not make all 3,014 catalog items the initial eBay run. Full-library eBay
collection remains a separate reviewed decision.

### 7.3 Query strategy

Test strategies independently and preserve the selected strategy on every row:

1. ISBN-13 through the Browse API's GTIN search when supported for the chosen
   marketplace.
2. ISBN-10 as a controlled keyword/search fallback if direct GTIN behavior does
   not support it reliably.
3. Quoted or normalized title plus author keywords.
4. Book-category constraints only after marketplace-specific category IDs and
   false-negative behavior are verified.
5. Buying-option, location, and delivery filters only when their effect is
   measured and recorded.

Never silently cascade multiple searches into one indistinguishable result set.
Each attempt should retain its query, strategy, rank, and status.

### 7.4 Price and listing normalization

- Preserve item price and shipping/delivery cost separately.
- Preserve original currency; do not convert currencies.
- A derived item-plus-shipping reference may be exposed only when both parts
  are comparable and its derivation is explicit.
- Preserve fixed-price versus auction or other buying options. Auction current
  bids are not directly comparable to fixed asking prices and must not be
  pooled blindly.
- Start with one marketplace and delivery context, expected to be US, subject
  to PR2 validation.
- Preserve condition, seller context, item ID/URL, item end date, and match
  confidence when returned and permitted.
- Exclude unavailable/ended items from active-listing statistics while retaining
  a sanitized status/diagnostic row when useful.

### 7.5 Combining eBay and AbeBooks

PR6 should add source-aware interpretation in stages:

- retain source-specific listing and usable-price counts;
- retain source-specific match and evidence status;
- calculate source-specific descriptive/conservative references;
- identify whether sources are comparable by currency, edition/match context,
  buying option, and price basis;
- report agreement, conflict, or non-comparability explicitly; and
- produce a combined conservative range only if a documented rule is justified
  by fixtures and review evidence.

Do not concatenate all prices and compute a naive pooled range. A second source
must not automatically increase market confidence. AbeBooks-only output must
remain backward compatible unless an explicitly versioned schema change is
reviewed.

## 8. Proposed Observation Contract

The eBay adapter should attempt to capture:

- stable project observation ID and `catalog_item_id`;
- `source_name=ebay` and active-listing evidence type;
- environment and marketplace ID;
- collection timestamp;
- lookup strategy, normalized query, result rank, and pagination context;
- eBay item ID and permitted item URL/reference;
- listing title and subtitle/short description when useful;
- seller username or permitted seller metadata;
- item price amount and currency;
- shipping/delivery cost amount and currency when returned;
- buying option and auction/fixed-price distinction;
- condition ID/name and available item specifics;
- item location/delivery context when permitted;
- item end date or availability status;
- match confidence and match notes;
- evidence/lookup status, sanitized error code, and diagnostic note; and
- adapter/schema version.

The exact mapping must be based on captured lawful fixtures from PR2. Raw API
payloads should not be retained wholesale by default.

## 9. Generated Artifacts

Candidate generated outputs are:

- `output/ebay_active_listing_observations.csv/.xlsx`
- `output/targeted_ebay_collection_summary.csv/.xlsx`
- `output/multi_source_market_observations.csv/.xlsx`
- `output/multi_source_market_evidence_summary.csv/.xlsx`
- `output/multi_source_review_workbook.xlsx`
- `output/multi_source_review_report.html`

Names and schemas should be finalized in their owning PR. All remain generated,
ignored/untracked artifacts. They are not durable market history and must not be
read by monthly import. Tests may add only small sanitized fixtures under the
existing test-fixture convention.

## 10. Reliability and Operational Requirements

- Explicit connection and read timeouts.
- Conservative pacing with configurable delay and result limits.
- Bounded pagination; no unbounded crawling.
- Retry only transient failures, with capped attempts and backoff.
- Respect `Retry-After` and rate-limit information when provided.
- Distinguish authentication, authorization, quota, rate-limit, no-result,
  invalid-query, parse, and transport failures.
- Fail one catalog lookup without corrupting already collected rows.
- Write deterministically ordered outputs after successful bounded collection.
- Print progress and sanitized summaries without credentials.
- Document overwrite and resume behavior before any large run.
- Require an explicit production environment selection; do not silently fall
  back between sandbox and production.

## 11. Incremental PR Sequence

### PR1 — v0.7.0 Release Plan

Define scope, evidence boundaries, credential rules, staged architecture,
artifacts, tests, and release gates. No functional code or credentials.

### PR2 — eBay Access / Credential Spike

Confirm developer enrollment, application keysets, exact OAuth scope, client-
credentials token flow, sandbox/production hosts, production eligibility,
marketplace headers, terms, quotas, response fields, filters, and a tiny lawful
search. Capture only sanitized fixtures and write an explicit proceed/defer
decision. No integration with summary/report workflows.

### PR3 — eBay Active Listings Client

Implement token acquisition, endpoint/environment selection, request building,
timeouts, pacing, bounded pagination, retry/error handling, and credential
redaction behind an isolated client. Use captured fixtures; live tests remain
opt-in.

### PR4 — eBay Observation Adapter

Normalize item-summary responses and status/errors into versioned source-neutral
observation candidates. Add ISBN/title matching and confidence tests while
preserving eBay-specific provenance and price components.

### PR5 — Targeted eBay Collection Workflow

Add smoke-test and reviewer-priority cohort selection, distinct output paths,
limits, progress, overwrite/resume documentation, and coverage diagnostics.
Begin with possible-sale plus stratified manual/edition-review candidates, not
the full catalog.

### PR6 — Multi-Source Market Evidence Summary

Combine reviewed AbeBooks and eBay observation inputs, add source-specific
measures and agreement/conflict/non-comparability semantics, and define any
versioned schema changes. Preserve AbeBooks-only compatibility and prohibit
naive pooling.

### PR7 — Workbook / HTML Report Updates

Expose concise source labels, source-specific evidence context, conflicts, and
caveats without turning reviewer artifacts into technical dumps. Keep active-
listing evidence separate from sold-price claims.

### PR8 — Documentation and Release Readiness

Align README, architecture, data model, Market Intelligence, roadmap, backlog,
release notes, and acceptance evidence. Validate credentials, generated-output
boundaries, single-source compatibility, source failure, and non-appraisal
language.

## 12. Testing Strategy

- Token success, expiration, refresh, malformed response, and sanitized failure.
- Sandbox versus production host and marketplace header selection.
- Query encoding for ISBN-13/GTIN, ISBN-10, and title/author.
- Pagination, result limit, pacing, timeout, retry, quota, and rate-limit paths.
- Fixed-price, auction, item price, shipping, currency, condition, seller, URL,
  end-date, and availability normalization.
- No results, ambiguous match, ended item, partial response, parse failure, and
  source unavailable status rows.
- Secret/token absence from logs, errors, fixtures, and generated artifacts.
- Deterministic observation IDs, ordering, schemas, and output naming.
- Target-cohort selection and bounded behavior.
- AbeBooks-only regression compatibility.
- Comparable agreement, material conflict, mixed currency, buying-option
  mismatch, edition ambiguity, and non-comparability.
- Workbook/report source labels and complete non-appraisal caveats.

Unit and integration tests must not require live eBay access. Any live smoke
test must be opt-in, strictly bounded, and skipped cleanly without credentials.

## 13. Release Gates

Proceed from each stage only when:

- PR2 proves lawful, stable enough access with documented credentials and
  production assumptions;
- no credential appears in repository history, logs, errors, fixtures, or
  artifacts;
- the client and adapter have deterministic fixture coverage;
- targeted collection shows acceptable match quality and call cost;
- cross-source rules expose rather than hide conflicts and non-comparability;
- reviewer outputs retain asking-price and non-appraisal caveats;
- generated artifacts remain ignored/untracked; and
- monthly import and durable data behavior remain unchanged.

If production Browse access cannot be confirmed, stop after the spike or retain
only fixture-backed exploratory code. Do not substitute scraping or a less
appropriate API merely to satisfy the release title.

## 14. Open Questions

- Which OAuth scope is available to the actual application keyset, and does
  production access require additional approval or an Application Growth Check?
- How representative is sandbox item-summary search compared with production?
- Does GTIN search reliably match ISBN-13 across the selected marketplace?
- Which marketplace/category/delivery filters improve precision without hiding
  valid international or unusual-edition listings?
- Are seller metadata, shipping amounts, condition, end dates, and item URLs
  consistently returned and permitted for retained generated artifacts?
- Should auctions be excluded from initial statistics or shown in a separate
  source-specific measure?
- What match-quality threshold is required before eBay affects a conservative
  range or recommendation?
- Can a combined range be justified, or should v0.7.0 stop at source-specific
  ranges plus agreement/conflict guidance?
- Is broader-than-targeted collection operationally useful after reviewing API
  calls, coverage, duplicate listings, and reviewer workload?

## 15. Acceptance Criteria

PR1 is complete when:

- this release plan exists and defines scope, non-goals, architecture, staged
  rollout, artifacts, tests, and release gates;
- active listings are labeled asking-price evidence only;
- Browse API direction is documented without assuming access or exact scope;
- credential storage and redaction requirements are explicit;
- observations precede multi-source summary changes;
- the first collection is smoke-tested and targeted rather than full-library;
- generated/durable boundaries and non-appraisal caveats remain explicit;
- roadmap, backlog, architecture, and Market Intelligence reflect v0.7.0;
- no functional code, credentials, or generated output is added; and
- repository validation passes.

# Library Valuation v0.7.0 Workflow Readiness Review

## Status

**Core workflow ready for final documentation and release review.**

Production eBay access, representative listing evidence, reviewer-artifact
integration, tagging, and release publication are not claimed by this review.

## Release Scope

v0.7.0 adds an isolated, bounded eBay active-listing path:

```text
Ignored local credentials
  -> bounded eBay access/client
  -> targeted active-listing observations
  -> repeated-input multi-source summary
```

Active listings are seller asking-price evidence. They are not completed sales,
appraisals, fair market value, realized prices, or expected proceeds.

## PR Checklist Through PR6

- [x] PR1 defines the staged eBay integration and production gate.
- [x] PR2 validates sandbox OAuth and one Browse request with redacted failures.
- [x] PR3 adds an immutable, in-memory active-listings client boundary.
- [x] PR4 maps results and safe statuses to the existing 25-field observation schema.
- [x] PR5 adds explicit bounded targeted collection and ignored CSV/XLSX output.
- [x] PR6 adds repeated observation inputs and source-aware summary fields.
- [x] AbeBooks-only confidence, range, and recommendation behavior remains intact.
- [x] Workbook and HTML report integration remains deferred.

## Sandbox Access Status

Sandbox `EBAY_US` has been validated. Verified HTTPS required the local Python
environment to set `SSL_CERT_FILE` to certifi's CA bundle; verification was not
disabled. OAuth application-token acquisition and Browse item-summary requests
succeeded. Production is disabled and unverified pending eBay Marketplace
Account Deletion/Closure notification compliance.

## Targeted Collection Smoke Result

The bounded smoke run used two books, three results per book, zero delay, and
ISBN-13 queries. OAuth and both Browse requests completed. Sandbox returned:

- 2 observation rows;
- 2 `no_results` statuses;
- 0 listing URLs;
- 0 prices or currencies; and
- ignored paired CSV/XLSX files under `output/`.

This validates access, request execution, adaptation, and generated output—not
production coverage, listing quality, price quality, or match quality.

## Multi-Source Summary Smoke Result

Command:

```bash
.venv/bin/python library_pipeline.py summarize-market-evidence \
  --observations output/full_abebooks_market_observations.csv \
  --observations output/smoke_ebay_observations.csv \
  --output-csv output/smoke_multisource_market_evidence_summary.csv \
  --output-xlsx output/smoke_multisource_market_evidence_summary.xlsx
```

Safe results:

- 3,014 summary rows;
- source mix: 3,012 `abebooks_only`, 2
  `abebooks_and_ebay_active_listings`;
- 2,896 rows with priced AbeBooks listing evidence;
- 0 rows with priced eBay listing evidence;
- 0 total eBay listings and 2 total eBay status rows;
- comparability: 2,896 `single_source_currency`, 118 `no_priced_listings`;
- CSV size approximately 1.4 MB and XLSX size approximately 757 KB; and
- both generated summary files ignored/untracked.

The eBay `no_results` rows remain source-specific and do not erase AbeBooks
evidence or mean global market absence.

## Operational Sequence

1. Configure sandbox credentials in ignored `.env` and source them into the
   current shell without printing their values.
2. Optionally run `ebay-access-check` with one query and a limit no greater than 3.
3. Run `collect-targeted-ebay-observations` with explicit summary/output paths,
   a small `--limit-books`, bounded results, and conservative pacing.
4. Run `summarize-market-evidence` with repeated AbeBooks and eBay
   `--observations` inputs.
5. Interpret eBay as supplemental active-listing asking-price evidence only.
6. Keep all generated artifacts under ignored `output/`.

## Generated Artifact Policy

Credentials, tokens, authorization headers, raw API responses, `.env`, and
generated CSV/XLSX files are not committed. Generated summaries are not durable
market history and are not read by monthly import. Durable catalog, acquisition,
Research Assessment, and Collector Review data remain unchanged.

## Known Limitations

- Sandbox results are not representative of production search quality.
- Production access remains gated and unverified.
- The live sandbox sample returned no listings, prices, or currencies.
- eBay match confidence remains unknown.
- Shipping is excluded and currency conversion is not performed.
- Cross-source prices are not pooled.
- Sold/completed listing evidence is absent.
- Full-library eBay collection is absent.
- Existing workbook and HTML report projections remain AbeBooks-only.

## Release Acceptance Checklist

- [x] Sandbox credentials and requests remain isolated and redacted.
- [x] Targeted collection requires explicit bounded inputs.
- [x] Observation and summary schemas are deterministic and tested.
- [x] AbeBooks-only behavior remains backward compatible.
- [x] eBay `no_results` is source-specific.
- [x] Mixed-source currencies remain separate and non-converted.
- [x] Generated smoke artifacts remain ignored/untracked.
- [x] Automated tests and compile validation pass.
- [x] CLI help matches the documented workflow.
- [x] Non-appraisal and production-gate caveats are documented.
- [ ] Final release documentation and notes are reviewed and committed.
- [ ] Working tree is clean after the final documentation commit.
- [ ] Annotated tag and GitHub Release are created explicitly.

This readiness review does not create a tag or publish a release.

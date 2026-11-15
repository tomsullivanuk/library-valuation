# Combined AbeBooks/eBay review — November 15, 2026

The completed November 11 AbeBooks website refresh was verified on the authoritative Mini: all 2,565 active records checked, 7,303 listings, protected source data unchanged, and no estimates published. This supersedes the earlier pending-affiliate status for fresh comparisons; it does not claim API approval. The website collector is tracked separately in PR #3.

A new private, network-free comparison joins those observations with the completed November 6–9 eBay review and a fresh Mini inventory/current-value snapshot. All 2,565 records remain active, accounting for 2,723 linked copies; four unidentified inventory entries bring the physical total to 2,727.

## Proposed review packet

- 1,197 books have 1,698 supported conditional eBay ranges. Each binding, seller grade and currency stays separate; none is selected as the owned copy's grade.
- 1,983 books retain plausibly title/author-matched AbeBooks used-price context after screening. Query ISBNs are not independently returned listing ISBNs. The export lacks binding, so these offers cannot establish verified same-edition comparisons or independently support replacement values.
- 567 books have at least one proposed scenario triggering the existing 50%/USD 25 endpoint-change review threshold.
- 788 books have a price-context or large-change flag. These groups overlap; they are not additive. Context differences may reflect binding, native grade or sampling rather than a market disagreement between identical copies.
- 58 cataloged books have existing physical identity questions, consolidated from the 54-book batch checklist and 30 linked canonical checks (26 overlap). The four unlinked canonical identity checks remain separate. The physical-check export therefore contains 62 book/entry rows, with no new condition grades assigned.
- Fifteen earlier pilot identity flags remain records-reconciliation work, not automatically new owner tasks.

The mutually exclusive primary queues are 409 conditional proposals without price-context/large-change flags, 787 price-context/large-change reviews, 58 existing physical-check books, and 1,311 requiring more market evidence. One physical-check book also has a flagged conditional scenario; this explains the 788 overlapping price-review count. Conditional proposals are not ready-to-publish estimates.

## Rules and limits

A supported eBay scenario retains the prior edition-support decision and independently returned matching ISBNs; it also requires known listing binding, at least three distinct offers, observations within 30 days, and strictly less than threefold spread. Bounds and counts are recomputed. Native AbeBooks grades remain separate and are not translated into eBay grades. No source averaging, implicit currency conversion, or merging across grades/bindings occurs. Cheaper new AbeBooks offers and nonoverlapping used context flag further research, not automatic repricing.

Ranges are per-copy asking-price spreads excluding shipping, not statistical intervals, appraisals or realized proceeds. The AbeBooks collector's bounded three-result sample is not a complete market distribution. Listing count does not establish independent sellers, including across sites.

Before publication, resolve existing identity questions, choose the scenario appropriate to the copy's confirmed binding/completeness/condition, inspect large changes and context mismatches, and recheck source freshness, live identity, saved manual-review protection and conflicts. Unsupported cases retain their saved values. This packet neither publishes estimates nor changes Action Item status, holdings, acquisitions or inventory decisions.

## Reproduce and inspect

`valuation.combined_market_review` consumes private immutable input copies: `current_library.json`, `current_book_checks.json`, `ebay_comparison.json`, `abebooks_cohort.json`, `abebooks_status.json`, and `abebooks_observations.csv`.

```sh
.venv/bin/python -m valuation.combined_market_review \
  --inputs output/combined_market_review_20261115/inputs \
  --output output/combined_market_review_20261115/NEW_review \
  --as-of 2026-11-15
```

The private packet is in `output/combined_market_review_20261115/final_review/`: searchable HTML, full evidence JSON, per-scenario proposals, all-book review queues, and consolidated physical questions. Generated records and input snapshots remain outside GitHub. Source hashes and code fingerprints are retained; a second read of the Mini confirms canonical state and original comparison files unchanged. An independent validation checks every proposal bound against the prior retained eBay offers, every AbeBooks group's raw prices/native grade/currency membership, exact scope and CSV counts. Nine new synthetic tests cover stale/changed editions, corrupt bounds, duplicates, cross-currency/native-grade separation, saved-review protection, and refusal to promote query confidence into verified evidence. The isolated comparison branch passes all 859 tests (865 when tested alongside the separate owner-interface fixes). Safari search and side-by-side evidence expansion were exercised successfully.

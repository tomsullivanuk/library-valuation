# Library Valuation v0.12.0 — Private Family Library and Local Search

Released November 11, 2026.

## Included

- Mac Mini operation with startup and reboot recovery, private snapshots, external Time Machine backup and documented restore checks.
- Bounded, resumable whole-library eBay comparison review covering 2,565 catalog records, provider-reported quota accounting and a 100-request reserve. Proposed ranges and records-only adjudications are separate review outputs; existing estimates remain unchanged and physical grading remains deferred.
- An offline-tested AbeBooks adapter. Fresh AbeBooks comparisons remain pending affiliate/API approval and permitted retention terms; the valuation review is not a completed multi-source refresh.
- A private friends-and-family catalog behind Cloudflare Access email verification, currently limited to the two test addresses. Recipient fields exclude purchase history, valuations, locations and private notes.
- Personal selection lists and durable requests, with tabular review, optional messages and submission history.
- One owner workspace with values and locations alongside requests, overlapping-request checks, approval and copy assignment, pending/declined states, and permanent gift or sale transfers. Transfers preserve history and create Libib follow-up rather than claiming an automatic Libib update.
- Combined ranked keyword and local AI topic search for both recipient browsing and the owner Library. Search includes descriptions, explains matches with source excerpts and falls back to keyword matching. Owner location and market filters constrain candidates before ranking; reserved holdings remain searchable by the owner.
- Clearer identity indicators, compact controls and revised owner and recipient presentation.

## Validation

850 automated tests pass. Python compilation and whitespace checks pass. Deployment on the Mini and live Chrome owner topic search were verified. Operational evidence for invitation, authorization, revocation, reboot, backup/restore, requests and transfers is preserved in the linked project records.

## Operating boundaries

Publishing this release does not add invited users or make the catalog public. Existing two-address access remains in place. Valuation comparisons are asking-price research, not appraisals or guaranteed proceeds. No revised estimates or actual physical grades are applied by this release.

GitHub contains application code, documentation and synthetic fixtures. Private library repositories, credentials, exports, request databases, model files and generated research outputs remain outside Git. Deployments require those private resources and the documented Mini configuration; downloading the release alone does not recreate the live library. Local search dependencies are optional and separately pinned in `requirements-search-lock.txt`.

## Project records

- [Roadmap](ROADMAP.md)
- [Whole-library review](WHOLE_LIBRARY_REVIEW_RUN_20261106.md)
- [Results comparison](VALUATION_RESULTS_COMPARISON_20261109.md)
- [Offline AbeBooks adapter](ABEBOOKS_SWS_OFFLINE_ADAPTER_20261109.md)
- [Private catalog](PRIVATE_FAMILY_CATALOG_20261110.md)
- [Requests](FAMILY_REQUESTS_20261110.md)
- [Unified owner workspace](UNIFIED_OWNER_WORKSPACE_20261110.md)
- [Gift and sale transfers](GIFT_SALE_TRANSFERS_20261110.md)
- [Local search](LOCAL_SEARCH_PILOT_20261110.md)

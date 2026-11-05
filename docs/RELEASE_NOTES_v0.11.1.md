# Library Valuation v0.11.1

Released November 5, 2026. A stable checkpoint of the everyday library workspace before migration and a future whole-library valuation review.

## Included

- Completed Libib inventory reconciliation, conservative review tooling, and preserved purchase history. The Library defaults to physically inventoried books; historical records remain accessible through Reports.
- Clear catalog-record counts, Libib collection locations, ISBNs, purchase costs, description search, compact filters, and simpler book details with plain-English market evidence.
- A local background service and double-click launcher. Action Items saves completion, deferral, dismissal, reopening, and notes; individual book dispositions can be saved.
- Estimate research tasks replace generic research scores with specific next steps for books lacking usable estimates.
- Research tasks support reviewing and saving a revised per-copy value range. Saved ranges update the Library and book details, complete the task, and retain earlier ranges and original evidence.
- Guarded local writes, stale-edit checks, edition-identity checks, and rollback coverage protect saved decisions and estimates.

## Validation

603 automated tests pass. Python compilation and whitespace checks pass. The estimate workflow was also checked in a browser using disposable records, including persistence after a service restart.

## Migration checkpoint

GitHub contains application code, documentation, and synthetic test fixtures. It does not contain the private library repositories, source exports, credentials, or generated reports needed to reproduce this particular library.

Before moving to the Mac Mini, preserve a private copy of the complete `data/` directory (including `workspace_actions.json` and `reviewed_estimates.json`, if present), `input/`, and `output/` with its market-evidence files and registered reports. Preserve any other locally configured source/cache paths and required credentials separately. Do not upload these private files to the public repository. Recreate the Python environment from `requirements.txt`; do not copy the existing virtual environment.

The service listens on the local machine only. This release does not implement remote hosting, authentication, Sites deployment, or an automated whole-library valuation refresh. A Sites migration needs a separate design for private data and saved changes. Existing estimates remain asking-price research rather than appraisals or guaranteed sale proceeds.

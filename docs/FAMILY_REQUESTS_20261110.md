# Personal lists and book requests — November 10, 2026

The family site at https://library-pilot.wearyfather.org/ now has personal saved selection lists and explicit request submission. Both the Cloudflare email policy and the service allowlist remain restricted to the existing two test addresses. No additional invitation, email notification, reservation, copy allocation or inventory change is made by submitting a request.

## Recipient and owner experience

Use “Add to my list” or “Remove from my list” while browsing. “My list” shows the saved titles, an optional overall message and prior submissions. Selection changes save on the Mini; message edits have an explicit Save message button and are also saved before review. “Review request” shows the complete list before the separate “Submit requests to Tom” action. A successful receipt identifies the dated request. Saving a draft alone never submits it.

Tom signs in using the owner address to see “Owner inbox.” It displays submitted requests, requester identity, dates, book labels and messages, with a print option. A family recipient cannot access this endpoint or another recipient's draft or submissions. Requests are advisory; Tom confirms availability separately. Email notifications are not configured: the inbox, not an email, is the durable delivery mechanism.

Draft changes after a submission do not replace it. Submitting a changed saved list creates another immutable request revision with its own reference. Repeated submission of the same draft version, even with a fresh retry key after reload, returns the existing receipt rather than duplicating requests. Browser tabs use optimistic version checks to reject stale overwrites. Catalog removal or an unknown reference blocks submission rather than inventing availability. Withdrawal and owner allocation are not implemented in this step.

## Authentication, data and operations

`valuation.family_service` replaces the generic static server on the same loopback port 8877. It verifies Cloudflare's JWT signature with the fixed team JWKS endpoint, issuer, application audience, expiry and required identity claims, then checks the local email allowlist on every request. The owner inbox additionally requires the configured owner address. It never trusts a plain caller-supplied email header. Mutations require the exact origin, JSON content type and a custom same-origin header; no CORS allowance is provided. Responses are no-store with a restrictive content policy. No token or private configuration is committed.

The allowlisted catalog snapshot and private SQLite request database live under `~/library-access-pilot/state/` on the Mini, outside the web root and Git repository. The directory is mode 0700, database/config files mode 0600. The service has explicit routes and no directory/file-serving endpoint. It uses transactions for saves and submissions; each submission stores book-label snapshots and its catalog fingerprint. Source catalog, purchase history, valuations, locations and private steward notes remain excluded. Recipient-authored messages are visible only to that recipient and the owner.

The existing managed login LaunchAgent starts the service and restarts it after failures. Its working directory and Python environment are explicit. The Cloudflare tunnel remains a system service. The static-server plist backup is retained privately outside the web root for rollback; switching back must preserve the request database. No new reboot was performed for this software change; the same startup arrangement passed the preceding pilot reboot test.

The installer is `operations/family_access_pilot/install_family_service.py`. It generates the privacy-allowlisted snapshot from the authoritative Mini, verifies unchanged canonical file hashes, writes local configuration and switches the managed server. It requires the actual owner/approved email arguments; never place private configuration in Git. Catalog refresh for this service uses that installer, not the earlier HTML-only export command. Refresh preserves request history and drafts, with unavailable books rejected on submission.

Use SQLite's connection backup API to capture a consistent live database; do not copy a database during an active transaction. The private verification backup is outside the served directory. The Mini's Time Machine arrangement covers this state directory; coverage is not proof that the new state has already reached a completed backup. Restore must preserve the current database first and reconcile any newer writes.

## Verification and limits

818 tests pass on both Macs. New checks cover isolated identities, owner-only inbox endpoints, invalid JWT signatures/issuer/audience/expiry/email, CSRF rejection, missing/stale/duplicate selections, stale tabs, immutable submissions, retry idempotency, database reopening, and a SQLite backup/restore using synthetic requests. A disposable browser test added an invented book, refreshed to verify persistence, saved a message, reviewed the request and observed a durable receipt. No synthetic request was submitted into production.

The deployed service rejects forged tokens on catalog, personal-list, inbox and private-state paths. Live SQLite backup integrity and schema checks pass. Canonical hashes remained unchanged during installation; the deployed allowlist contains exactly two addresses and the snapshot contains 2,565 records. Fresh real-user list/submission and owner-inbox browser acceptance remain an owner review step, not a claimed completed live test. No real data or submitted requests are published to GitHub or Sites. Estimates are unchanged and physical grading remains deferred.

## Live sign-in repair

The first real browser acceptance exposed a Mini-specific missing system CA trust bundle: urllib could not verify TLS while fetching Cloudflare signing keys. Configured PyJWKClient with the maintained CA bundle supplied by the existing requests dependency, preserving certificate/hostname verification and JWT signature checks. Public signing-key retrieval now succeeds on the Mini. Added a regression test asserting verified TLS and friendly HTML sign-in/unavailable pages rather than raw JSON at the root. All 819 tests pass on both Macs. Verified the actual invited browser session loads “Our library,” 2,565 records and “My list (0)” with its authenticated identity. No access rules or saved request data were changed by the repair.

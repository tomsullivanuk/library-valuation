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


The [unified owner workspace](UNIFIED_OWNER_WORKSPACE_20261110.md) supersedes the
separate Owner inbox: owner login now opens Library Valuation with a Requests tab.
Approval, copy assignment, overlap checks and collection tracking are implemented
there. The family interface remains the recipient view only.

## Recipient UX and description search

The family header now persistently identifies the signed-in recipient from verified `/api/me` data. Instructions refer to Pops Sullivan, explain saved lists versus submitted requests/reservations, and put the catalog timestamp to the right. Browse and My List are prominent buttons with selected-state semantics. My List displays title, author, publication/ISBN, availability and Remove controls in a table; submitted requests use title/author/status tables and readable local dates instead of technical UUID headings. Owner fields remain excluded. No selections, messages or submissions were changed during UI verification.

With explicit owner authorization, the family privacy projection now additionally permits book descriptions from linked imported Libib inventory observations (the same source used by steward BookView.description). This supersedes earlier blanket exclusion of descriptions; private notes/raw evidence/costs/valuations/locations remain excluded. The installer builds an explicit catalog-ID-to-description map, checks canonical hashes and writes the private snapshot. It does not copy arbitrary catalog descriptions or notes. Old snapshots without descriptions remain readable through normalization; unexpected fields are rejected. Descriptions are escaped and can be opened in Browse.

Search is local keyword matching, not an AI service. It matches across book metadata and descriptions with accent, punctuation/apostrophe, case, word-order and ISBN-spacing normalization. Every query word must match, with compact ISBN/phrase matching as a fallback. No external model, embedding service, credentials, fee or additional data-sharing destination was introduced. This does not provide semantic synonyms or typo correction.

Verified live Safari recipient sign-in, the existing four-book My List table, original message and submitted transfer status. A query for “interdisciplinary” returned 17 records although no titles/authors/publishers/ISBNs contained that term; normalization also handles punctuation variants beyond the 16 exact description occurrences. Inspected a description result, cleared search, and left My List open. Snapshot has descriptions for 2,306 of 2,565 catalog records. All 839 tests pass on laptop and Mini, including explicit-description escaping/privacy coverage and existing access/isolation tests. The installer reports canonical data unchanged and exactly two allowed addresses.

## Recipient wording and direct submission follow-up

Renamed the recipient page and browser title Thomas D Sullivan Library and applied the owner's exact library/ownership/delivery instructions. Catalog updated is now right-aligned alongside the result count below Browse search. Search is hidden in My List, with Browse query preserved when switching back.

My List now offers Submit request and Continue browsing. Submit saves the currently entered optional message (blank is allowed) and submits directly, preserving optimistic draft versions and retry idempotency keys. It replaces the intermediate Save message/Review request screen. Continue browsing is non-destructive: selections remain saved and a message typed during this page visit remains in memory. The message field starts blank with Optional Message to Pops as a placeholder rather than preloading an old draft message. Existing stored draft and historical submission messages are not deleted by loading the page. Unsaved message text is not persisted across a page reload; it is saved with Submit request.

Prior submissions use one table with submitted date, book, author, status, and Message details links that expand the original message beneath the row. No owner-only fields are exposed. Original submissions and request IDs remain in private storage.

Live Safari verification confirmed the exact heading/instructions, relocated timestamp, hidden search in My List, blank message placeholder, new actions and prior-submission table. No production submit/remove/save action was taken. All 839 Python tests pass on laptop and Mini. The additional tests/family_app_ui.mjs fake-DOM runtime check verifies blank message handling, search hiding/restoration, expandable messages, non-destructive Continue browsing and the direct message-save/submit payload sequence using invented records only. JavaScript syntax and whitespace checks pass. Changes remain in PR #2.

### My List text reduction

Hide the catalog timestamp and routine autosave note in My List while keeping them in Browse. Remove the saved-choices explanatory paragraph. Submission progress, confirmations and errors remain visible when relevant. Extended the synthetic UI checks to verify these visibility rules and restoration in Browse; all runtime checks and whitespace checks pass. Deployed script only; no saved selections or requests changed.

### Browse-only introduction

Hide the top introductory instructions when My List is selected; preserve the library title, signed-in identity and navigation. Instructions remain in Browse. Catalog render tests and synthetic UI visibility/submission tests pass. Deployed with a family-service restart; no saved records changed.

### Exception-only availability

Removed My List's Availability column. Saved titles absent from the current available catalog now show a No longer available warning beneath the title; available titles have no repetitive label. Submission validation remains unchanged. Catalog render and synthetic UI checks pass; deployed without modifying saved selections or requests.

## Owner-only AI search comparison

Added an isolated local-AI/keyword comparison prototype at /owner/search-pilot, with a private 42-query replay report. Family Browse search remains unchanged until the topic results are reviewed. See LOCAL_SEARCH_PILOT_20261110.md for model pinning, privacy boundaries, replay results, startup/fallback verification, dependencies and rollout gate. No production requests or estimates were changed.

## Combined search enabled

With owner approval, Browse now uses the existing local AI plus ranked-keyword engine in one search field. It displays relevant source excerpts, preserves exact title/ISBN priority and current availability checks, ignores stale query responses, and retains keyword/basic-local fallbacks. The owner-only comparison page remains for diagnostics. Search is read-only; My List, submission, purchase and transfer records remain unchanged. See LOCAL_SEARCH_PILOT_20261110.md for rollout verification and rollback.


## Clear submitted choices from My List — November 11, 2026

A successful submission now atomically saves its immutable request and clears the sender's draft books and message, advancing the draft version. The interface reloads both draft and submissions, so My List immediately reflects the cleared draft while Prior submissions retains the requested books. Failed submissions retain the draft. Idempotent retries return the earlier request without clearing newer choices; stale windows cannot re-save the submitted draft.

The existing guest draft left behind by the reported six-book submission was cleaned only after verifying its version, references and message exactly matched the latest submitted payload. The Mini ledger was backed up first, and both original submissions remained byte-for-byte unchanged. No new request was submitted during this repair.

Validation: 854 tests pass, plus JavaScript syntax, Python compilation and whitespace checks. Coverage includes draft clearing, immutable requests, persistence/backup, failed submission retention and retry protection for newly saved choices.


## Request messages, saved decisions and sorting — November 11, 2026

My List is explicitly counted as books awaiting submission; the history heading is now Submitted requests. The recipient table sorts Submitted, Book, Author, Status and Message via keyboard-operable column buttons with direction arrows and aria-sort. Newest submissions are the default. Message sorting groups rows by whether a requester or owner message is available. Owner messages appear in each book's Message details, labelled Pops Sullivan with a timestamp; the initial requester message is retained.

Owner actions are now staged: selecting Approve enables choosing a copy, then Save decision persists the status, reservation and optional requester message together. Decline, Return to pending and Add message use the same explicit save flow. Cancel discards the staged change. Transfers retain their separate final confirmation and now accept an optional requester message too. Messages are stored with the decision event, scoped to submission and book; the guest endpoint returns only message text and timestamp, never owner values, locations, actors, copy IDs or sale proceeds. These are in-app messages; no email is sent.

The owner table adds Submitted date and sorts Submitted, Requested by, Book, Estimate, Location and Status. Estimate sorting uses the first numeric USD amount, with missing estimates last; location uses numeric-aware text ordering. Action and Assigned copy remain controls. Newest first is the default.

Both interfaces check for status updates every 15 seconds while visible and on window focus/tab return. Recipient refresh replaces only changed submitted-request rows, preserving the draft and unsaved message. Owner refresh waits while an action form or editable control is active. Sorting and filters are preserved, and owner controls do not discard a staged decision. Polling failures leave the last displayed state available; it is not an instantaneous push channel.

Validation: 856 tests pass, including scoped message history, privacy-safe API responses, invalid-message validation and stale-version rejection. Script syntax and compilation checks pass. Live owner verification confirmed Book ascending sorting and a staged approval/copy selection leaving the existing Declined decision unchanged until save; the form was cancelled without a production write.

Live Safari verification also confirmed the Submitted requests heading, “0 books awaiting submission” label and Book ascending sort. All existing request states were retained; no production decision or message was sent during verification.

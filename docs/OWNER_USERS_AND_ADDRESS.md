# Owner users, permanent address and request-history maintenance

The family library uses https://library.wearyfather.org/ and the owner workspace uses https://library.wearyfather.org/owner/. The earlier pilot hostname remains on the same protected Access application and tunnel, redirecting GET requests to the permanent origin. Old-origin writes are refused so an old browser window cannot silently save through the redirect. Cookies and request protections use the new origin; users may need a fresh email-code sign-in.

## Users

The owner workspace's Users tab provides guest creation, display-name editing, enable/disable controls, access/synchronization status, last observed guest visit, request counts, invitation instructions and administration history. The owner identity is protected and cannot be edited or disabled through these controls. Email addresses are stable request identities; changing an email means disabling the old identity and creating a new one. Existing requests and personal drafts are preserved on disable.

The registry and append-only administration events live in the existing private request database. On first initialization only, approved addresses are imported from the established service configuration. Subsequent config reloads cannot resurrect disabled guests. Access checks consult the registry on every authenticated request, including requests from an already-issued session. Names and emails never appear in the public source repository.

A new grant starts pending and locally blocked. The service updates only the configured dedicated Cloudflare email policy, verifies the resulting addresses, and activates the local guest only after successful verification. Disabling first blocks the local identity; provider failure cannot preserve application access. Retry synchronizes pending changes. Unexpected provider members, non-email include rules, removed owner access, or changed require/exclude rules stop synchronization for administrator review. These are guarded coordinated changes, not a claim of an atomic transaction across two systems. Avoid simultaneous manual edits of the managed policy in Cloudflare.

An owner can copy the library link or personalized instructions and open an email draft. No invitation is sent automatically. A disabled or pending identity is not offered invitation controls.

## Private provider connection

The account needs a token with **Access: Apps and Policies Edit**, scoped to the selected account, as described in the [Cloudflare policy API](https://developers.cloudflare.com/api/resources/zero_trust/subresources/access/subresources/policies/methods/update/). Cloudflare scopes this permission to the account, not to a single policy; application code pins its calls to the configured policy ID and preserves the other policy settings. Use a finite expiry and renew it before the date shown in Users. A provider outage or expired token prevents successful new grants; existing active guests continue normally, and local disable still denies access.

Store the token only in the Mini's private state directory, mode 0600. Configuration contains its file path, account and policy identifiers, never a browser-visible token. It is never sent to GitHub, included in command arguments, or returned by the owner API. Configure from the Mini with hidden input:

```sh
.venv/bin/python -m operations.family_access_pilot.configure_users \
  --config "$HOME/library-access-pilot/state/config.json" \
  --account ACCOUNT_ID --policy POLICY_ID --expires-on YYYY-MM-DD
```

The helper verifies the existing provider/local membership match before installing the connection. Restart the managed family service afterward. Preserve configuration, token and SQLite backups privately; restore local state and provider policy together with deliberate review of any newer changes. Catalog refresh preserves the permanent origin, redirect host, provider settings and existing guest configuration instead of overwriting them with pilot defaults.

## Archive and test cleanup

Requests offers **Archive submission** when every item is declined or transferred. It hides the submission from the normal owner inbox. **Show archived** exposes archived submissions and **Restore submission** reverses the archive. Recipient history, transfer accounting and the original submissions/events remain intact.

Deleting test history is deliberately a separate server-side operation. A preview explicitly identifies submission IDs and test recipient identities; every item must already be declined and there must be no effective transfer. The execution step checks an exact fingerprint, obtains a write reservation, creates a consistent live SQLite backup through a second read connection, validates backup integrity, and removes only the named submissions and their decisions, transfers, events and archive markers. Personal drafts, other submissions, user administration events and source catalog/inventory/purchase records remain intact.

```sh
.venv/bin/python -m operations.family_access_pilot.cleanup_test_history \
  --config PRIVATE_CONFIG --submission TEST_SUBMISSION_ID \
  --test-email TEST_ADDRESS --plan NEW_PRIVATE_PLAN.json

.venv/bin/python -m operations.family_access_pilot.cleanup_test_history \
  --config PRIVATE_CONFIG --plan REVIEWED_PRIVATE_PLAN.json \
  --execute --backup-directory NEW_PRIVATE_BACKUP_DIRECTORY
```

The requested cleanup was completed against explicitly identified test records after the private backup and new-address owner sign-in. Private completion receipts record database integrity, removed counts and unchanged canonical library hashes; request details and backups stay outside GitHub. No real guest invitation was sent during implementation.

## Verification and boundaries

The final laptop suite passes 878 tests. The affected administration/service tests also run on the Mini. JavaScript syntax and Python compilation checks pass.

Tests cover guest/owner route isolation, stale edits, owner lockout prevention, individual-address validation, concurrent initialization, provider failure and retry, rejection of policy drift, retained native policy settings, immediate local disable, protected-origin redirects, archive/restore behavior, selective cleanup, concurrent/new request preservation and validated backup recovery. Browser checks exercised synthetic guest creation and invitation instructions, then verified the real owner Users page, display-name save, connected status and request-history cleanup.

The live connection was verified with a provider GET and matching memberships. An optional same-payload policy PUT test was blocked by automatic approval review and was not performed. Real add/disable operations were not exercised against production identities; those flows were tested with isolated synthetic users and a simulated provider. The application's existing guest identities and protected owner remained active throughout.

## Invitation layout and connection settings

Prepare invitation opens one full-width panel beneath the selected guest. The editable message expands to show its content; Copy invitation and Open email draft use the current edited text. Close returns focus to the guest’s invitation control. No email is sent automatically.

Settings contains connection status and the renewal date. Users shows a renewal reminder only within 30 days of expiry (or after expiry). Browser checks verified the single-panel behavior, edited draft link and live Settings details.

## Bulk request approvals

In Requests, filter to the requester and Pending, then Select All (only matching pending requests) or use individual checkboxes. Approve selected stages the decisions without saving. Available single-copy books are assigned automatically; books with multiple inventory copies require an explicit choice even when only one remains available. Reserved/transferred copies are disabled.

One optional message applies to every saved selection and remains in each book’s requester-visible history. Save ready approvals saves only assigned selections; unassigned or failed requests remain selected with the message retained. Each save uses the existing version and reservation checks; this is a sequence of individually committed approvals, so a conflict does not undo other successful approvals. Clear All abandons staged selections. No live requests were approved during implementation.

Decline selected stages the same pending selections for decline with a shared optional message. Copy fields are disabled and no assignment is required. Save declines is the only step that persists those decisions. Switching between Approve selected and Decline selected preserves the message; Clear All cancels the staged selection. Isolated browser verification saved three synthetic declines without copy assignments; production requests were not changed.

## Storage picking list

Requests → choose Requested by → Picking list produces a read-only list of all saved approved requests for that person, independent of status/search filters. It groups by assigned-copy location in numeric order, then title, and includes author, assigned copy, pull checkboxes, timestamp and totals. Print / Save PDF uses the browser print dialog. Checkboxes are temporary and do not record transfer or change inventory. With Everyone selected, each book also shows its requester.

## Bulk permanent handover

Filter Requests to Approved and the requester, select the books actually handed over, then Transfer selected. The existing assigned copies are retained and locked. Choose Gift or Sale, enter one optional shared message, and check the permanent-handover confirmation before Save transfers. Pulling books from storage alone is not a transfer. Bulk sales record no proceeds; use individual transfers when recording sale amounts.

Each save uses existing version checks and transfer accounting. Successful transfers refresh the active library; partial failures remain selected and offer Refresh library after transfers. Library/purchase history and correction records are preserved; Libib still requires a separate update. Browser verification used synthetic requests only, including blocked save without handover confirmation and three confirmed transfers. Full suite: 878 passing.

## Owner Library request status

Library cards combine current Requested by / Reserved for / Transferred to summaries with any separate saved disposition. Book details list pending requesters, each inventory copy’s reservation or transfer, and the count of unassigned copies. Names come from the private user registry, falling back to email. Archived submission decisions remain visible in copy history. The display reads existing owner-only APIs and never rewrites dispositions, requests, inventory or purchase records.

Status refreshes on entering Library/book views and periodically while visible, avoiding focused form inputs. Offline/unavailable status is explicitly noted in book details. Browser verification checked the real approved reservation read-only; synthetic checks verified one reserved and one available copy alongside an unchanged saved Keep disposition.

Library’s Request status filter offers Requested (pending), Reserved (approved), Transferred, and Any request status. A title can match multiple statuses when different copies or requests have different states. Transferred/Any explicitly includes transferred titles outside the current physical inventory; All retains the present-inventory default. The filter combines with search, location and market filters, affects CSV row selection, and resets with Clear. Synthetic matching checks cover all states and transferred inclusion; live browser verification checked Reserved and Transferred results.

## Owner-created picking lists

Library cards have Select for picking checkboxes and controls to Select visible books, Clear selection, and Add selected to picking list. Book details also offer Add to picking list. The dialog supports For myself, For someone else (active existing users only), or Pull for review. Each title needs an available inventory copy; a single available inventory copy is preselected only when it is the title’s sole copy.

Self/other picks create approved reservations using the existing request ledger. Review picks create a labelled pending owner review entry with a suggested copy and no reservation. Requests → Picking list includes approved reservations and open review picks, grouped by copy location; a review pick warns if its suggested copy has since been assigned. Decline a review entry to remove it from future picking reports. Existing guest drafts and saved dispositions are untouched. Owner-created selections are idempotent and all-or-nothing; current reservations are checked under a database write lock. No access grants or invitations are created.

The copy selector offers All available copies when an edition has multiple unassigned copies. Each physical copy gets its own reservation while repeated titles are split across compatible request submissions in one atomic transaction. Retrying the same operation cannot duplicate any layer. Existing reservations are preserved and unavailable copies cannot be selected again.

## Family topic browsing

The family Browse view now offers ten broad topics, narrower subtopics for every broad topic, and More books to explore for records without reliable assignment signals. Books may match multiple topics. Topic selection combines with both keyword and enhanced search, and persists when moving to My List and back. Counts are distinct currently requestable catalog records, not physical-copy totals, and a book can contribute to more than one topic.

Assignments use the existing metadata export’s Library of Congress classes and subject terms, with title-based fallback. ISBN is used to reject mismatched edition metadata, not as a subject code. This first pass is a browsing aid rather than completed professional cataloging; inferred topics can need correction. Rules live in valuation/browse_topics.py. No new third-party lookups are performed and canonical catalog/inventory/purchase records remain unchanged. The authenticated /api/topics response contains public topic labels and opaque family references only, not owner IDs, locations, purchase data, raw metadata or user records.

Initial audit of the completed inventory: 2,565 catalog records; 1,847 matched existing metadata after ISBN checks; 531 records had no assigned topic and remain discoverable under More books to explore. These are inventory audit counts; live family counts exclude fully reserved/transferred books. Browser checks used a synthetic family account to verify broad/subtopic filtering, search intersection, adding to My List, and returning to the same topic. No real guest lists or requests were changed.

The topic chooser labels the two levels explicitly. Narrower subjects appear in a shaded, inset panel with smaller rounded buttons and a browsing path. History & Politics includes American, ancient, European, medieval and world history, political thought, and military history where matching books exist. Other broad topics also have narrower choices; empty choices are hidden.

## Combined storage visit checklist

Open Reports → Storage visit — picks and checks by box (also linked from Requests and Action Items). The laptop layout has box navigation beside collapsible box cards; phone layouts use a horizontal box list and full-width entry cards. Large checkboxes, answer fields, per-box progress, and Next box support working at storage. Print / Save PDF still produces all boxes, including saved answers and completion indicators.

The selected visit date is remembered on the device; a fresh device uses the most recent saved current/future visit, or tomorrow in Chicago. Today is available explicitly. The list reads non-archived approved reservations, open owner review picks, and current Action Items. Book checks are included by default; optional research can be added. Completed checks saved in this visit remain visible after reload. Compound labels such as “81 and 81a” are preserved rather than inventing a precise box. Multi-location tasks share one answer and completion status.

Answers save automatically after a pause, with a Save notes button and visible save result. Check complete updates the corresponding Action Item and can be unchecked to reopen it. Pulled from storage records only visit progress; it never transfers the copy, changes inventory or releases a reservation. The current reservation and assigned slot are rechecked before pickup progress is saved. Saved entries and their events live in workspace_actions.json, keyed by visit date and stable task or submission/reference/slot identifiers, alongside existing action decisions. Existing dispositions and inventory records are preserved. The existing owner authentication, request token, write lock, global revision check, and atomic publication apply to every save. A stale device cannot silently overwrite newer work.

An internet connection is required to open the current checklist and synchronize devices. Unsaved drafts are kept in local browser storage under a workspace-specific key; failed saves show an error and retain the draft. Reconnect, use Reload latest, then Save notes. If the saved answer changed elsewhere, copy/merge the draft after reviewing the saved version. Drafts do not travel between devices until saved. Canonical action and pickup state always comes from the server, not the draft. The page is not a fully offline application. No changes are sent to requesters.

Validation includes persistence/restart and concurrent-write tests, current-copy checks, invalid-input tests, full Python suite, JavaScript syntax checks, synthetic owner browser walkthroughs (saving answers, completing checks, pickup progress, reload persistence and failed-save recovery), and responsive checks at laptop, 820px tablet, and 390px phone sizes. Live records are only viewed during rollout verification.

## Owner/family view switching and sign out

The owner header offers Family browsing, and the family view at /browse offers Return to Owner workspace. This is a presentation switch using the same authenticated identity: owner tools retain their existing owner-email check. My List and submissions in family browsing belong to the signed-in owner, never another recipient. The ordinary root URL still sends the owner to /owner/. The account script carries the current owner route fragment through the switch so a storage-visit user returns to the checklist; unsaved visit drafts remain in the existing workspace-specific device storage. Return targets are constrained to the local owner workspace.

Both owner and guest headers show Sign out / Switch account. It opens /sign-out, showing the current email, saved-work reminder and a final link to Cloudflare’s /cdn-cgi/access/logout endpoint. Keep browsing cancels without ending the session. After signing out, reopen the library and authenticate with the desired email; only the designated owner email grants owner tools. Logout may end other Cloudflare Access sessions under the same account. No credentials, Access policies, user grants, saved lists, requests, reservations or storage progress are changed by view navigation.

Validation covers owner/guest separation, owner personal lists, constrained return links, gateway script injection, sign-out-page persistence, script parsing and the full suite. A synthetic browser walkthrough verified a round trip from the checklist through family browsing, personal-list saving, draft retention, and sign-out cancellation. Real Cloudflare sessions were not signed out during verification.

## Pulled status follows saved storage actions

Requests now shows Approved → Pulled → Transferred. Pulled is computed from the most recently saved pickup action for the exact submission, book reference and assigned copy, across all visit dates. Existing saved pickups appear automatically; no second confirmation or data migration is required. Unchecking a pickup returns its displayed status to Approved while retaining the reservation. Transfer takes precedence. A reassignment or a new approval after reopening cannot reuse an old pickup; approval messages preserve the pickup status.

The request ledger retains the approval/reservation and its version; its API includes a composed `decision.status` for display and filtering. This avoids duplicating pickup state across two stores. Reservation exclusivity, transfer validation and inventory/disposition behavior remain unchanged. Owner Requests, assigned-copy labels, owner Library labels/filters and the recipient’s request status use the same composed status. Pulled requests remain eligible for individual and bulk handover. The printing-only picking report lists approvals still awaiting a pull; its paper boxes are static, and pickups are recorded in the working Storage visit checklist.

The working checklist initializes pickup checkmarks from current Pulled status even when a different visit date is selected. Changes remain saved through the existing protected storage-visit endpoint. Validation covers existing pickups, latest-action ordering across visit dates, undo, copy/request isolation, continued reservations, reapproval/reassignment, messages, transfer precedence and recipient privacy. A synthetic browser walkthrough verified checkbox → Saved → Pulled in Requests, an untouched Approved book, filtering and bulk-transfer eligibility. Real handovers are never performed as tests.

## Applying reviewed storage answers to catalog records

Physical binding confirmations can select a binding-specific ISBN already supported by preserved source-page evidence. Apply only the reviewed ISBN-10 and normalized ISBN-13 fields to the existing catalog IDs; preserve titles, publication metadata, fingerprints, holdings, reservations, estimates and dispositions. Preserve confirmed binding and the original comment in the durable follow-up review, since the fixed catalog schema has no binding field. Refresh the allowlisted family snapshot by stable reference so its identifiers agree.

When part of a check is resolved but an identifier or edition issue remains, a `remaining_question` on the canonical follow-up review narrows the current prompt after reconciliation-derived identity questions are assembled. Original question/evidence and comments remain intact. Update the saved action fingerprint to the reviewed question and leave the action Open; resolved answers stay Complete. Retain prior state, a reviewed plan, changed fields and a review event in the private workspace review audit. Catalog and action changes share the existing workspace file lock and rollback-capable publication mechanism. Validate against the live action snapshot after restarting the workspace.

## Remaining / Done / All picking views

Requests now has one Picking list / Storage visit entry point, using the same saved checklist instead of a separate paper-only report. The Show control defaults to Remaining: unpulled approved copies, unfinished review picks and open checks due by the visit date. Done shows saved pulled copies and completed checks; All shows both. Completed checks remain reviewable independently of the date on their original visit. Transferred requests are excluded from active picking work.

The Requested by control narrows pulls to that requester and retains checks in the boxes containing their active picks. Box navigation, progress counts and Next box follow the scope and visibility. Saving an item as done removes it from Remaining without rebuilding other answer editors. A global Saved message confirms the result even after that row is hidden. Printing expands box details but respects hidden rows and boxes; the printed overview states the selected view and requester. Changing the visit date returns the view to Remaining.

Validation used synthetic approvals, an existing saved pull, completed/open checks in shared and unrelated boxes, and a second requester. Browser checks covered default Remaining, Done, All, requester scope, keeping related checks, and removal after a successful save. Live pickup and handover records were not modified as tests.

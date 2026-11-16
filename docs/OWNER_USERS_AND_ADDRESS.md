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

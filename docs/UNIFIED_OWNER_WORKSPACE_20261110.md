# One owner workspace — November 10, 2026

The owner operates from the existing Library Valuation workspace, with a new Requests tab alongside Library, Action Items, Reports and Settings. The family-facing site is only the recipient interface. The earlier family Owner inbox is superseded; owner sign-in at https://library-pilot.wearyfather.org/ redirects to `/owner/`, which presents the existing steward workspace rather than a second owner application. The same Requests tab is available through the private local steward connection.

## Owner workflow

Requests show requester identity, original submission/message, current estimate, location, recorded physical-copy choices, current decision and other requesters for the same book. Values use the same market presentation and identity-checked saved estimate review as the steward workspace; no new valuation is inferred. The book title opens the existing book detail route within the same workspace.

- Pending: leave a request undecided, releasing any previous reservation.
- Declined: record the decision and release any previous reservation.
- Approved: explicitly assign an eligible recorded copy. No automatic first-come allocation.
- Collected: available only after approval and assignment, with a separate physical-collection confirmation. It records that this copy has left the library; it cannot be silently reverted through the ordinary decision controls.

Copies within a multi-copy holding use numbered units of that recorded quantity; these labels distinguish allocation slots, not newly verified identifying marks. The owner still checks the physical book when handing it over. Unknown or stale inventory links cannot be assigned. A unique transactional assignment constraint prevents two requests receiving the same unit. Version checks reject stale decisions. Overlap flags count other requesting people, not repeat submissions by the same person.

## Authority, availability and history

The existing private SQLite request store now also holds request decisions and append-only decision/collection events. This is the operational reservation and collection ledger on the authoritative Mini. Original Libib observations/holdings and acquisition records remain unchanged as historical evidence. Source inventory is not rewritten to pretend a later collection was part of the original inventory.

Approved and collected units are excluded from family availability. Titles with no remaining unassigned units disappear from newly loaded family browsing, and stale draft submissions fail validation rather than promise availability. Personal receipt statuses expose only pending/approved/declined/collected, not copy locations, valuations, other recipients or private ledger details.

Collection events overlay current steward copy counts, physical-book totals and active catalog scope. Collection triggers a workspace reload so its Library view reflects the updated counts. Estimates and purchase history are preserved; the historical “all records” reporting scope remains available. A mistaken collection requires explicit reconciliation rather than erasing the event. No real request was approved, declined or collected during rollout verification.

## Security and routing

The existing Cloudflare and local signed-identity allowlists remain the same two test addresses. Every `/owner/` page, script, report and API request requires the configured owner identity before a fixed loopback connection to the original steward service. Family identities cannot retrieve private book models or owner state, even by guessing owner paths. The original loopback service keeps its host/origin checks and workspace mutation token. Remote owner writes additionally require the exact external origin; the bridge forwards only to the fixed local service, not arbitrary destinations. Inline workspace scripts receive a fresh content-policy nonce.

The owner-only request routes are served by the existing steward process and operate on the same request database as the family service. There is no public access-policy change and no shared bypass token. The family HTML/JSON remains privacy-allowlisted. Private request data, backups, local configuration and original catalog records remain outside GitHub and Sites.

## Verification and operation

823 tests pass on laptop and Mini. New tests exercise overlapping people, copy exclusivity, approval/release/collection transitions, stale versions, unknown assignments, irreversible collection events, current-count overlays without source mutation, and restoring allocation locks/history from a SQLite backup. Guest identities are denied all owner pages and mutation routes. Existing JWT, CSRF, draft isolation, submission persistence and privacy checks continue to pass.

A pre-upgrade SQLite backup passed integrity verification. Live owner Chrome sign-in redirected to the existing Library Valuation workspace; Requests displayed the real pending submission, current estimate/location and both recorded copy options. No real decision control was activated. The retained real request and decision-event count were checked after deployment. The main launch-managed library service and separate family gateway were restarted; the installer now retries bounded launchd bootstrap failures while the previous process exits. No additional machine reboot was performed for this change.

The ledger and configuration remain under `~/library-access-pilot/state/`, already included in the Mini's Time Machine scope. Use SQLite backup for a consistent restore point and preserve newer request/collection events before recovery. The previous pilot established automatic-login-then-lock recovery; this update preserves that startup arrangement. Physical grading remains deferred and estimates are unchanged.

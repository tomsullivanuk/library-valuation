# Private read-only library — November 10, 2026

Published at https://library-pilot.wearyfather.org/ using the existing Cloudflare Access application and Mini tunnel. The saved sole email Include rule was inspected immediately before publication and contains exactly the owner's address and the already authorized test address. No new invitees or public access were added. Personal email addresses are intentionally omitted from this public document.

`valuation.family_catalog` loads strict catalog identities and the validated completed physical inventory. It fails if the declaration is absent, catalog links are missing or identities duplicate. It constructs new recipient records using only title, author, publisher, publication year, ISBN, a hashed reference and the label “Physically inventoried.” It does not serialize the steward model. Purchase/acquisition records, valuations, locations, dispositions, descriptions, private notes, raw inventory evidence and original IDs are not exported. Descriptions are omitted deliberately because free-text privacy has not been established.

The output is one escaped, read-only HTML page with title/author/publisher/ISBN search, a result count, empty state and snapshot timestamp. There are no forms for submissions, edits, reservations, lists or requests. Presence in the completed inventory is not live availability, a reservation or a promise to give a book; the page explains that confirmation with Tom is required. Four unresolved inventory entries are not given invented catalog identities.

## Verification and publication

813 tests pass on both laptop and Mini, including projection tests for historical exclusion, missing/duplicate identities, exact allowed fields, private-data sentinels and safe HTML escaping. The export contains 2,565 catalog records. All canonical data-file hashes were unchanged during publication. The served HTML contains exactly 2,565 articles and matches the generated file hash. Only `index.html` is in the served `public/` directory. Anonymous external access still returns an authentication redirect (302). The earlier pilot verified recipient PIN access, revocation and locked-screen reboot recovery; a fresh authenticated browser walkthrough of the real catalog remains an owner review step.

The real output stays on the Mini and is not committed to GitHub or uploaded to Sites. The isolated sample LaunchAgent now serves this read-only snapshot; the original steward app remains separate. Access controls protect the complete HTML payload, not just visible fields. No API or credential is embedded. Authorized recipients can read/download the displayed catalog; it is not a DRM boundary.

Refresh manually on the authoritative Mini:

```sh
cd ~/library-valuation
.venv/bin/python -m valuation.family_catalog --data-dir data --destination /Users/wearypops/library-access-pilot/public
```

Refresh stages and atomically replaces the HTML after checking canonical hashes. Publication does not automatically refresh when the catalog changes; no recurring job was added. The pre-publication synthetic page is retained outside the web root at `~/library-access-pilot/synthetic-before-real.html` for rollback. Both local canonical records and the user-facing snapshot remain subject to the Mini's existing backup arrangement. Startup uses the already verified automatic-login/lock configuration.

Estimates remain unchanged and physical grading remains deferred. Personal selection lists, notifications and copy allocations are later work.


The November 10 [personal-list and request service](FAMILY_REQUESTS_20261110.md)
now supersedes the static-only server. Its private JSON snapshot is the current
source for browsing; use the request-service installer for refresh. The older
HTML export command alone no longer refreshes the active service.

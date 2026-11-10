# Sites external invitation pilot — November 10, 2026

Purpose: establish whether an invited family member can browse without creating a ChatGPT account. No real library data, connected apps, lists, requests or reservations are included. Three invented books support basic title/author search.

Sites project: `appgprj_6af32ec0405c8191a55089ca83d1c969`.
The account reports `external_visitor_invites_enabled: true`. Initial access is custom and owner-only, with zero external visitors. This confirms invitation capability, not account-free recipient access.

The deployed source is mirrored in `prototypes/sites-access-pilot/` for PR review. Sites uses its separate source repository; deployed source commit: `446a1980f58260ae7b53c200455167268039bc12`. The local publishing checkout is `sites/family-access-pilot/`; do not add its nested Git repository or credentials to this repository. Future updates must synchronize the reviewed snapshot and Sites source.

## Pending recipient test

Obtain a user-controlled test email not associated with ChatGPT and explicit authorization to send its invitation. Do not invent an address or contact family members. Invite only that address through Sites' native external-viewer mechanism. Do not change the audience to public or distribute a service access token.

In a signed-out browser, test: uninvited access denied; invitation redemption; whether email verification or account creation is required; access to sample books; return visit; forwarded invitation behavior; and access after revocation. Never record passwords, tokens or verification codes in the PR. Report account-free access only after observing successful authorized entry without account creation. Existing signed-in owner access is not sufficient evidence.

Decision gate: adopt Sites only if the supported recipient experience meets the account-free requirement and access can be revoked. Otherwise compare another managed host with supported email magic links. Durable isolated lists, submissions and recovery are a later test, not demonstrated by this static access pilot.

Estimates and physical grading are untouched. The user supplied and authorized a user-controlled test address. Sites accepted it as the sole external viewer (access revision 2, November 10); the address is intentionally omitted from this public PR. Recipient email delivery and redemption remain unverified.

Deployment succeeded: https://library-family-access-pilot.viridclove4.chatgpt.site . A direct browser visit displayed “Log in to access” and “Continue with ChatGPT.” This demonstrates that the ordinary site URL is gated, but does not prove what the invitation-specific redemption flow does. Account-free access remains unconfirmed pending the recipient test.

# Account-free family access pilot — November 10, 2026

The owner prefers email magic links over requiring a ChatGPT account. The Sites direct-URL test displayed a ChatGPT sign-in gate; no invitation email delivery or account-free redemption was verified. Preserve the existing private Sites pilot without widening its audience.

## Proposed next pilot

Use the same three invented books with a separately hosted application and managed passwordless authentication. Supabase Auth is a candidate, not a selected or provisioned service. Its documented default email sender is restricted to project-team addresses, so a test to an external recipient needs properly configured SMTP; do not mistake a successful authentication API call for email delivery.

First establish the owner's existing hosting/email services or set up suitable accounts. No paid service commitment or credential sharing is implied. Keep source in the existing GitHub PR. Never expose the Mini steward service or upload real library records for this test.

## Required behavior

- Only explicitly invited email addresses can enter. Disable open registration and enforce membership on the server on every protected page and endpoint, independently of authentication success.
- Show a neutral response to sign-in requests, apply provider-supported rate limits, and use fixed HTTPS redirect destinations.
- Use provider-managed expiring single-use links; avoid consuming the credential on an email scanner's preliminary visit. Confirm the selected provider's supported cross-browser and confirmation behavior before implementation.
- Keep browser sessions secure and offer sign-out. A revoked invitation must deny subsequent protected requests even if the authentication session remains valid.
- No passwords, ChatGPT account or separate recipient registration form. A provider-side identity record may still exist and must be explained accurately.
- Retain no secrets in GitHub, browser bundles, screenshots or application logs. Do not include tokens in analytics or referrers.

## Test sequence

1. Deploy the empty sign-in page and synthetic catalog behind server-enforced authorization.
2. Verify anonymous and uninvited access cannot retrieve sample catalog payloads.
3. With the already authorized test recipient, send one invitation after sender and redirect configuration are verified. Record provider acceptance separately from delivery and receipt.
4. Open from a private browser: verify mailbox access, confirm no account-creation requirement, browse and search samples.
5. Test replay, expiry, return visit, email scanning and revoked access. No public-link workaround or shared service credential.
6. Record observed outcomes in this PR before choosing the production host. Personal lists, submissions and data recovery require a subsequent durable-storage pilot.

Current status: planning and provider prerequisites only. No magic-link email has been sent, no new hosting/authentication account has been created and no real catalog data or estimates have changed. Physical grading remains deferred.

Sources: https://supabase.com/docs/guides/auth/auth-email-passwordless and https://supabase.com/docs/guides/auth/auth-smtp (checked November 10, 2026).

## Cloudflare setup progress

The owner activated Zero Trust Free in their existing Cloudflare account. The dashboard wizard configured a dedicated `Library sample pilot` application with origin `http://localhost:8877`, hostname `library-pilot.wearyfather.org`, owner plus one authorized test email, and a dedicated `library-sample-pilot` tunnel. The wizard explicitly offers email One Time PIN authentication. Personal recipient details and tunnel credentials are omitted here.

The Mini serves only the three invented books from a separate `~/library-access-pilot` directory on loopback port 8877; a local HTTP check succeeded. The original steward service and catalog are untouched. Cloudflare's official arm64 connector is staged under `~/library-access-pilot/bin/`; connector registration/service activation and end-to-end access remain pending. The sample HTTP server is a temporary pilot process, not yet a reboot-tested production service. DNS creation was confirmed by the dashboard; external availability is not yet verified.

The owner repaired connector registration using a private token prompt. Cloudflare's wizard then confirmed the dedicated tunnel deployed and the application protected. The installed daemon uses a token file; no token is retained here. The wizard did not actually enable its promised OTP provider: a direct test initially showed only Cloudflare-account login. Added the native One-time PIN provider and explicitly selected it for this sample application, preserving the email allowlist. Verified the email-entry form, requested the authorized test code, and observed the “Enter your code” confirmation with a ten-minute expiry. Actual mailbox receipt, successful code verification, sample content retrieval and revocation remain pending. A code-request confirmation is not proof of delivery or successful account-free access.

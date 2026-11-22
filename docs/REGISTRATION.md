# Library access applications

Public page: the library origin followed by `/register`. The rest of the library remains behind its existing Cloudflare Access application. A separate, more-specific Access application bypasses authentication only for `/register` and its subpaths. The gateway independently routes only a fixed set of registration endpoints before authentication; every other owner/catalog endpoint still requires its normal identity checks. Do not put a bypass policy on the root library application.

## Applicant experience

Registration is limited to U.S. mailing addresses. Collect name, email, street, optional unit, ZIP code, mailing city and state; country is stored as US without a Country field. Applicants enter ZIP first; the page suggests city/state using Zippopotam.us, preserving leading zeros and allowing ZIP+4. If several places are returned the applicant can choose, and any result can be corrected. Lookup sends only the five-digit ZIP, not name, street or email. Data is advisory (GeoNames), not USPS address validation. If lookup fails, manual entry remains available. The server rejects non-U.S. country values rather than accepting them through an alternate client.

Submitting the form never grants access. A valid new application immediately enters Pending applications. The applicant receives an acknowledgment that registration is under review and that they will receive notification of its approval status within 24 hours. No registration email click or confirmation action is needed. The owner receives the application details and review link immediately through the email queue. Cloudflare still verifies inbox possession with its one-time code at sign-in, after owner approval.

Existing guests and duplicate/declined applications receive the same generic submission response without disclosing membership or repeatedly sending mail. Duplicate submissions do not alter saved details or create repeated notifications. During upgrade, legacy applications still awaiting email confirmation are moved to pending review with their original details preserved. Queued old verification messages are cancelled, and each applicant/owner notification is queued once. Previously approved/declined records and their confirmed-email evidence remain unchanged. Old confirmation URLs show a harmless explanation; no GET or retired confirmation POST can grant access.

Public submissions have a honeypot plus durable hourly limits: five submissions per client, two per email, and thirty globally. ZIP lookup is limited to sixty per client/hour. The client identifier is HMAC-hashed using a private server secret; raw client IPs are not stored. No third-party scripts run on registration/confirmation pages. These modest-volume controls may need adjustment if readership grows.

## Owner decisions

Owner email includes name, email, postal address and a secure review link to `/owner/#users/<application-id>`. A forwarded link confers no authority: the viewer must sign in as Owner. Opening or scanning it does not decide anything. The Users page highlights that application and provides Approve/Decline buttons with confirmation and an optional note. Pending and reviewed applications retain their addresses, notes and audit events privately. New applications are labeled Registered rather than Email verified, with a review-by time 24 hours after registration. This is a manual owner review target, not automatic approval or decline. Applicants cannot read other applications.

Approval uses the existing guest-administration workflow, including Cloudflare policy verification. It stays Approving if provider synchronization fails; Retry approval resumes without sending premature or duplicate instructions. After verified access, the applicant gets a sign-in email explaining Cloudflare’s one-time code, My List and requesting books. Decline never adds or enables a user; it emails the applicant to contact the owner directly, plus any owner note. Stale decisions return a conflict, so competing tabs cannot both approve and decline.

## Private setup and delivery

Install the code, then run on the Mini:

```sh
.venv/bin/python -m operations.family_access_pilot.enable_registration
```

The helper uses the existing private Access connection, creates only the path-specific registration application and its bypass policy, checks original applications unchanged, backs up configuration/provider results privately, creates a private rate-limit salt, and enables registration in the service config. If the Access token lacks application-write permission, setup stops and the route must be configured by an administrator. Restart the family gateway after configuration changes. No postal address, access credential or application token belongs in Git.

`registration_applications`, `registration_events`, and `registration_limits` share the private request database and its backup regime. Notification outbox migration adds a per-message recipient: ordinary owner request/visitor alerts still go to the owner Gmail address; acknowledgment and decision emails go only to the appropriate applicant. These use the existing iCloud sender, encrypted SMTP, durable queue and conservative handling of ambiguous sends. Owner Settings reports aggregate email queue status. Previously prepared/sent alerts are unchanged.

Verify public form access, protected library/owner access, and synthetic submission/approval/decline before using it with real applicants. Live end-to-end email receipt and real provider grants should be verified with an owner-designated test address rather than invented public recipients.

References: [Cloudflare application-path precedence](https://developers.cloudflare.com/cloudflare-one/access-controls/policies/app-paths/), [ZIP lookup coverage/accuracy](https://docs.zippopotam.us/docs/getting-started/), [USPS ZIP and mailing-city distinctions](https://faq.usps.com/s/article/ZIP-Code-The-Basics).

## Registration emblem

The owner-supplied Thomas D. Sullivan Library & Archive emblem is stored unchanged at `valuation/assets/library-emblem.png` and served only through the fixed public `/register/emblem.png` route. Registration and confirmation pages display it with descriptive alternative text, intrinsic dimensions, and responsive CSS (380 px desktop; up to 280 px on phones). No visitor request goes to ChatGPT for branding. Source supplied by the owner: https://chatgpt.com/s/m_6b02114f80c88191b399ec4344181c59.

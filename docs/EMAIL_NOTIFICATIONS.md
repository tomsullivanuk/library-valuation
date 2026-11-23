# Owner email notifications

The family gateway reconciles new, committed requests into a private SQLite outbox every 30 seconds. Each owner alert includes the requesting email, book count, and a separate section per title with author, publisher/year, confirmed binding by location, recorded storage locations, and available/reserved/transferred copy counts at preparation time, and the current estimated resale value (including owner-reviewed estimates). Missing or unverified details are omitted. The submission note and a clear Review request link follow the books. Private inventory enrichment is confined to the owner email; recipient-facing snapshots are unchanged. If enrichment is unavailable, submission metadata still sends with a notice to check current inventory in Requests. Prepared emails are frozen for safe retries. Draft edits do not send mail. There is currently no separate guest chat facility. Repeated submissions with the same submission ID do not create additional alerts.

Guest visits to authenticated library pages are recorded once per person per local calendar day, with first/last visit times. API polling and owner activity are excluded. This measures visits, not fresh Cloudflare logins. At 8 a.m. America/Chicago, a summary covers the previous calendar day. Quiet days produce no email. Restarts catch up missed days. Initialization starts tracking now, without importing historical last-seen values or sending old request alerts.

## Book approval and decline notices

New saved owner approval/decline decisions automatically email the requester. Approval identifies the books, includes any owner message, and says “Thomas will coordinate delivery directly with you.” Decline identifies the books and includes the owner's decision message verbatim; no reason is invented when the message is blank. Only title/author and the decision note are included, not owner inventory locations or resale values.

Decisions prepared in the same worker cycle are grouped by requester and approval/decline status, reducing bulk-operation email volume. Different notes remain associated with their books; a shared note is printed once. Unchanged status edits and internal owner-pick creation events do not create notices. Later changes superseding a decision before preparation are respected. A durable event cursor and the outbox commit together; restarts do not repeat notifications. Initialization starts at the latest existing event so historical decisions are not emailed retroactively. The normal SMTP retry/uncertainty safeguards apply.

## iCloud setup (selected delivery option)

The existing domain receives mail through iCloud, while Cloudflare hosts DNS. No DNS or existing mailbox changes are needed to add an address to that established iCloud custom domain.

1. Sign in to the Apple Account that owns the wearyfather.org custom email domain. Open iCloud.com → iCloud+ → Custom Email Domain → wearyfather.org. Under your name, add `library@wearyfather.org`. If three addresses already exist, stop and review rather than deleting an existing address. This is an address on the existing mailbox, not a separate Apple Account.
2. At account.apple.com → Sign-In and Security → App-Specific Passwords, generate a password named **Library notifications**. Two-factor authentication is required. Use the same Apple Account that owns the new address.
3. On the Mac mini, open Terminal and run:

```sh
cd /Users/wearypops/library-valuation
.venv/bin/python -m operations.family_access_pilot.configure_email
```

Enter your full primary `@icloud.com` Mail address (not the Gmail Apple sign-in address or the custom alias), then paste the app-specific password at the hidden prompt. Do not paste it in chat, source code, or a command argument. The helper stores it in a private file next to the service configuration and preserves other settings. It saves an email-disabled configuration and a private configuration backup. It does not send an email.

The resulting private config object is:

```json
"email_notifications": {
  "enabled": false,
  "provider": "icloud",
  "from": "Library <library@wearyfather.org>",
  "smtp_username": "YOUR_PRIMARY_ADDRESS@icloud.com",
  "password_file": "/absolute/private/path/library-icloud-password"
}
```

4. Restart the family service so Owner → Settings → Email notifications shows iCloud and the library sender. Inspect queued items before enabling. Verify SMTP login with the stored credentials, then set enabled to true and restart. Confirm one controlled request reaches the owner inbox before considering setup complete. Sending is not verified merely by saving configuration.

Apple's endpoint is fixed to `smtp.mail.me.com:587`, using verified STARTTLS before authentication. The password is used only for outgoing mail. Changing the main Apple Account password revokes app-specific passwords, so notification delivery would need a replacement.

## Resend alternative

Resend remains supported for existing installations. Verify a sending domain using its supplied DNS records; create a scoped sending-only API key and store it in a private file. Configure `provider: "resend"`, `from`, and `api_key_file` in the private `email_notifications` object. Omitting provider preserves the original Resend behavior. Never replace unrelated mail records. Attempted emails are pinned to their original delivery provider; switching an attempted item requires manual review to avoid duplicates.

Owner request alerts and visitor reports go to `tomsullivanuk@gmail.com`. Book decision notices go to the corresponding requester. The registration workflow also sends under-review acknowledgments and decision emails to the applicant’s address; see REGISTRATION.md. If the object is absent or enabled is false, tracking and queuing continue but nothing is sent. Restart the family service after changing configuration. Check Owner → Settings → Email notifications for queue counts, then submit a controlled request and confirm its receipt. A queue collected before setup will be delivered when enabled; inspect it before enabling if setup was delayed.

The existing persistent family service runs the worker; no additional scheduler is needed. The Mac mini must be awake and the service running. Notifications delayed by downtime catch up after restart.

## Reliability and private state

New tables in the private request database: `notification_meta`, `notification_visits`, `notification_outbox`. Back these up with the request ledger. Outgoing messages and visitor addresses are private; never publish this database. A file lock serializes workers. Alerts are discovered from committed submissions so a crash between submission and queue processing cannot lose them.

Resend receives a stable idempotency key and a frozen payload for every retry. Retry delays grow from one minute to one hour. Since provider keys expire after 24 hours, attempted mail older than 23 hours is held as `needs_review` rather than risking a duplicate. Check Resend logs before manually resolving such an item. For iCloud SMTP, failed connections before sending and explicit SMTP rejections can be retried. An interrupted or uncertain send is held as `needs_review` because SMTP has no idempotency guarantee. A stable Message-ID helps investigate but is not a duplicate-prevention guarantee. Confirm recipient receipt before manually resending held items.

Provider acceptance is recorded as `sent`, not confirmed inbox delivery; check the recipient inbox and sender mailbox for bounces. Provider errors never log API keys, request notes, or response bodies.

References: [Resend idempotency](https://resend.com/changelog/idempotency-keys), [domain setup](https://resend.com/docs/dashboard/domains/introduction).

Apple references: [mail server settings](https://support.apple.com/en-us/102525), [app-specific passwords](https://support.apple.com/en-us/102654), [custom-domain addresses](https://support.apple.com/en-am/guide/icloud/mm11db96ba8e/icloud).

Owner Email History is available at `/owner/email-history` from Settings or the notification status page. It shows the recipient, subject/type, Central date/time, status, and expandable saved text, with recipient/date/status/type filters and a CSV export of every matching row (the HTML view pages at 100 rows). Only the owner may view or export it. The report covers application emails, not manually sent mail or Cloudflare login codes. Provider acceptance is not proof of inbox delivery. New records retain queue and acceptance times; legacy rows show first-attempt time or “Not recorded,” rather than inventing delivery timestamps. Sent payloads remain the source for the displayed recipient, sender, subject and body. CSV fields are escaped against spreadsheet formula execution.

Reports and Settings organization (November 23, 2026): Email History is under Reports → Communications, and its return link leads to Reports. Settings keeps Email delivery configuration/health, Guest access connection, and Workspace & data. Reports separates live Storage visit and Library catalog tools from saved snapshots. The inventory workbook has a main collection card when current; stale or unavailable files remain in the collapsed saved-report archive. Report cards use short names, a purpose, saved date/format, and one download action, with limitations/provenance in Details. Existing report files and workflow shortcuts are preserved.

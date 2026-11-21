# Owner email notifications

The family gateway reconciles new, committed requests into a private SQLite outbox every 30 seconds. Each alert includes the requesting email, titles, the submission note, and an owner Requests link. Draft edits do not send mail. There is currently no separate guest chat facility. Repeated submissions with the same submission ID do not create additional alerts.

Guest visits to authenticated library pages are recorded once per person per local calendar day, with first/last visit times. API polling and owner activity are excluded. This measures visits, not fresh Cloudflare logins. At 8 a.m. America/Chicago, a summary covers the previous calendar day. Quiet days produce no email. Restarts catch up missed days. Initialization starts tracking now, without importing historical last-seen values or sending old request alerts.

## Delivery setup on the library server

1. Create a Resend account. Verify a sending domain/subdomain under your domain using the DNS records Resend supplies (SPF/DKIM). A sending subdomain is suitable; do not replace unrelated existing mail records.
2. Choose a verified From address, for example `Library <library@notifications.example.org>` (replace with your verified domain).
3. Create a sending-only Resend API key scoped to that domain. Store it in a private file outside the repository, readable only by the service account (`chmod 600`). Never put the key in source code, GitHub, or a chat message.
4. Add the following object to the existing private family-service config, using the real absolute key-file path and From address:

```json
"email_notifications": {
  "enabled": true,
  "from": "Library <library@notifications.example.org>",
  "api_key_file": "/absolute/private/path/resend-api-key"
}
```

The recipient is fixed to `tomsullivanuk@gmail.com`. No guest receives automated emails from this feature. If the object is absent or enabled is false, tracking and queuing continue but nothing is sent. Restart the family service after changing configuration. Check Owner → Settings → Email notifications for queue counts, then submit a controlled request and confirm its receipt. A queue collected before setup will be delivered when enabled; inspect it before enabling if setup was delayed.

The existing persistent family service runs the worker; no additional scheduler is needed. The Mac mini must be awake and the service running. Notifications delayed by downtime catch up after restart.

## Reliability and private state

New tables in the private request database: `notification_meta`, `notification_visits`, `notification_outbox`. Back these up with the request ledger. Outgoing messages and visitor addresses are private; never publish this database. A file lock serializes workers. Alerts are discovered from committed submissions so a crash between submission and queue processing cannot lose them.

Resend receives a stable idempotency key and a frozen payload for every retry. Retry delays grow from one minute to one hour. Since provider keys expire after 24 hours, attempted mail older than 23 hours is held as `needs_review` rather than risking a duplicate. Check Resend logs before manually resolving such an item. Provider acceptance is recorded as `sent`, not confirmed inbox delivery; investigate bounces in Resend. Provider errors never log API keys, request notes, or response bodies.

References: [Resend idempotency](https://resend.com/changelog/idempotency-keys), [domain setup](https://resend.com/docs/dashboard/domains/introduction).

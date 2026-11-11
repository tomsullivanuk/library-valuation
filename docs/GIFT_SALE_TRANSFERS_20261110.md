# Gift and sale transfers

The owner Requests workflow reserves an explicitly selected copy through approval. Once the book is handed over, Mark transferred opens a handover form requiring Gift or Sale. Sale accepts optional USD proceeds; blank means unrecorded, not zero. Amounts must be nonnegative finite numbers with no more than two decimal places. Save transfer requires explicit physical-departure confirmation.

A transfer is terminal in the ordinary UI. It preserves the original request, recipient, assigned slot, actor, timestamp and previous decisions. Gift/sale and proceeds are stored transactionally with the transfer and append-only event. Purchase history and valuation estimates are untouched. Current steward inventory and family availability exclude the transferred copy while other copies remain. The family interface receives only the request status, not sale proceeds or owner history.

Existing collected states and events are retained verbatim for compatibility; the owner display calls these transferred without inventing gift/sale information. The new state and legacy state both retain exclusive copy allocation and current-count overlays. No production book was transferred for acceptance testing.

## Libib investigation

Sources checked November 10, 2026:

- https://support.libib.com/libib/website/library/item-overview.html — Delete Copy removes one specific copy; an item cannot have zero copies. Delete removes the item from its collection. Pro permits moving individual copies and restoring deleted items for 30 days.
- https://support.libib.com/libib/website/settings.html — CSV exports are per collection; Pro barcode exports provide per-copy barcodes.
- https://support.libib.com/rest-api/introduction.html — Pro API keys and a request every two seconds are documented.
- https://support.libib.com/rest-api/accounts.html — published navigation covers accounts, managers and patrons. No documented item/copy write endpoint was found in the reviewed public documentation. API availability alone does not establish collection synchronization capability.

For now, transfer history explicitly says Libib requires a manual update; the application performs no Libib deletion or automatic synchronization. Remove only the departed copy in its original collection; when it is the last copy, remove the item. Preserve the pre-change collection export. Do not use lending for a permanent departure. Moving to an archive collection is another possible Libib approach but would require explicitly excluding that collection from every future physical-inventory import.

Before another completed Libib snapshot is imported, reconcile transferred slots against stable source entry IDs, collection, quantities, and (where available) copy barcodes. Current numbered quantity units are allocation slots, not verified Libib barcodes. Changed quantities already require review in the completed-snapshot importer. A future reconciliation must mark departures already represented by the source snapshot so the overlay is not subtracted twice, and must flag reappearing/recreated entries rather than silently reactivate them. That import reconciliation is not automatic in this change; do not assume a new CSV snapshot is transfer-aware. No new source snapshot was imported.

A later supported item/copy API, if Libib confirms one, could support an idempotent outbound queue with exact copy matching, retries, and read-back verification. Until then, Transferred requests and their history form the owner's manual Libib follow-up list. Lending remains deferred.

## Validation

838 tests pass on the Mini and laptop, including new gift/sale, optional proceeds, amount validation, atomic rollback, exclusive assignment, transfer-count overlays, terminal-state protection and SQLite backup coverage. A private SQLite backup passed integrity checking before deployment. Both launch-managed services were restarted to use the same transfer-aware availability rules. Access remains restricted to the existing two test addresses. Estimates and physical grading remain unchanged.

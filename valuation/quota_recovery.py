"""One bounded recovery batch using only the existing conservative allowance.

This explicit operator command does not replace or rebaseline the frozen runner.
Stop its LaunchAgent first; the shared lock also prevents concurrent collection.
"""
import argparse
import fcntl
import json
import os
from pathlib import Path

from valuation import whole_library_review as whole
from valuation.ebay_access import EbayCredentials


def required_requests(folder):
    """Worst-case remaining normal calls plus 25 retry/auth attempts.

    Every pending book can require one search and ten details. Completed searches
    and details use the durable checkpoint. All attempts still hit the original
    400-attempt batch limit and the ledger's pre-dispatch 100-request reserve.
    """
    path = folder / 'collection/checkpoint.json'
    checkpoint = json.loads(path.read_text()) if path.exists() else {}
    pending = 0
    for book in whole.read_csv(folder / 'cohort.csv'):
        entry = checkpoint.get('books', {}).get(book['catalog_item_id'], {})
        if entry.get('completed'):
            continue
        search = entry.get('search')
        pending += (sum(i not in entry.get('details', {}) for i in search['item_ids'])
                    if search is not None else 11)
    return min(400, pending + 25) if pending else 0


def recover_one(root, credentials):
    root = whole.private_root(root)
    with (root / '.controller.lock').open('a') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return 'already_running'
        manifest = json.loads((root / 'manifest.json').read_text())
        status = json.loads((root / 'status.json').read_text())
        if (root / 'critical_stop.json').exists() or status['state'] == 'critical_stop':
            return 'critical_stop'
        whole.verify_frozen(root, manifest)
        pending = [b for b in manifest['batches'] if not (root / b['folder'] / 'result.json').exists()]
        if not pending:
            return 'complete'
        batch = pending[0]
        folder = root / batch['folder']
        required = required_requests(folder)
        ledger = whole.QuotaLedger(root / 'quota_ledger.json')
        quota = whole.refresh_quota(credentials, root, ledger)
        receipt = dict(at=whole.stamp(), batch=batch['number'],
                       manifest_sha256=whole.sha(root / 'manifest.json'),
                       recovery_code_sha256=whole.sha(__file__),
                       allowance_before=quota['remaining'], required_requests=required,
                       reserve=whole.RESERVE, publication='disabled', physical_grading='deferred')
        receipts = root / 'quota_recovery_receipts'
        receipts.mkdir(exist_ok=True)
        path = receipts / f'batch_{batch["number"]:03}.json'
        if not ledger.ready(required):
            receipt['outcome'] = 'insufficient_conservative_allowance'
            whole.atomic(path, receipt)
            return receipt['outcome']
        receipt['outcome'] = 'started'
        whole.atomic(path, receipt)

        def update(state, **fields):
            status.update(fields, state=state, updated_at=whole.stamp())
            whole.atomic(root / 'status.json', status)
            whole.dashboard(root)

        def charged_request(request, timeout):
            ledger.charge()
            return whole.default_request_json(request, timeout)

        def factory(c, s, save, **kwargs):
            return whole.PilotApi(c, s, save, request_json=charged_request, **kwargs)

        try:
            update('collecting', current_batch=batch['number'])
            whole.collect(folder / 'cohort.csv', folder / 'collection', credentials,
                          search_mode='used_preferred', max_results=10, request_budget=400,
                          delay=.5, api_factory=factory,
                          progress=lambda message: update('collecting', last_progress=message))
            whole.verify_frozen(root, manifest)
            whole.review_batch(folder)
            whole.verify_frozen(root, manifest)
            results = [json.loads((root / b['folder'] / 'result.json').read_text())
                       for b in manifest['batches'] if (root / b['folder'] / 'result.json').exists()]
            whole.consolidate(root, manifest)
            update('waiting_for_quota', completed_batches=len(results),
                   completed_books=sum(r['books'] for r in results),
                   requests=sum(r['requests'] for r in results),
                   current_batch=batch['number'] + 1,
                   next_attempt_at=whole.parse_time(quota['reset']) + 120)
            receipt.update(outcome='batch_complete', allowance_after=ledger.state()['remaining'],
                           canonical_unchanged=True, completed_at=whole.stamp())
            whole.atomic(path, receipt)
            return 'batch_complete'
        except Exception as error:
            # Fail closed. No arbitrary exception text or authentication material.
            receipt.update(outcome='critical_stop', error_type=type(error).__name__,
                           allowance_after=ledger.state()['remaining'])
            whole.atomic(path, receipt)
            whole.atomic(root / 'critical_stop.json', dict(at=whole.stamp(),
                         issue='quota_recovery_failure', error_type=type(error).__name__))
            update('critical_stop', issue='quota_recovery_failure')
            raise


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--credentials', type=Path, required=True)
    args = parser.parse_args()
    import certifi
    os.environ['SSL_CERT_FILE'] = certifi.where()
    credentials = EbayCredentials.from_environment(json.loads(args.credentials.expanduser().read_text()))
    print(recover_one(args.root, credentials))

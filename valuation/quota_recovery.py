"""One bounded recovery batch, optionally using an authorized fresh balance.

This explicit operator command does not replace or rebaseline the frozen runner.
Stop its LaunchAgent first; the shared lock also prevents concurrent collection.
"""
import argparse
import fcntl
import json
import os
from pathlib import Path
from urllib.parse import urlsplit

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


def recover_one(root, credentials, *, use_fresh_balance=False,
                fresh_policy='explicit_single_batch_fresh_balance', allow_partial=False):
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
        previous = ledger.state() if ledger.path.exists() else None
        quota = whole.refresh_quota(credentials, root, ledger)
        receipt = dict(at=whole.stamp(), batch=batch['number'],
                       manifest_sha256=whole.sha(root / 'manifest.json'),
                       recovery_code_sha256=whole.sha(__file__),
                       allowance_before=quota['remaining'], required_requests=required,
                       reserve=whole.RESERVE, publication='disabled', physical_grading='deferred')
        receipts = root / 'quota_recovery_receipts'
        receipts.mkdir(exist_ok=True)
        suffix = '_fresh_' + str(whole.now()).replace('.', '_') if use_fresh_balance else ''
        path = receipts / f'batch_{batch["number"]:03}{suffix}.json'
        if use_fresh_balance:
            sample = json.loads((root / 'quota_history.json').read_text())[-1]
            if (sample['reset'] != quota['reset'] or
                    not isinstance(sample.get('limit'), int) or
                    not 0 <= sample['reported_remaining'] <= sample['limit']):
                raise ValueError('Invalid fresh balance')
            receipt.update(policy=fresh_policy,
                           ledger_before_refresh=previous, provider_before=sample,
                           allowance_before=sample['reported_remaining'],
                           outcome='authorized_reconciliation_pending')
            # Persist the authorization/audit trail before increasing allowance.
            whole.atomic(path, receipt)
            quota = dict(quota, remaining=sample['reported_remaining'],
                         updated_at=whole.stamp(), reconciliation_receipt=str(path))
            whole.atomic(ledger.path, quota)
        if not ledger.ready(1 if allow_partial else required):
            receipt['outcome'] = 'insufficient_conservative_allowance'
            whole.atomic(path, receipt)
            return receipt['outcome']
        receipt['outcome'] = 'started'
        whole.atomic(path, receipt)

        def update(state, **fields):
            status.update(fields, state=state, updated_at=whole.stamp())
            whole.atomic(root / 'status.json', status)
            whole.dashboard(root)

        attempts = []

        def charged_request(request, timeout):
            ledger.charge()
            endpoint = urlsplit(request.full_url).path
            operation = ('oauth' if request.get_method() == 'POST' else
                         'search' if endpoint.endswith('/item_summary/search') else
                         'detail' if '/buy/browse/' in endpoint else 'other')
            attempt = dict(at=whole.stamp(), operation=operation, outcome='dispatched')
            attempts.append(attempt)
            whole.atomic(path.with_suffix('.requests.json'), attempts)
            try:
                result = whole.default_request_json(request, timeout)
                attempt['outcome'] = 'returned'
                return result
            except Exception as error:
                attempt.update(outcome='error', error_type=type(error).__name__,
                               http_status=getattr(error, 'status_code', None))
                raise
            finally:
                whole.atomic(path.with_suffix('.requests.json'), attempts)

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
            receipt['request_counts'] = {kind: sum(a['operation'] == kind for a in attempts)
                                         for kind in ('oauth', 'search', 'detail', 'other')}
            # Save successful collection before the optional comparison request.
            whole.atomic(path, receipt)
            if use_fresh_balance:
                try:
                    whole.refresh_quota(credentials, root, ledger)
                    after = json.loads((root / 'quota_history.json').read_text())[-1]
                    receipt['provider_after'] = after
                    receipt['same_provider_window'] = after['reset'] == sample['reset']
                    if receipt['same_provider_window']:
                        receipt['provider_decrease'] = sample['reported_remaining'] - after['reported_remaining']
                    receipt['allowance_after_comparison'] = ledger.state()['remaining']
                except Exception as error:
                    receipt['comparison_error_type'] = type(error).__name__
                whole.atomic(path, receipt)
            return 'batch_complete'
        except Exception as error:
            checkpoint_path = folder / 'collection/checkpoint.json'
            checkpoint = json.loads(checkpoint_path.read_text()) if checkpoint_path.exists() else {}
            errors = [entry.get('error', {}) for entry in checkpoint.get('books', {}).values()
                      if entry.get('error')]
            if (allow_partial and checkpoint.get('status') != 'complete' and errors and
                    errors[-1].get('http_status') == 429):
                whole.verify_frozen(root, manifest)
                receipt.update(outcome='quota_paused', allowance_after=ledger.state()['remaining'])
                whole.atomic(path, receipt)
                update('waiting_for_quota', next_attempt_at=whole.parse_time(quota['reset']) + 120)
                return 'quota_paused'
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
    parser.add_argument('--use-fresh-balance', action='store_true',
                        help='Explicitly reconcile to a fresh provider balance for this one batch only')
    args = parser.parse_args()
    import certifi
    os.environ['SSL_CERT_FILE'] = certifi.where()
    credentials = EbayCredentials.from_environment(json.loads(args.credentials.expanduser().read_text()))
    print(recover_one(args.root, credentials, use_fresh_balance=args.use_fresh_balance))

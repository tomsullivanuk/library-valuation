"""Finite whole-library controller using fresh eBay balances at batch boundaries.

The original frozen valuation/identification rules and manifest are preserved.
Local dispatch accounting enforces the 100-request cushion between API checks;
it never caps the next fresh provider balance.
"""
import argparse
import fcntl
import json
import os
from pathlib import Path
import time

from valuation import whole_library_review as whole
from valuation.ebay_access import EbayCredentials, EbayRequestError
from valuation.quota_recovery import recover_one

POLICY = 'provider_authoritative_batch_balance'
CODE = ('provider_quota_controller.py', 'quota_recovery.py')


def fingerprints():
    return {name: whole.sha(Path(__file__).parent / name) for name in CODE}


def enable(root):
    """Explicit, one-time continuation receipt; never replace an existing policy."""
    root = whole.private_root(root)
    with (root / '.controller.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        manifest = json.loads((root / 'manifest.json').read_text())
        whole.verify_frozen(root, manifest)
        path = root / 'provider_quota_policy.json'
        if path.exists():
            raise ValueError('Continuation policy already exists; preserve its audit trail')
        whole.atomic(path, dict(policy=POLICY, enabled_at=whole.stamp(),
                     manifest_sha256=whole.sha(root / 'manifest.json'),
                     code_fingerprints=fingerprints(), reserve=whole.RESERVE,
                     prior_status=json.loads((root / 'status.json').read_text()),
                     prior_ledger=json.loads((root / 'quota_ledger.json').read_text()),
                     publication='disabled', physical_grading='deferred'))


def verify_policy(root):
    policy = json.loads((root / 'provider_quota_policy.json').read_text())
    if (policy['policy'] != POLICY or policy['reserve'] != 100 or
            policy['manifest_sha256'] != whole.sha(root / 'manifest.json') or
            policy['code_fingerprints'] != fingerprints()):
        raise ValueError('Continuation policy changed')


def run(root, credentials, *, once=False, sleep=time.sleep, clock=whole.now):
    root = whole.private_root(root)
    with (root / '.provider_controller.lock').open('a') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return 'already_running'
        path = root / 'provider_controller_state.json'
        state = json.loads(path.read_text()) if path.exists() else {}

        def update(value, **fields):
            state.update(fields, state=value, updated_at=whole.stamp())
            whole.atomic(path, state)

        failures = 0
        while True:
            if (root / 'critical_stop.json').exists():
                return 'critical_stop'
            try:
                verify_policy(root)
                if state.get('next_attempt_at', 0) > clock():
                    if once:
                        return state['state']
                    sleep(min(60, state['next_attempt_at'] - clock()))
                    continue
                state.pop('next_attempt_at', None)
                result = recover_one(root, credentials, use_fresh_balance=True,
                                     fresh_policy=POLICY, allow_partial=True)
                if result == 'already_running':
                    if once:
                        return result
                    sleep(60)
                    continue
                if result == 'critical_stop':
                    return result
                if result == 'complete':
                    manifest = json.loads((root / 'manifest.json').read_text())
                    whole.verify_frozen(root, manifest)
                    whole.consolidate(root, manifest)
                    status = json.loads((root / 'status.json').read_text())
                    status.pop('next_attempt_at', None)
                    status.update(state='complete', updated_at=whole.stamp())
                    whole.atomic(root / 'status.json', status)
                    whole.atomic(root / 'completion_verification.json', dict(
                        completed_at=whole.stamp(), canonical_unchanged=True,
                        protected=whole.protected(manifest['project']), publication='disabled'))
                    whole.dashboard(root)
                    update('complete')
                    return 'complete'
                if result in {'insufficient_conservative_allowance', 'quota_paused'}:
                    quota = json.loads((root / 'quota_ledger.json').read_text())
                    next_at = whole.parse_time(quota['reset']) + 120
                    status = json.loads((root / 'status.json').read_text())
                    status.update(state='waiting_for_quota', next_attempt_at=next_at,
                                  updated_at=whole.stamp())
                    whole.atomic(root / 'status.json', status)
                    whole.dashboard(root)
                    update('waiting_for_quota', next_attempt_at=next_at)
                    if once:
                        return 'waiting_for_quota'
                    continue
                # A completed batch is not a daily-reset wait under this policy.
                status = json.loads((root / 'status.json').read_text())
                status.pop('next_attempt_at', None)
                status.update(state='between_batches', updated_at=whole.stamp())
                whole.atomic(root / 'status.json', status)
                whole.dashboard(root)
                update('between_batches')
                failures = 0
                if once:
                    return 'batch_complete'
            except Exception as error:
                failures += 1
                transient = (isinstance(error, EbayRequestError) and
                             error.status_code not in {401, 403} and
                             not (root / 'critical_stop.json').exists())
                if transient and failures <= 5:
                    update('retrying', next_attempt_at=clock() + min(1800, 60 * 2 ** (failures - 1)),
                           error_type=type(error).__name__)
                    if once:
                        return 'retrying'
                    continue
                whole.atomic(root / 'critical_stop.json', dict(at=whole.stamp(),
                             issue='provider_quota_controller_failure', error_type=type(error).__name__))
                status = json.loads((root / 'status.json').read_text())
                status.update(state='critical_stop', issue='provider_quota_controller_failure',
                              updated_at=whole.stamp())
                whole.atomic(root / 'status.json', status)
                whole.dashboard(root)
                update('critical_stop', error_type=type(error).__name__)
                return 'critical_stop'


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('enable', 'run'))
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--credentials', type=Path)
    parser.add_argument('--once', action='store_true')
    args = parser.parse_args()
    if args.command == 'enable':
        enable(args.root)
    else:
        import certifi
        os.environ['SSL_CERT_FILE'] = certifi.where()
        credentials = EbayCredentials.from_environment(json.loads(args.credentials.expanduser().read_text()))
        print(run(args.root, credentials, once=args.once))

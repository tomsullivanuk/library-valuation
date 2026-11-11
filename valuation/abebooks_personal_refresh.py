"""Read-only, paced HTML comparison refresh; no estimate publication path."""
from __future__ import annotations

import argparse
import csv
import fcntl
import hashlib
import json
import os
from pathlib import Path
import time
from datetime import datetime, timezone

from valuation.abebooks import MARKET_OBSERVATION_FIELDNAMES, collect_observations_for_sample, fetch_url
from valuation.market_evidence_summary import aggregate_market_evidence, market_evidence_summary_fieldnames


def stamp():
    return datetime.now(timezone.utc).isoformat()


def atomic_json(path, value):
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(value, indent=2))
    os.chmod(temporary, 0o600)
    temporary.replace(path)


def save_csv(path, rows, fields):
    temporary = path.with_suffix('.tmp')
    with temporary.open('w', newline='') as handle:
        os.chmod(temporary, 0o600)
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
        handle.flush()
        os.fsync(handle.fileno())
    temporary.replace(path)


def protected(project):
    paths = list((project / 'data').rglob('*'))
    paths.append(project / 'output/libib_inventory_20261020/combined_market_evidence_summary.csv')
    return {str(p.relative_to(project)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in paths if p.is_file()}


def prepare(project, root):
    from valuation.workspace_service import load_model
    if root.exists():
        raise ValueError('Choose a new output directory')
    before = protected(project)
    model = load_model(project / 'data', project / 'output')
    active = set(model.completed_inventory.catalog_item_ids)
    cohort = [dict(catalog_id=b.catalog_item_id, title=b.title, author=b.author,
                   isbn13=b.isbn13, isbn10=b.isbn10) for b in model.books
              if b.catalog_item_id in active]
    cohort.sort(key=lambda row: row['catalog_id'])
    if not cohort or len(cohort) != len({b['catalog_id'] for b in cohort}):
        raise ValueError('Invalid active inventory')
    if before != protected(project):
        raise ValueError('Source state changed during preparation')
    root.mkdir(parents=True, mode=0o700)
    atomic_json(root / 'cohort.json', cohort)
    atomic_json(root / 'protected.json', before)
    atomic_json(root / 'status.json', dict(state='prepared', total=len(cohort), updated=stamp()))


def run(project, root, *, delay=5, max_books=None, fetch=fetch_url):
    if delay < 5:
        raise ValueError('At least five seconds between requests')
    with (root / 'worker.lock').open('w') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        cohort = json.loads((root / 'cohort.json').read_text())
        baseline = json.loads((root / 'protected.json').read_text())
        checkpoints = root / 'books'
        checkpoints.mkdir(exist_ok=True, mode=0o700)
        requests = 0
        last_request = 0

        def paced(url):
            nonlocal requests, last_request
            time.sleep(max(0, delay - (time.monotonic() - last_request)))
            last_request = time.monotonic()
            requests += 1
            return fetch(url)

        state, reason, processed = 'complete', '', 0
        for book in cohort:
            checkpoint = checkpoints / (hashlib.sha256(book['catalog_id'].encode()).hexdigest() + '.json')
            if checkpoint.exists():
                saved = json.loads(checkpoint.read_text())
                if any(row['lookup_status'] == 'source_unavailable' for row in saved):
                    state, reason = 'blocked', 'Prior unavailable response requires review; no automatic retry'
                    break
                continue
            if protected(project) != baseline:
                state, reason = 'stopped', 'Protected source state changed'
                break
            rows = collect_observations_for_sample(book, fetch_html=paced,
                    observation_date=stamp(), max_results_per_book=3)
            for row in rows:
                row['seller'] = ''
            atomic_json(checkpoint, rows)
            processed += 1
            if any(row['lookup_status'] == 'source_unavailable' for row in rows):
                state, reason = 'blocked', '; '.join(row['match_notes'] for row in rows)
                break
            count = len(list(checkpoints.glob('*.json')))
            atomic_json(root / 'status.json', dict(state='running', completed=count,
                total=len(cohort), completed_batches=count // 25, requests_this_run=requests, updated=stamp()))
            if max_books is not None and processed >= max_books:
                state = 'paused'
                break
        rows = [row for path in sorted(checkpoints.glob('*.json'))
                for row in json.loads(path.read_text())]
        save_csv(root / 'observations.csv', rows, MARKET_OBSERVATION_FIELDNAMES)
        summary = aggregate_market_evidence(rows)
        save_csv(root / 'review_summary.csv', summary, market_evidence_summary_fieldnames())
        unchanged = protected(project) == baseline
        if not unchanged:
            state, reason = 'stopped', 'Protected source state changed'
        count = len(list(checkpoints.glob('*.json')))
        status = dict(state=state, reason=reason, completed=count, total=len(cohort),
            completed_batches=(count + 24) // 25 if count == len(cohort) else count // 25,
            requests_this_run=requests, observed_listings=sum(r['lookup_status'] == 'observed' for r in rows),
            source_data_unchanged=unchanged, estimates_published=False, updated=stamp())
        atomic_json(root / 'status.json', status)
        print(json.dumps(status), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['prepare', 'run'])
    parser.add_argument('--project', type=Path, default=Path.cwd())
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--max-books', type=int)
    args = parser.parse_args()
    project, root = args.project.resolve(), args.output.resolve()
    if root == project or project / 'data' == root or project / 'data' in root.parents:
        raise ValueError('Output must be separate from source repositories')
    if args.command == 'prepare':
        prepare(project, root)
    else:
        run(project, root, max_books=args.max_books)


if __name__ == '__main__':
    main()

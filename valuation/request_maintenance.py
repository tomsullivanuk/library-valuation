"""Reversible request archiving and explicitly scoped, backed-up test cleanup."""
from contextlib import closing
from datetime import datetime,timezone
import hashlib,json,sqlite3,os
from pathlib import Path
from valuation import family_requests as requests,family_owner as owner


def schema(db):
    owner.schema(db)
    db.execute('CREATE TABLE IF NOT EXISTS request_archives(submission TEXT PRIMARY KEY,actor TEXT NOT NULL,created TEXT NOT NULL)');db.commit()


def archive(db,actor,submission,archived):
    schema(db)
    if type(archived) is not bool:raise ValueError('Choose archive or restore')
    with db:
        db.execute('BEGIN IMMEDIATE')
        s=db.execute('SELECT payload FROM submissions WHERE id=?',(submission,)).fetchone()
        if not s:raise ValueError('Unknown request')
        states=[owner.decision(db,submission,b['reference'])['state'] for b in json.loads(s['payload'])['books']]
        if archived and any(s not in ('declined','transferred','collected') for s in states):raise requests.Conflict('Finish all items before archiving this submission')
        if archived:db.execute('INSERT OR REPLACE INTO request_archives VALUES(?,?,?)',(submission,actor,datetime.now(timezone.utc).isoformat()))
        else:db.execute('DELETE FROM request_archives WHERE submission=?',(submission,))
    return dict(submission=submission,archived=archived)


def fingerprint(db,ids):
    tables=('submissions','request_decisions','request_events','request_transfers','request_archives')
    rows={}
    for t in tables:
        if not db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",(t,)).fetchone():continue
        key='id' if t=='submissions' else 'submission'
        rows[t]=[dict(r) for r in db.execute(f'SELECT * FROM {t} WHERE {key} IN ({",".join("?" for _ in ids)}) ORDER BY rowid',ids)]
    return hashlib.sha256(json.dumps(rows,sort_keys=True).encode()).hexdigest()


def preview(config,ids,test_emails):
    if not ids or len(set(ids))!=len(ids):raise ValueError('Specify unique test submissions')
    with closing(requests.connect(config['database'])) as db:
        schema(db);rows=[]
        for sid in ids:
            r=db.execute('SELECT * FROM submissions WHERE id=?',(sid,)).fetchone()
            if not r or r['email'] not in test_emails:raise ValueError('Unknown or non-test submission')
            books=json.loads(r['payload'])['books']
            if any(owner.decision(db,sid,b['reference'])['state']!='declined' for b in books):raise ValueError('Every test item must be declined first')
            if db.execute('SELECT 1 FROM request_transfers WHERE submission=?',(sid,)).fetchone():raise ValueError('Effective transfers must be corrected before cleanup')
            rows.append(dict(id=sid,email=r['email'],books=len(books)))
        return dict(ids=ids,test_emails=test_emails,submissions=rows,fingerprint=fingerprint(db,ids))


def purge(config,plan,backup_dir):
    with closing(requests.connect(config['database'])) as db:
        schema(db)
        with db:
            db.execute('BEGIN IMMEDIATE')
            if fingerprint(db,plan['ids'])!=plan['fingerprint']:raise requests.Conflict('Test history changed; prepare a fresh preview')
            # A second read connection backs up the committed database while this
            # reserved write lock prevents competing changes. No live rows yet deleted.
            backup=Path(backup_dir);backup.mkdir(parents=True,exist_ok=False,mode=0o700)
            with closing(sqlite3.connect(config['database'])) as source,closing(sqlite3.connect(backup/'requests.sqlite')) as dest:
                source.backup(dest)
                if dest.execute('PRAGMA integrity_check').fetchone()[0]!='ok':raise ValueError('Backup failed validation')
            (backup/'requests.sqlite').chmod(0o600)
            (backup/'cleanup_manifest.json').write_text(json.dumps(plan,indent=2));(backup/'cleanup_manifest.json').chmod(0o600)
            for t in ('request_events','request_transfers','request_decisions','request_archives','submissions'):
                key='id' if t=='submissions' else 'submission'
                db.execute(f'DELETE FROM {t} WHERE {key} IN ({",".join("?" for _ in plan["ids"])})',plan['ids'])
    return dict(removed_submissions=len(plan['ids']),removed_requested_books=sum(r['books'] for r in plan['submissions']),backup=str(backup))

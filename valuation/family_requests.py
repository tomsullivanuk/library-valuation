"""Durable, isolated drafts and immutable book-request submissions."""
import json
import sqlite3
import uuid
from datetime import datetime, timezone

class Conflict(ValueError): pass

def connect(path):
    db=sqlite3.connect(path,timeout=10);db.row_factory=sqlite3.Row
    db.execute('PRAGMA foreign_keys=ON')
    db.executescript('''CREATE TABLE IF NOT EXISTS drafts(email TEXT PRIMARY KEY,version INTEGER NOT NULL,payload TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS submissions(id TEXT PRIMARY KEY,email TEXT NOT NULL,key TEXT NOT NULL,created TEXT NOT NULL,payload TEXT NOT NULL,UNIQUE(email,key));''')
    return db

def draft(db,email):
    r=db.execute('SELECT version,payload FROM drafts WHERE email=?',(email,)).fetchone()
    return dict(version=r['version'],**json.loads(r['payload'])) if r else dict(version=0,books=[],message='')

def save(db,email,version,books,message,catalog):
    if type(version) is not int or not isinstance(books,list) or len(books)>3000 or not isinstance(message,str) or len(message)>2000:raise ValueError('Invalid list')
    if any(not isinstance(x,str) or x not in catalog for x in books) or len(set(books))!=len(books):raise ValueError('A selected book is no longer in this catalog. Refresh before saving.')
    with db:
        db.execute('BEGIN IMMEDIATE')
        old=draft(db,email)
        if old['version']!=version:raise Conflict('Your list changed in another window. Reload before editing.')
        db.execute('INSERT OR REPLACE INTO drafts VALUES(?,?,?)',(email,version+1,json.dumps(dict(books=books,message=message))))
    return draft(db,email)

def submit(db,email,version,key,catalog,snapshot):
    if type(version) is not int or not isinstance(key,str) or len(key)>80 or not key:raise ValueError('Invalid submission key')
    with db:
        db.execute('BEGIN IMMEDIATE')
        old=db.execute("SELECT id,created,payload FROM submissions WHERE email=? AND (key=? OR json_extract(payload, '$.draft_version')=?)",(email,key,version)).fetchone()
        if old:return dict(old)|dict(payload=json.loads(old['payload']))
        d=draft(db,email)
        if d['version']!=version:raise Conflict('Your list changed. Review it again before submitting.')
        if not d['books'] or any(ref not in catalog for ref in d['books']):raise ValueError('Review your list against the current catalog before submitting.')
        payload=dict(books=[catalog[r] for r in d['books']],message=d['message'],catalog_snapshot=snapshot,draft_version=version)
        id=str(uuid.uuid4());created=datetime.now(timezone.utc).isoformat()
        db.execute('INSERT INTO submissions VALUES(?,?,?,?,?)',(id,email,key,created,json.dumps(payload)))
    return dict(id=id,created=created,payload=payload)

def submissions(db,email=None):
    rows=db.execute('SELECT id,email,created,payload FROM submissions '+('WHERE email=? ' if email else '')+'ORDER BY created DESC', (email,) if email else ()).fetchall()
    return [dict(r)|dict(payload=json.loads(r['payload'])) for r in rows]

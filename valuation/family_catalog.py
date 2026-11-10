"""Read-only allowlisted family catalog; never serializes steward records."""
import argparse
from datetime import datetime, timezone
import hashlib
import html
from pathlib import Path
import tempfile
import os

from valuation.completed_inventory import resolve_completed_inventory
from valuation.libib_catalog import StrictCatalogRepository

FIELDS = ('reference', 'title', 'author', 'publisher', 'year', 'isbn', 'availability')


def project(rows, scope):
    if not scope.completed:
        raise ValueError('A completed physical inventory is required')
    ids = set(scope.catalog_item_ids)
    selected = [r for r in rows if r['catalog_item_id'] in ids]
    if len({r['catalog_item_id'] for r in selected}) != len(selected):
        raise ValueError('Duplicate catalog identity')
    if {r['catalog_item_id'] for r in selected} != ids:
        raise ValueError('Physical inventory references missing catalog records')
    return sorted([dict(reference=hashlib.sha256(('family-v1:'+r['catalog_item_id']).encode()).hexdigest()[:20],
        title=r['title'], author=r['author'], publisher=r['publisher'], year=r['publication_year'],
        isbn=r['isbn13'] or r['isbn10'], availability='Physically inventoried') for r in selected],
        key=lambda r:(r['title'].casefold(),r['reference']))


def render(records, generated_at):
    if any(set(r) != set(FIELDS) for r in records):
        raise ValueError('Unexpected recipient-facing field')
    esc=lambda v:html.escape(str(v),quote=True)
    cards=[]
    for r in records:
        publication=' · '.join(v for v in (r['publisher'],r['year']) if v)
        cards.append('<article><h2>'+esc(r['title'])+'</h2><p>'+esc(r['author'])+'</p><p class="muted">'+esc(publication)+'</p>'
          + ('<p class="muted">ISBN '+esc(r['isbn'])+'</p>' if r['isbn'] else '')
          + '<p class="availability">'+esc(r['availability'])+'</p></article>')
    return '''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="robots" content="noindex,nofollow"><meta name="referrer" content="no-referrer"><title>Our library</title>
<style>body{max-width:1000px;margin:32px auto;padding:20px;font:17px/1.5 system-ui;color:#25372e;background:#faf9f5}h1,h2{font-family:Georgia;color:#245d49}h1{font-size:2rem}h2{font-size:1.3rem;margin:0}article{background:white;border:1px solid #d4ddd6;border-radius:10px;padding:20px;margin:14px 0}p{margin:6px 0}.muted{color:#606c65;font-size:.9rem}.availability{font-size:.85rem;color:#245d49}input{font:inherit;padding:12px;width:100%;box-sizing:border-box;border:1px solid #97a79e;border-radius:6px}header{margin-bottom:24px}[hidden]{display:none}</style>
<header><p class="muted">PRIVATE · FRIENDS & FAMILY</p><h1>Our library</h1><p>Browse the books recorded in our completed physical inventory.</p><p>This is a read-only catalog. Books shown here are not reserved or promised; availability needs confirmation with Tom.</p><p class="muted">Updated '''+esc(generated_at)+'''</p></header><label for="search">Search title, author, publisher or ISBN</label><input id="search" type="search" placeholder="Find a book…"><p id="count" role="status" aria-live="polite">'''+str(len(records))+''' catalog records</p><main>'''+''.join(cards)+'''</main><p id="empty" hidden>No matching books.</p>
<script>const input=document.querySelector('#search'),cards=[...document.querySelectorAll('article')];input.addEventListener('input',()=>{const q=input.value.toLocaleLowerCase().trim();let n=0;for(const card of cards){card.hidden=!card.textContent.toLocaleLowerCase().includes(q);if(!card.hidden)n++}document.querySelector('#count').textContent=n+' catalog records';document.querySelector('#empty').hidden=n!==0});</script></html>'''


def publish(data_dir, destination):
    data_dir=Path(data_dir).resolve();destination=Path(destination).resolve()
    if destination == data_dir or data_dir in destination.parents:
        raise ValueError('Publication must be outside canonical data')
    before={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in data_dir.iterdir() if p.is_file()}
    records=project(StrictCatalogRepository(data_dir/'catalog_items.csv').load(),resolve_completed_inventory(data_dir))
    page=render(records,datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC'))
    after={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in data_dir.iterdir() if p.is_file()}
    if before != after:raise ValueError('Canonical data changed during snapshot generation')
    destination.mkdir(parents=True,exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=destination,delete=False) as f:
        temporary=f.name;f.write(page.encode());f.flush();os.fsync(f.fileno())
    os.chmod(temporary,0o644);os.replace(temporary,destination/'index.html')
    return dict(catalog_records=len(records),canonical_unchanged=True,published_fields=list(FIELDS),
                content_sha256=hashlib.sha256(page.encode()).hexdigest())

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--data-dir',required=True);p.add_argument('--destination',required=True)
    a=p.parse_args();import json;print(json.dumps(publish(a.data_dir,a.destination)))

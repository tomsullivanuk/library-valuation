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

FIELDS = ('reference', 'title', 'author', 'publisher', 'year', 'isbn', 'availability', 'description')


def project(rows, scope, descriptions=None):
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
        isbn=r['isbn13'] or r['isbn10'], availability='Physically inventoried', description=(descriptions or {}).get(r['catalog_item_id'],'')) for r in selected],
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
          + ('<details class="book-description"><summary>Book description</summary><p>'+esc(r.get('description',''))+'</p></details>' if r.get('description') else '')
          + '<p class="availability">'+esc(r['availability'])+'</p></article>')
    return '''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="robots" content="noindex,nofollow"><meta name="referrer" content="no-referrer"><title>Thomas D Sullivan Library</title>
<style>body{max-width:1000px;margin:32px auto;padding:20px;font:17px/1.5 system-ui;color:#25372e;background:#faf9f5}h1,h2{font-family:Georgia;color:#245d49}h1{font-size:2rem}h2{font-size:1.3rem;margin:0}button{font:inherit;padding:.45rem .8rem;border:1px solid #245d49;border-radius:6px;background:white;color:#245d49;cursor:pointer}button:disabled{opacity:.55;cursor:default}button[aria-pressed="true"]{background:#245d49;color:white}.family-nav{display:flex;gap:.6rem;margin:1rem 0}.family-nav button{font-weight:600;padding:.6rem 1.1rem}.catalog-meta{display:flex;justify-content:space-between;align-items:baseline;gap:1rem;flex-wrap:wrap}.form-actions{display:flex;gap:.6rem;margin:.7rem 0}.message-details td{background:#f1f5f1;white-space:pre-wrap}.header-meta{display:flex;justify-content:space-between;gap:1rem;flex-wrap:wrap}.family-table{width:100%;border-collapse:collapse;background:white}.family-table th,.family-table td{text-align:left;vertical-align:top;padding:.7rem;border-bottom:1px solid #d4ddd6}.table-scroll{overflow-x:auto}.family-table small{display:block}.availability-warning{color:#865314;font-weight:600}.family-table button{white-space:nowrap}.family-table th button{border:0;background:transparent;padding:0;font-weight:700;text-align:left}textarea{display:block;width:100%;max-width:600px;min-height:5rem;font:inherit;margin:.4rem 0}#signed-in{font-weight:600}.book-description p{white-space:pre-line}.book-description{margin:.5rem 0}article{background:white;border:1px solid #d4ddd6;border-radius:10px;padding:20px;margin:14px 0}p{margin:6px 0}.muted{color:#606c65;font-size:.9rem}.availability{font-size:.85rem;color:#245d49}input{font:inherit;padding:12px;width:100%;box-sizing:border-box;border:1px solid #97a79e;border-radius:6px}header{margin-bottom:24px}[hidden]{display:none}</style>
<header><div class="header-meta"><p class="muted">PRIVATE · FRIENDS & FAMILY</p><p id="signed-in" role="status">Checking sign-in…</p></div><h1>Thomas D Sullivan Library</h1><div id="browse-intro"><p>Browse the library and add books you’re interested in owning to My List.</p><p>When you’re ready, open My List to review your choices and send a request to Pops Sullivan. Adding a book to your list doesn’t reserve it; Pops will confirm availability and arrange delivery with you.</p></div></header><div id="search-tools"><label for="search">Search title, author, publisher, ISBN or book description</label><input id="search" type="search" placeholder="Try a title, author, topic or phrase…"></div><div class="catalog-meta"><p id="count" role="status" aria-live="polite">'''+str(len(records))+''' catalog records</p><p class="muted updated" style="text-align:right">Catalog updated '''+esc(generated_at)+'''</p></div><main>'''+''.join(cards)+'''</main><p id="empty" hidden>No matching books.</p>
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

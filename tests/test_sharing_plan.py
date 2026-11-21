"""Exercise real candidate logic with invented copies and dispositions."""
import json
import subprocess
from pathlib import Path

from valuation.steward_workspace import _DOCUMENT


def test_sale_candidates_respect_copy_assignments_and_owner_plans():
    function = _DOCUMENT.split('    function saleCandidate(', 1)[1].split('    function renderSelling()', 1)[0]
    script = '''const activeCatalogIds = new Set(['b']);
const workspaceState = {dispositions:{}};
const dispositionValue = value => ['gift','donate'].includes(value) ? 'gift_donate' : value;
function saleCandidate(''' + function + '''
const book = {catalog_item_id:'b',copy_count:3,disposition:'undecided'};
const rows = [
 saleCandidate(book),
 saleCandidate(book,{copies:[{assignment:{}},{assignment:null},{assignment:{}}],events:[{state:'pending'}]}),
 saleCandidate(book,{copies:[{assignment:{}},{assignment:{}}],events:[]}),
 ...['keep','gift','donate','gift_donate','recycle'].map(disposition => saleCandidate({...book,disposition})),
 saleCandidate({...book,catalog_item_id:'historical'}),
 saleCandidate({...book,copy_count:0}),
];
workspaceState.dispositions.b='keep'; rows.push(saleCandidate(book));
console.log(JSON.stringify(rows));'''
    rows = json.loads(subprocess.check_output(['node', '-e', script], text=True))
    assert rows[0]['available'] == 3
    assert rows[1]['available'] == 1 and rows[1]['pending'] is True
    assert all(row is None for row in rows[2:])


def test_generated_client_syntax_and_live_sale_status_gate(tmp_path):
    script = _DOCUMENT.split('<script>', 1)[1].split('</script>', 1)[0]
    path = tmp_path / 'workspace.js'
    path.write_text(script)
    subprocess.run(['node', '--check', str(path)], check=True, capture_output=True)
    selling = _DOCUMENT.split('function renderSelling()', 1)[1].split('function renderLibrary(', 1)[0]
    assert selling.index('if (!requestStatusLoaded)') < selling.index('const candidates')
    assert 'const ready = candidates.filter(row => !row.pending)' in selling
    assert '...ready.map' in selling
    assert 'December 31, 2026' in _DOCUMENT
    assert 'Nothing is automatically listed or repriced' in selling

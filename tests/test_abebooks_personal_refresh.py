import json

from valuation import abebooks_personal_refresh as refresh


def job(tmp_path):
    (tmp_path / 'data').mkdir()
    source = tmp_path / 'data/estimates.json'
    source.write_text('{"low":20}')
    root = tmp_path / 'output/review'
    root.mkdir(parents=True)
    refresh.atomic_json(root / 'protected.json', refresh.protected(tmp_path))
    refresh.atomic_json(root / 'cohort.json', [dict(catalog_id='a', title='A'), dict(catalog_id='b', title='B')])
    return root, source


def test_resume_does_not_repeat_completed_books(tmp_path, monkeypatch):
    root, source = job(tmp_path)
    calls = []
    def collect(book, **kwargs):
        calls.append(book['catalog_id'])
        return [dict(catalog_id=book['catalog_id'], lookup_status='no_results', seller='private')]
    monkeypatch.setattr(refresh, 'collect_observations_for_sample', collect)
    refresh.run(tmp_path, root, max_books=1)
    refresh.run(tmp_path, root)
    refresh.run(tmp_path, root)
    assert calls == ['a', 'b']
    assert source.read_text() == '{"low":20}'
    assert 'private' not in (root / 'observations.csv').read_text()
    assert json.loads((root / 'status.json').read_text())['state'] == 'complete'


def test_block_stops_and_is_not_automatically_retried(tmp_path, monkeypatch):
    root, _ = job(tmp_path)
    calls = []
    def collect(book, **kwargs):
        calls.append(book['catalog_id'])
        return [dict(catalog_id=book['catalog_id'], lookup_status='source_unavailable', match_notes='HTTP 403')]
    monkeypatch.setattr(refresh, 'collect_observations_for_sample', collect)
    refresh.run(tmp_path, root)
    refresh.run(tmp_path, root)
    assert calls == ['a']
    assert json.loads((root / 'status.json').read_text())['state'] == 'blocked'


def test_changed_estimates_stop_before_network(tmp_path, monkeypatch):
    root, source = job(tmp_path)
    source.write_text('{"low":30}')
    monkeypatch.setattr(refresh, 'collect_observations_for_sample', lambda *a, **k: (_ for _ in ()).throw(AssertionError('network')))
    refresh.run(tmp_path, root)
    status = json.loads((root / 'status.json').read_text())
    assert status['state'] == 'stopped'
    assert status['completed'] == 0
    assert not status['source_data_unchanged']

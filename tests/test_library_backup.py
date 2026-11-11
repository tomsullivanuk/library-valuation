import hashlib
import json
import tarfile

import pytest
from operations.library_backup import backup


def test_backup_restores_canonical_files_excludes_transients_and_keeps_history(tmp_path):
    source = tmp_path / 'app'
    for name, content in [('data/catalog_items.csv', 'id,title\n1,Example\n'),
                          ('data/workspace_actions.json', '{"revision":2}'),
                          ('output/evidence.csv', 'price\n35\n'),
                          ('output/migration/old.tar.gz', 'old archive'),
                          ('data/private.key', 'secret'), ('.env', 'SECRET=example')]:
        path = source / name; path.parent.mkdir(parents=True, exist_ok=True); path.write_text(content)
    first = backup(source, tmp_path / 'backups')
    second = backup(source, tmp_path / 'backups')
    assert first != second and first.is_dir()
    manifest = json.loads((first / 'manifest.json').read_text())
    with tarfile.open(first / 'library.tar.gz') as archive:
        assert set(archive.getnames()) == {'data/catalog_items.csv', 'data/workspace_actions.json', 'output/evidence.csv'}
        for row in manifest['files']:
            assert hashlib.sha256(archive.extractfile(row['path']).read()).hexdigest() == row['sha256']
    with pytest.raises(ValueError):
        backup(source, source / 'recursive-backups')

"""Create verified, dated library snapshots; never delete previous backups."""
import argparse
import fcntl
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import tarfile
import tempfile
from datetime import datetime, timezone


def backup(source, destination):
    source, destination = Path(source).resolve(), Path(destination).resolve()
    if destination == source or source in destination.parents:
        raise ValueError('Backup destination must be outside the application directory')
    if not (source / 'data/catalog_items.csv').is_file():
        raise ValueError('Source catalog is missing')
    destination.mkdir(parents=True, exist_ok=True, mode=0o700)
    name = 'library-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S.%fZ')
    # Build locally first so partial archives are never published as backups.
    with tempfile.TemporaryDirectory(prefix='library-backup-') as temp:
        stage = Path(temp)
        rows = []
        with (source / 'data/.workspace.lock').open('a') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            with tarfile.open(stage / 'library.tar.gz', 'w:gz') as archive:
                paths = [source / 'requirements.txt']
                for directory in ('data', 'input', 'output', 'cache', 'config', 'valuation', 'operations'):
                    paths.extend(sorted((source / directory).rglob('*')))
                for path in paths:
                    rel = path.relative_to(source)
                    if path.is_symlink() or not path.is_file():
                        continue
                    if any(part in {'migration', '__pycache__', '.git', '.venv'} for part in rel.parts):
                        continue
                    if path.name.startswith('.env') or path.name == '.DS_Store' or path.suffix in {'.log', '.pid', '.lock', '.pem', '.key', '.pyc'}:
                        continue
                    raw = path.read_bytes()
                    rows.append(dict(path=str(rel), bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest()))
                    info = tarfile.TarInfo(str(rel)); info.size = len(raw); info.mode = 0o600
                    archive.addfile(info, io.BytesIO(raw))
        with tarfile.open(stage / 'library.tar.gz') as archive:
            for row in rows:
                if hashlib.sha256(archive.extractfile(row['path']).read()).hexdigest() != row['sha256']:
                    raise RuntimeError('Backup verification failed')
        (stage / 'manifest.json').write_text(json.dumps(dict(schema_version=1, created_utc=datetime.now(timezone.utc).isoformat(), files=rows), indent=2)+'\n')
        sums = ''.join(hashlib.sha256((stage / f).read_bytes()).hexdigest()+'  '+f+'\n' for f in ('library.tar.gz', 'manifest.json'))
        (stage / 'SHA256SUMS').write_text(sums)
        pending = destination / ('.'+name+'.pending')
        shutil.copytree(stage, pending)
        for f in pending.iterdir():
            os.chmod(f, 0o600)
            if hashlib.sha256(f.read_bytes()).digest() != hashlib.sha256((stage/f.name).read_bytes()).digest():
                raise RuntimeError('Published copy verification failed')
        os.chmod(pending, 0o700)
        final = destination / name
        pending.rename(final)
    # This confirms the local iCloud folder copy, not Apple's upload completion.
    print('Verified snapshot written:', final, flush=True)
    return final


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--destination', type=Path, required=True)
    args = parser.parse_args()
    backup(args.source, args.destination)

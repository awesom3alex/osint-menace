"""Three bounded installer checks; never runs OSINT tools or external searches."""
import hashlib
import json
import shutil
import sqlite3
import sys
import tarfile
import tempfile
import time
import urllib.request
from pathlib import Path


def service(version):
    def get(route):
        with urllib.request.urlopen('http://127.0.0.1:8080'+route, timeout=5) as response:
            return json.load(response)
    assert get('/health').get('ok') is True, 'Health check failed.'
    assert get('/api/version').get('version') == version, 'Running version differs from this checkout.'
    print('Check 1 passed: application health and version '+version+'.')


def database_snapshot(source, destination):
    """Copy stable DB/WAL/SHM files to writable storage for read-only mount checks."""
    source=Path(source);destination=Path(destination)
    def stamp():
        result={}
        for suffix in ('','-wal'):
            path=Path(str(source)+suffix)
            if path.exists():
                stat=path.stat();result[suffix]=(stat.st_ino,stat.st_size,stat.st_mtime_ns)
        return result
    for _ in range(3):
        try:
            before=stamp()
            if '' not in before:raise ValueError('Current history database is missing.')
            for suffix in ('','-wal','-shm'):
                original=Path(str(source)+suffix);copy=Path(str(destination)+suffix)
                copy.unlink(missing_ok=True)
                if original.is_file():shutil.copyfile(original,copy)
            if before==stamp():return
        except FileNotFoundError:
            pass
        time.sleep(0.1)
    raise ValueError('History database changed during validation; retry after activity settles.')


def data(archive, data_root=Path('/source/data')):
    count=0
    with tarfile.open(archive, 'r:gz') as backup:
        for entry in backup:
            if not entry.isfile() or entry.name in ('data/workspace.sqlite3', 'data/workspace.sqlite3-wal', 'data/workspace.sqlite3-shm'):
                continue
            relative=Path(entry.name)
            if relative.is_absolute() or '..' in relative.parts:
                raise ValueError('Invalid backup member.')
            path=data_root.parent/relative
            if not path.is_file():
                raise ValueError('An original case or evidence file is missing.')
            stored=backup.extractfile(entry)
            assert stored is not None
            def digest(stream):
                value=hashlib.sha256()
                for chunk in iter(lambda:stream.read(1024*1024),b''):
                    value.update(chunk)
                return value.digest()
            with path.open('rb') as current:
                if digest(current)!=digest(stored):
                    raise ValueError('An original case or evidence file changed during installation.')
            count+=1
    # A database can change its WAL/layout on restart. Compare saved records,
    # permitting only the existing interrupted-search recovery transformation.
    with tempfile.TemporaryDirectory() as folder, tarfile.open(archive, 'r:gz') as backup:
        database = Path(folder) / 'workspace.sqlite3'
        for suffix in ('', '-wal', '-shm'):
            name = 'data/workspace.sqlite3' + suffix
            try:
                entry = backup.getmember(name)
            except KeyError:
                continue
            if not entry.isfile():
                raise ValueError('Invalid database backup member.')
            with backup.extractfile(entry) as source, Path(str(database) + suffix).open('wb') as target:
                shutil.copyfileobj(source, target)
        if database.exists():
            current_copy = Path(folder) / 'current.sqlite3'
            database_snapshot(data_root/'workspace.sqlite3', current_copy)
            with sqlite3.connect(database) as previous, sqlite3.connect(current_copy) as current:
                assert current.execute('PRAGMA quick_check').fetchone()[0] == 'ok', 'History database integrity check failed.'
                for key, kind, target, created, raw in previous.execute('SELECT id,type,target,created,payload FROM records'):
                    found = current.execute('SELECT type,target,created,payload FROM records WHERE id=?', (key,)).fetchone()
                    assert found is not None and found[:3] == (kind, target, created), 'An original history record is missing or changed.'
                    old, new = json.loads(raw), json.loads(found[3])
                    if kind == 'addon' and old.get('status') in ('queued', 'running'):
                        old.update(status='interrupted', output=old.get('output', '') + '\nSearch interrupted by server restart. Start a new search to retry.')
                    if kind in ('global_search','research_tool') and old.get('status') == 'running':
                        assert isinstance(new.get('finished_at'), str), 'Interrupted research timestamp missing.'
                        old.update(status='interrupted', finished_at=new['finished_at'], entries=old.get('entries', []),
                                   errors=old.get('errors', []) + ['Research request interrupted by server restart. Review inputs before retrying.'])
                    assert old == new, 'An original history payload changed.'
                    count += 1
                for key, payload in previous.execute('SELECT tool,payload FROM health'):
                    assert current.execute('SELECT payload FROM health WHERE tool=?', (key,)).fetchone() == (payload,), 'A tool-health record changed.'
    print(f'Check 2 passed: {count} original data files/history records preserved.')


def pages():
    demo='00000000-0000-4000-8000-000000000001'
    for route in ('/cases','/demo',f'/cases/{demo}/entities',f'/cases/{demo}/sharing-review'):
        with urllib.request.urlopen('http://127.0.0.1:8080'+route,timeout=10) as response:
            if response.status!=200:
                raise ValueError('An application screen did not load.')
    print('Check 3 passed: case workspace and populated demo screens load.')


if __name__=='__main__':
    mode=sys.argv[1]
    if mode=='service':service(sys.argv[2])
    elif mode=='data':data(sys.argv[2])
    elif mode=='pages':pages()
    else:raise SystemExit('Unknown setup check.')

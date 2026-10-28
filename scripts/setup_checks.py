"""Three bounded installer checks; never runs OSINT tools or external searches."""
import hashlib
import json
import sys
import tarfile
import urllib.request
from pathlib import Path


def service(version):
    def get(route):
        with urllib.request.urlopen('http://127.0.0.1:8080'+route, timeout=5) as response:
            return json.load(response)
    assert get('/health').get('ok') is True, 'Health check failed.'
    assert get('/api/version').get('version') == version, 'Running version differs from this checkout.'
    print('Check 1 passed: application health and version '+version+'.')


def data(archive):
    count=0
    with tarfile.open(archive, 'r:gz') as backup:
        for entry in backup:
            if not entry.isfile() or not (entry.name.startswith(('data/cases/', 'data/evidence/', 'data/catalog/')) or entry.name=='data/cli_state.json'):
                continue
            relative=Path(entry.name)
            if relative.is_absolute() or '..' in relative.parts:
                raise ValueError('Invalid backup member.')
            path=Path('/source')/relative
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
    print(f'Check 2 passed: {count} original case/evidence/catalog files preserved.')


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

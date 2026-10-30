"""Reviewed source expansion, immutable page observations, activity, and saved case backups."""
import datetime as dt
import difflib
import hashlib
import http.client
import ipaddress
import json
import os
import re
import shutil
import socket
import ssl
import threading
import uuid
import zipfile
from urllib.parse import urljoin, urlsplit

from bs4 import BeautifulSoup
from flask import Blueprint, abort, redirect, render_template, request, send_file, url_for

from case_workflow import event, findings
from investigation import target_url
from paths import DATA_ROOT

bp = Blueprint('case_research', __name__)
BACKUPS = DATA_ROOT / "backups"
BACKUP_LOCK = threading.Lock()
CAPTURE_LOCK = threading.BoundedSemaphore(2)
KINDS = ('email', 'username', 'phone', 'domain', 'ip')


def identifiers(case, ref='', graph_id='', node_id=''):
    values = []
    if ref:
        found = next((f for key, _, _, f in findings(case) if key == ref), None)
        if found is None:
            abort(404)
        if isinstance(found.get('value'), str):
            values.append((found.get('label', 'Finding'), found['value']))
    if graph_id or node_id:
        graph = next((g for g in case.get('graphs', []) if g['id'] == graph_id), None)
        node = next((n for n in graph['nodes'] if n['id'] == node_id), None) if graph else None
        if node is None:
            abort(404)
        values.extend((f['name'], str(f['value'])) for f in node.get('fields', []) if f.get('value'))
        values.append((node['type'], node['label']))
    output = []
    for label, raw in values:
        value = raw.strip()
        kind = None
        if re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+', value):
            kind = 'email'
        else:
            try:
                ipaddress.ip_address(value)
                kind = 'ip'
            except ValueError:
                if re.fullmatch(r'\+?[\d ().-]{7,25}', value):
                    kind = 'phone'
                if value.startswith(('https://', 'http://')):
                    value = urlsplit(value).hostname or ''
                if kind is None and re.fullmatch(r'(?:[A-Za-z0-9-]+\.)+[A-Za-z]{2,63}', value):
                    kind = 'domain'
                elif re.search(r'username|handle|account', label, re.I) and re.fullmatch(r'@?[\w.-]{1,100}', value):
                    kind, value = 'username', value.lstrip('@')
        if kind and (kind, value) not in output:
            output.append((kind, value))
    return output


@bp.get('/cases/<case_id>/expand')
def expand(case_id):
    import addon_tools
    import app
    case = app.load_case(case_id)
    candidates = identifiers(case, request.args.get('ref', ''), request.args.get('graph', ''), request.args.get('node', ''))
    return render_template('source_expansion.html', case=case, candidates=candidates, kinds=KINDS, tools=addon_tools.catalog())


@bp.post('/cases/<case_id>/expand')
def launch_expansion(case_id):
    import app
    import workspace_features
    case = app.load_case(case_id)
    data = request.get_json(silent=True)
    if not isinstance(data, dict) or data.get('kind') not in KINDS or not isinstance(data.get('target'), str) or not 1 <= len(data['target'].strip()) <= 254:
        abort(400, 'Choose a supported identifier type and enter a target.')
    # Reuse the bounded search queue; results stay in History until explicitly saved.
    if data.get('tools') != ['console']:
        response, status = workspace_features.launch()
        if status == 202:
            payload = response.get_json()
            import workspace_store
            group = workspace_store.get(payload['id'])
            group['origin_case_id'] = case['id']
            workspace_store.put(payload['id'], 'unified', group)
            payload['url'] += '?case_id=' + case['id']
            return payload, status
        return response, status
    target, kind = data['target'].strip(), data['kind']
    try:
        results = app.run_search(kind, target, '', False, '21,22,80,443,8080')
        import workspace_store
        key = uuid.uuid4().hex
        workspace_store.put(key, 'console', dict(id=key, target=target, kind=kind, origin_case_id=case['id'], timestamp=app.utc_now(), results=results, summary=app.result_summary(results)))
    except (ValueError, OSError) as exc:
        return dict(error=str(exc)), 400
    return dict(url=url_for('workspace.history_detail', record_id=key, case_id=case['id'])), 202


def fetch_public_page(url):
    """Pin each connection to validated public DNS answers, including redirects."""
    for _ in range(4):
        parsed = urlsplit(url)
        if parsed.scheme not in ('http', 'https') or not parsed.hostname or parsed.username or parsed.password or len(url) > 2048:
            raise ValueError('Use a public HTTP or HTTPS source URL without credentials.')
        port = parsed.port or (443 if parsed.scheme == 'https' else 80)
        if port not in (80, 443):
            raise ValueError('Source captures support standard web ports only.')
        addresses = {answer[4][0] for answer in socket.getaddrinfo(parsed.hostname, port, type=socket.SOCK_STREAM)}
        if not addresses or any(not ipaddress.ip_address(address).is_global for address in addresses):
            raise ValueError('Local, private, and reserved network sources are not allowed.')
        address = sorted(addresses)[0]
        connection = http.client.HTTPConnection(parsed.hostname, port, timeout=8)
        # Resolve once, then connect to the validated IP. TLS still checks original host.
        connection.sock = socket.create_connection((address, port), timeout=8)
        try:
            if parsed.scheme == 'https':
                connection.sock = ssl.create_default_context().wrap_socket(connection.sock, server_hostname=parsed.hostname)
            path = parsed.path or '/'
            if parsed.query:
                path += '?' + parsed.query
            connection.request('GET', path, headers={'Host': parsed.netloc, 'User-Agent': 'OSINT-Menace-Source-Capture/0.4', 'Accept-Encoding': 'identity', 'Accept': 'text/html,text/plain'})
            response = connection.getresponse()
            if response.status in (301, 302, 303, 307, 308):
                location = response.getheader('Location')
                if not location:
                    raise ValueError('Source redirect has no destination.')
                url = urljoin(url, location)
                continue
            if response.status != 200:
                raise ValueError(f'Source returned HTTP {response.status}; no observation was saved.')
            mime = response.getheader('Content-Type', '').split(';')[0].lower()
            if mime not in ('text/html', 'text/plain', 'application/xhtml+xml') or response.getheader('Content-Encoding', 'identity') != 'identity':
                raise ValueError('Source must return uncompressed HTML or plain text.')
            raw = response.read(1_000_001)
            if len(raw) > 1_000_000:
                raise ValueError('Source page exceeds the 1 MB capture limit.')
            text = raw.decode('utf-8', errors='replace')
            if mime != 'text/plain':
                soup = BeautifulSoup(text, 'html.parser')
                for tag in soup(['script', 'style', 'noscript', 'template']):
                    tag.decompose()
                text = soup.get_text('\n')
            text = '\n'.join(line for line in (' '.join(line.split()) for line in text.splitlines()) if line)
            if not text or len(text) > 60000:
                raise ValueError('Readable source text is empty or exceeds 60,000 characters.')
            return dict(url=url, text=text, sha256=hashlib.sha256(text.encode()).hexdigest())
        finally:
            connection.close()
    raise ValueError('Source redirected too many times.')


def locate(case, ref):
    finding = next((f for key, _, _, f in findings(case) if key == ref), None)
    if finding is None:
        abort(404)
    return finding


def validate_observations(items):
    if not isinstance(items, list) or len(items) > 25:
        raise ValueError('A finding supports up to 25 retained source observations.')
    seen = set()
    for item in items:
        if (not isinstance(item, dict) or not isinstance(item.get('id'), str) or not re.fullmatch(r'[a-f0-9]{32}', item['id'])
                or item['id'] in seen or not isinstance(item.get('text'), str) or not 1 <= len(item['text']) <= 60000
                or not isinstance(item.get('url'), str) or len(item['url']) > 2048
                or not isinstance(item.get('timestamp'), str) or len(item['timestamp']) > 100
                or hashlib.sha256(item['text'].encode()).hexdigest() != item.get('sha256')):
            raise ValueError('Invalid source observation or content hash.')
        from case_workflow import validated_url
        validated_url(item['url'])
        dt.datetime.fromisoformat(item['timestamp'].replace('Z', '+00:00'))
        seen.add(item['id'])


@bp.route('/cases/<case_id>/observations/<path:ref>', methods=['GET', 'POST'])
def observations(case_id, ref):
    import app
    case = app.load_case(case_id)
    finding = locate(case, ref)
    error = None
    if request.method == 'POST':
        url = finding.get('source_url', '')
        if not url:
            abort(400, 'This finding needs a recorded source URL before it can be rechecked.')
        if not CAPTURE_LOCK.acquire(blocking=False):
            abort(429, 'Two source captures are running. Try again shortly.')
        try:
            snapshot = fetch_public_page(url)
            with app.CASE_LOCK:
                case = app.load_case(case_id)
                finding = locate(case, ref)
                if finding.get('source_url') != url:
                    raise ValueError('The source URL changed during capture. Review it before retrying.')
                items = finding.setdefault('observations', [])
                if len(items) >= 25:
                    raise ValueError('25 observations are retained. Export this case before creating another evidence record.')
                snapshot.update(id=uuid.uuid4().hex, timestamp=app.utc_now())
                items.append(snapshot)
                event(case, 'source_rechecked', 'Captured a new source observation.', ref=ref)
                case['updated_at'] = app.utc_now()
                from case_backups import MAX_CASE, encode
                if len(encode(case)) > MAX_CASE:
                    raise ValueError('Case exceeds the supported size limit; no observation was saved.')
                app.save_case(case)
            return redirect(url_for('case_research.observations', case_id=case_id, ref=ref))
        except (ValueError, OSError, http.client.HTTPException) as exc:
            error = str(exc)
        finally:
            CAPTURE_LOCK.release()
    items = finding.get('observations', [])
    by_id = {item['id']: item for item in items}
    before = by_id.get(request.args.get('before')) or (items[-2] if len(items) > 1 else None)
    after = by_id.get(request.args.get('after')) or (items[-1] if items else None)
    diff = list(difflib.ndiff(before['text'].splitlines(), after['text'].splitlines()))[:600] if before and after else []
    return render_template('source_observations.html', case=case, finding=finding, ref=ref, observations=items, before=before, after=after, diff=diff, error=error), 400 if error else 200


@bp.get('/cases/<case_id>/dashboard')
def dashboard(case_id):
    import app
    case = app.load_case(case_id)
    today = dt.datetime.now(dt.timezone.utc).date().isoformat()
    tasks = [dict(task, overdue=bool(task.get('due') and task['due'] < today)) for task in case.get('investigation', {}).get('tasks', []) if task['status'] != 'Complete']
    unverified = [dict(label=f.get('label', 'Finding'), url=target_url(case, ref)) for ref, _, _, f in findings(case) if f.get('verification_status', 'Unverified') == 'Unverified']
    connections = [dict(label=edge['label'], url=url_for('case_graphs.workspace', case_id=case_id, graph=g['id'], focus=edge['id'])) for g in case.get('graphs', []) for edge in g['edges'] if edge.get('status') != 'supported' or not edge.get('evidenceRefs')]
    changes = []
    for ref, _, _, finding in findings(case):
        items = finding.get('observations', [])
        if len(items) >= 2 and items[-1]['sha256'] != items[-2]['sha256']:
            changes.append(dict(label=finding['label'], timestamp=items[-1]['timestamp'], url=url_for('case_research.observations', case_id=case_id, ref=ref)))
    return render_template('case_dashboard.html', case=case, tasks=tasks, unverified=unverified, connections=connections, changes=changes, events=sorted(case.get('events', []), key=lambda e:e['timestamp'], reverse=True)[:30])


def saved_backups(case_id):
    records = []
    for path in (BACKUPS / case_id).glob('*.json'):
        if not re.fullmatch(r'[a-f0-9]{32}', path.stem):
            continue
        try:
            item = json.loads(path.read_text())
            if (isinstance(item, dict) and item.get('id') == path.stem and isinstance(item.get('timestamp'), str)
                    and isinstance(item.get('updated_at'), str) and isinstance(item.get('bytes'), int)
                    and isinstance(item.get('sha256'), str) and re.fullmatch(r'[a-f0-9]{64}', item['sha256'])
                    and (path.with_suffix('.zip')).is_file()):
                records.append(item)
        except (OSError, ValueError):
            continue
    return sorted(records, key=lambda item:item['timestamp'], reverse=True)


@bp.get('/backups')
def backup_overview():
    import app
    cases = [dict(case, backups=saved_backups(case['id'])) for case in app.list_cases()]
    return render_template('backup_center.html', cases=cases, case=None)


@bp.get('/cases/<case_id>/backups')
def backup_center(case_id):
    import app
    case = app.load_case(case_id)
    return render_template('backup_center.html', case=case, cases=[], backups=saved_backups(case_id))


@bp.post('/cases/<case_id>/backups')
def create_backup(case_id):
    import app
    from case_backups import archive_case, checked_zip
    with BACKUP_LOCK, app.CASE_LOCK:
        case = app.load_case(case_id)
        folder = BACKUPS / case_id
        folder.mkdir(mode=0o700, parents=True, exist_ok=True)
        if len(list(folder.glob('*.zip'))) >= 20:
            abort(400, '20 backups are retained. Export and archive older backups on the host before creating more.')
        key = uuid.uuid4().hex
        temporary = folder / (key + '.tmp')
        try:
            with archive_case(case) as source, temporary.open('xb') as target:
                temporary.chmod(0o600)
                shutil.copyfileobj(source, target)
            checked_zip(temporary)
            with temporary.open('rb') as stream:
                digest = hashlib.file_digest(stream, 'sha256').hexdigest()
            meta = dict(id=key, timestamp=app.utc_now(), updated_at=case['updated_at'], bytes=temporary.stat().st_size, sha256=digest)
            os.replace(temporary, folder / (key + '.zip'))
            receipt = folder / (key + '.json.tmp')
            receipt.write_text(json.dumps(meta))
            receipt.chmod(0o600)
            os.replace(receipt, folder / (key + '.json'))
        except (ValueError, OSError) as exc:
            temporary.unlink(missing_ok=True)
            abort(409, str(exc))
    return redirect(url_for('case_research.backup_center', case_id=case_id))


def verified_backup(case_id, key):
    import app
    from case_backups import checked_zip
    app.load_case(case_id)
    if not re.fullmatch(r'[a-f0-9]{32}', key):
        abort(404)
    path = BACKUPS / case_id / (key + '.zip')
    meta = next((item for item in saved_backups(case_id) if item['id'] == key), None)
    if not meta:
        abort(404)
    try:
        with path.open('rb') as stream:
            if hashlib.file_digest(stream, 'sha256').hexdigest() != meta['sha256']:
                raise ValueError('Backup integrity check failed.')
        restored, _, _ = checked_zip(path)
        if restored['id'] != case_id:
            raise ValueError('Backup belongs to another case.')
    except (ValueError, OSError, zipfile.BadZipFile, RuntimeError, KeyError, TypeError) as exc:
        abort(409, str(exc))
    return path


@bp.get('/cases/<case_id>/backups/<key>.zip')
def download_backup(case_id, key):
    return send_file(verified_backup(case_id, key), mimetype='application/zip', as_attachment=True, download_name='case-backup-'+key+'.zip')


@bp.post('/cases/<case_id>/backups/<key>/preview')
def preview_backup(case_id, key):
    import case_backups
    path = verified_backup(case_id, key)
    with case_backups.IMPORT_LOCK:
        case_backups.cleanup_staging()
        if len(list(case_backups.STAGING.glob('*.zip'))) >= 4:
            abort(429, 'Four restore previews are pending. Finish one or wait for expiry.')
        token = uuid.uuid4().hex
        staged = case_backups.STAGING / (token + '.zip')
        shutil.copyfile(path, staged)
        case, _, counts = case_backups.checked_zip(staged)
        with staged.open('rb') as source:
            sha = hashlib.file_digest(source, 'sha256').hexdigest()
    return render_template('backup_import.html', preview=case, counts=counts, token=token, sha=sha)

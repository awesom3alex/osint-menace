"""Bounded, cached checks for published stable OSINT Menace releases."""
import json
import re
import threading
import time
import urllib.error
import urllib.request

REPOSITORY = 'awesom3alex/osint-menace'
API_URL = f'https://api.github.com/repos/{REPOSITORY}/releases/latest'
TIMEOUT = 5
CACHE_SECONDS = 6 * 60 * 60
_lock = threading.Lock()
_cache = {}


def version_tuple(value):
    match = re.fullmatch(r'v?(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)', str(value))
    if not match:
        raise ValueError('Only stable semantic release versions are supported.')
    return tuple(map(int, match.groups()))


def latest_release():
    request = urllib.request.Request(API_URL, headers={
        'Accept': 'application/vnd.github+json', 'User-Agent': 'OSINT-Menace-Update-Check'})
    with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
        raw = response.read(1_000_001)
    if len(raw) > 1_000_000:
        raise ValueError('Release metadata exceeds the size limit.')
    data = json.loads(raw)
    if data.get('draft') or data.get('prerelease'):
        raise ValueError('The latest release is not stable.')
    version = '.'.join(map(str, version_tuple(data['tag_name'])))
    tag = data['tag_name']
    return dict(version=version, tag=tag, name=str(data.get('name') or tag)[:300],
                url=f'https://github.com/{REPOSITORY}/releases/tag/{tag}',
                archive=f'https://api.github.com/repos/{REPOSITORY}/tarball/{tag}')


def check(current):
    with _lock:
        now = time.monotonic()
        if _cache.get('expires', 0) <= now:
            try:
                _cache.update(release=latest_release(), error=False, expires=now + CACHE_SECONDS)
            except (OSError, ValueError, KeyError, TypeError):
                _cache.update(release=None, error=True, expires=now + 15 * 60)
        release = _cache.get('release')
        return dict(current=current, status='unavailable' if _cache.get('error') else 'ok',
                    available=bool(release and version_tuple(release['version']) > version_tuple(current)),
                    latest=release)


def register(app):
    from flask import jsonify

    @app.get('/api/updates')
    def release_update_status():
        response = jsonify(check(app.config['APP_VERSION']))
        response.headers['Cache-Control'] = 'no-store'
        return response

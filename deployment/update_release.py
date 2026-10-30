"""Stage a stable release beside the installation; never replace original data/source."""
import hashlib
import io
import json
import os
import shutil
import sys
import tarfile
import urllib.request
from pathlib import Path, PurePosixPath

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "osint"))
from release_updates import latest_release, version_tuple  # noqa: E402

MAX_ARCHIVE = 100 * 1024 * 1024
MAX_EXPANDED = 300 * 1024 * 1024
PROTECTED = {'.git', '.env', 'data', 'exports', 'output', 'tmp', 'reference_scripts'}


def extract_release(raw, destination):
    """Reject links, traversal, runtime/configuration files, and oversized archives."""
    with tarfile.open(fileobj=io.BytesIO(raw), mode='r:gz') as archive:
        members = []
        expanded = 0
        for entry in archive:
            expanded += entry.size
            if len(members) >= 30000 or expanded > MAX_EXPANDED:
                raise ValueError('Release exceeds extraction limits.')
            members.append(entry)
        roots = set()
        paths = set()
        for entry in members:
            path = PurePosixPath(entry.name)
            if path.is_absolute() or '..' in path.parts or not path.parts:
                raise ValueError('Unsafe release path.')
            roots.add(path.parts[0])
            relative = PurePosixPath(*path.parts[1:])
            if not (entry.isdir() or entry.isfile()):
                raise ValueError('Release links and special files are not allowed.')
            if relative == PurePosixPath('.'):
                continue
            if str(relative) in paths:
                raise ValueError('Duplicate release path.')
            paths.add(str(relative))
            first = relative.parts[0]
            # Bundled public catalog is application data, not an investigation.
            if first in PROTECTED and not str(relative).startswith('data/catalog/') and str(relative) not in ('data', 'data/catalog'):
                raise ValueError('Release contains protected runtime/configuration paths.')
            if first.startswith('.env') or (str(relative).startswith('addons/sources/') or str(relative).startswith('osint/addons/sources/')):
                raise ValueError('Release contains deployment-specific files.')
        if len(roots) != 1:
            raise ValueError('Expected a single release archive root.')
        destination.mkdir(parents=True)
        for entry in members:
            relative = PurePosixPath(*PurePosixPath(entry.name).parts[1:])
            if relative == PurePosixPath('.'):
                continue
            target = destination.joinpath(*relative.parts)
            if entry.isdir():
                target.mkdir(parents=True, exist_ok=True)
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                with archive.extractfile(entry) as source, target.open('xb') as output:
                    shutil.copyfileobj(source, output)
                target.chmod(0o755 if entry.mode & 0o111 else 0o644)


def stage(root, run, current):
    release = latest_release()
    if version_tuple(release['version']) <= version_tuple(current):
        print(f"Already current: installed v{current}; latest stable v{release['version']}.")
        return False
    request = urllib.request.Request(release['archive'], headers={'User-Agent': 'OSINT-Menace-Updater'})
    with urllib.request.urlopen(request, timeout=60) as response:
        raw = response.read(MAX_ARCHIVE + 1)
    if len(raw) > MAX_ARCHIVE:
        raise ValueError('Release download exceeds the size limit.')
    run.mkdir(parents=True, exist_ok=True)
    release_root = run / 'source'
    extract_release(raw, release_root)
    if (release_root / 'osint/VERSION').read_text().strip() != release['version']:
        raise ValueError('Release tag and source VERSION do not match.')
    for filename in ('install.py', 'deployment/install.sh', 'deployment/docker-compose.yml', 'deployment/setup_checks.py', 'deployment/update_release.py'):
        if not (release_root / filename).is_file():
            raise ValueError('Release is missing required installation files.')
    # Only releases with shared-data installer support are safe for staged upgrades.
    if 'OSINT_DATA_DIR' not in (release_root / 'deployment/install.sh').read_text():
        raise ValueError('This release does not support safe staged upgrades.')
    # This is a private configuration backup, outside either Docker build context.
    config_backup = run / 'configuration'
    config_backup.mkdir(mode=0o700)
    for path in root.glob('.env*'):
        if path.is_symlink():
            raise ValueError('Symlinked environment files require a manual upgrade.')
        if path.is_file():
            shutil.copy2(path, config_backup / path.name)
            shutil.copy2(path, release_root / path.name)
            (config_backup / path.name).chmod(0o600)
            (release_root / path.name).chmod(0o600)
    (run / 'release.json').write_text(json.dumps(dict(release, sha256=hashlib.sha256(raw).hexdigest()), indent=2))
    print(f"Staged v{release['version']}; source archive SHA-256 recorded. Existing source and data are untouched.")
    return True


def deployment(run):
    """Preserve resolved deployment settings, with only source/image paths changed."""
    path = run / 'deployment.json'
    config = json.loads(path.read_text())
    if set(config.get('services', {})) != {'menace'}:
        raise ValueError('Multi-service deployments require a manual upgrade.')
    release = json.loads((run / 'release.json').read_text())
    service = config['services']['menace']
    # Host path supplied by the wrapper, not the helper container's /run mapping.
    service['build'] = {'context': os.environ['MENACE_RELEASE_SOURCE'], 'dockerfile': 'deployment/Dockerfile'}
    service['image'] = 'osint-menace:' + release['version']
    mounts = [m for m in service.get('volumes', []) if m.get('target') == '/app/data']
    if len(mounts) != 1 or mounts[0].get('type') != 'bind':
        raise ValueError('The updater requires the existing bind-mounted /app/data directory.')
    # Force every existing bind path to remain an explicit absolute path.
    if any(v.get('type') == 'bind' and not Path(v['source']).is_absolute() for v in service.get('volumes', [])):
        raise ValueError('Unresolved deployment volume paths.')
    path.write_text(json.dumps(config, indent=2))
    path.chmod(0o600)
    (run / 'data-path.txt').write_text(mounts[0]['source'])


if __name__ == '__main__':
    try:
        mode = sys.argv[1]
        if mode == 'check':
            release = latest_release()
            print(f"Installed v{sys.argv[2]}; latest stable v{release['version']}.")
        elif mode == 'stage':
            stage(Path('/configuration-source'), Path('/run'), sys.argv[2])
        elif mode == 'deployment':
            deployment(Path('/run'))
        else:
            raise ValueError('Unknown updater operation.')
    except (OSError, ValueError, KeyError, TypeError, tarfile.TarError) as exc:
        raise SystemExit('Update stopped: ' + str(exc)) from None

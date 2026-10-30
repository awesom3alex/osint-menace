"""Release checks and staged-upgrade safety without replacing production."""

import io
import json
import os
import tarfile
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch

from deployment import update_release as updater

import app
import release_updates as updates


def archive(files, link=None):
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as result:
        for name, value in files.items():
            raw = value.encode()
            entry = tarfile.TarInfo(name if name.startswith("/") else "release/" + name)
            entry.size = len(raw)
            entry.mode = 0o755 if name.endswith(".sh") else 0o644
            result.addfile(entry, io.BytesIO(raw))
        if link:
            entry = tarfile.TarInfo("release/" + link)
            entry.type = tarfile.SYMTYPE
            entry.linkname = "/etc/passwd"
            result.addfile(entry)
    return buffer.getvalue()


def release():
    return dict(
        version="0.4.0",
        tag="v0.4.0",
        name="More Sources. Fewer Alibis.",
        url="https://github.com/awesom3alex/osint-menace/releases/tag/v0.4.0",
        archive="https://api.github.com/repos/awesom3alex/osint-menace/tarball/v0.4.0",
    )


class ReleaseTests(TestCase):
    def setUp(self):
        updates._cache.clear()
        self.addCleanup(updates._cache.clear)

    def test_semantic_order_cache_and_offline(self):
        self.assertGreater(updates.version_tuple("v0.10.0"), updates.version_tuple("0.9.0"))
        for invalid in ("v0.4.0-beta", "0.04.0", "anything"):
            with self.assertRaises(ValueError):
                updates.version_tuple(invalid)
        with (
            patch.object(updates, "latest_release", return_value=release()) as fetch,
            patch.dict(app.app.config, APP_VERSION="0.3.0"),
        ):
            result = app.app.test_client().get("/api/updates").get_json()
            self.assertTrue(result["available"])
            self.assertEqual(result["current"], "0.3.0")
            self.assertFalse(updates.check("0.4.0")["available"])
            self.assertFalse(updates.check("0.5.0")["available"])
            self.assertEqual(fetch.call_count, 1)
        updates._cache.clear()
        with patch.object(updates, "latest_release", side_effect=OSError("offline")):
            self.assertEqual(updates.check("0.3.0")["status"], "unavailable")
            self.assertFalse(updates.check("0.3.0")["available"])

    def test_published_stable_metadata_only_and_fixed_urls(self):
        payload = dict(
            tag_name="v0.4.0",
            draft=False,
            prerelease=False,
            name="Release",
            html_url="https://attacker.example",
        )
        with patch.object(
            updates.urllib.request, "urlopen", return_value=io.BytesIO(json.dumps(payload).encode())
        ):
            self.assertEqual(updates.latest_release()["url"], release()["url"])
        for key in ("draft", "prerelease"):
            payload[key] = True
            with patch.object(
                updates.urllib.request,
                "urlopen",
                return_value=io.BytesIO(json.dumps(payload).encode()),
            ):
                with self.assertRaises(ValueError):
                    updates.latest_release()
            payload[key] = False

    def test_archive_paths_links_and_runtime_files_rejected(self):
        for name in (
            "../escape",
            "/absolute",
            ".env",
            "data/cases/private.json",
            "addons/sources/tool/file",
            "osint/addons/sources/tool/file",
        ):
            with self.subTest(name=name), TemporaryDirectory() as folder:
                with self.assertRaises(ValueError):
                    updater.extract_release(archive({name: "bad"}), Path(folder) / "source")
        with TemporaryDirectory() as folder:
            with self.assertRaises(ValueError):
                updater.extract_release(
                    archive({"VERSION": "0.4.0"}, link="escape"), Path(folder) / "source"
                )
        with TemporaryDirectory() as folder:
            root = Path(folder) / "source"
            updater.extract_release(
                archive(
                    {"VERSION": "0.4.0", "install.sh": "#!/bin/bash", "data/catalog/a.json": "{}"}
                ),
                root,
            )
            self.assertTrue((root / "install.sh").stat().st_mode & 0o100)

    def test_staging_keeps_original_data_and_configuration(self):
        files = {
            "osint/VERSION": "0.4.0",
            "deployment/install.sh": "# OSINT_DATA_DIR",
            "deployment/docker-compose.yml": "services: {}",
            "deployment/setup_checks.py": "# check",
            "deployment/update_release.py": "# updater",
            "install.py": "# main",
        }
        with TemporaryDirectory() as folder:
            root = Path(folder) / "original"
            root.mkdir()
            (root / "data").mkdir()
            (root / "data/case.json").write_text("evidence")
            (root / "VERSION").write_text("0.3.0")
            (root / ".env").write_text("SESSION=private")
            run = Path(folder) / "upgrade"
            with (
                patch.object(updater, "latest_release", return_value=release()),
                patch.object(
                    updater.urllib.request, "urlopen", return_value=io.BytesIO(archive(files))
                ),
            ):
                self.assertTrue(updater.stage(root, run, "0.3.0"))
            self.assertEqual((root / "data/case.json").read_text(), "evidence")
            self.assertEqual((root / "VERSION").read_text(), "0.3.0")
            self.assertEqual((run / "source/.env").read_text(), "SESSION=private")
            self.assertEqual((run / "configuration/.env").stat().st_mode & 0o777, 0o600)
            self.assertFalse((run / "source/data/case.json").exists())
            self.assertTrue((run / "release.json").exists())

    def test_equal_version_no_download_and_mismatched_archive_stops(self):
        with (
            TemporaryDirectory() as folder,
            patch.object(updater, "latest_release", return_value=release()),
            patch.object(updater.urllib.request, "urlopen") as download,
        ):
            self.assertFalse(updater.stage(Path(folder), Path(folder) / "run", "0.4.0"))
            download.assert_not_called()
        with (
            TemporaryDirectory() as folder,
            patch.object(updater, "latest_release", return_value=release()),
            patch.object(
                updater.urllib.request,
                "urlopen",
                return_value=io.BytesIO(archive({"osint/VERSION": "0.5.0"})),
            ),
        ):
            with self.assertRaises(ValueError):
                updater.stage(Path(folder), Path(folder) / "run", "0.3.0")

    def test_deployment_preserves_ports_environment_and_data_mount(self):
        config = dict(
            name="osint-menace",
            services=dict(
                menace=dict(
                    image="old",
                    ports=[dict(target=8080, published="8099")],
                    environment=dict(SECRET="retained"),
                    volumes=[dict(type="bind", source="/original/data", target="/app/data")],
                    restart="unless-stopped",
                )
            ),
        )
        with TemporaryDirectory() as folder:
            run = Path(folder)
            (run / "deployment.json").write_text(json.dumps(config))
            (run / "release.json").write_text(json.dumps(release()))
            with patch.dict(os.environ, MENACE_RELEASE_SOURCE="/releases/new/source"):
                updater.deployment(run)
            saved = json.loads((run / "deployment.json").read_text())
            self.assertEqual(
                saved["services"]["menace"]["volumes"], config["services"]["menace"]["volumes"]
            )
            self.assertEqual(
                saved["services"]["menace"]["environment"],
                config["services"]["menace"]["environment"],
            )
            self.assertEqual(
                saved["services"]["menace"]["ports"], config["services"]["menace"]["ports"]
            )
            self.assertEqual(saved["services"]["menace"]["image"], "osint-menace:0.4.0")
            self.assertEqual((run / "data-path.txt").read_text(), "/original/data")
            self.assertEqual((run / "deployment.json").stat().st_mode & 0o777, 0o600)

    def test_database_and_extra_files_preserved_and_missing_history_detected(self):
        import sqlite3

        from deployment.setup_checks import data

        with TemporaryDirectory() as folder:
            root = Path(folder) / "data"
            root.mkdir()
            (root / "custom-setting.json").write_text("retained")
            database = root / "workspace.sqlite3"
            with sqlite3.connect(database) as db:
                db.execute(
                    "CREATE TABLE records (id TEXT PRIMARY KEY, type TEXT, target TEXT, created TEXT, payload TEXT)"
                )
                db.execute("CREATE TABLE health (tool TEXT PRIMARY KEY, payload TEXT)")
                db.execute(
                    "INSERT INTO records VALUES (?,?,?,?,?)",
                    ("search", "console", "private", "date", '{"results":[1]}'),
                )
                db.execute("INSERT INTO health VALUES (?,?)", ("tool", '{"ok":true}'))
            backup = Path(folder) / "backup.tar.gz"
            with tarfile.open(backup, "w:gz") as archive_file:
                archive_file.add(root, arcname="data")
            data(backup, root)
            with sqlite3.connect(database) as db:
                db.execute("DELETE FROM records")
            with self.assertRaises(AssertionError):
                data(backup, root)
            (root / "custom-setting.json").write_text("changed")
            with self.assertRaises(ValueError):
                data(backup, root)


FAKE_DOCKER = r"""#!/usr/bin/env python3
import json,os,sys
from pathlib import Path
args=sys.argv[1:]
with open(os.environ['FAKE_LOG'],'a') as log:log.write(json.dumps(args)+'\n')
if args[:2]==['exec','osint-menace-addons']:print('0.3.0')
if args[:3]==['compose','config','--format']:
 print(json.dumps({'name':'original','services':{'menace':{'volumes':[{'type':'bind','source':os.environ['FAKE_ROOT']+'/data','target':'/app/data'}],'environment':{'KEEP':'private'},'ports':[{'target':8080,'published':'8099'}]}}}))
if 'stage' in args or 'deployment' in args:
 run=None
 for i,arg in enumerate(args):
  if arg=='-v' and args[i+1].endswith(':/run'):run=Path(args[i+1][:-5])
 if 'stage' in args:
  if os.environ.get('FAKE_STAGE_FAIL')=='1':sys.exit(1)
  if os.environ.get('FAKE_CURRENT')=='1':sys.exit(0)
  (run/'release.json').write_text('{"version":"0.4.0"}')
  (run/'source').mkdir()
  code='#!/bin/bash\nprintf "%s" "$COMPOSE_FILE" > "'+str(run)+'/invoked-config"\nprintf "%s" "$OSINT_DATA_DIR" > "'+str(run)+'/invoked-data"\nexit '+os.environ.get('FAKE_INSTALL_RESULT','0')+'\n'
  (run/'source/deployment').mkdir()
  (run/'source/deployment/install.sh').write_text(code)
 else:
  (run/'data-path.txt').write_text(os.environ['FAKE_ROOT']+'/data')
if args and args[0]=='build':sys.stdin.read()
"""


class UpdateShellTests(TestCase):
    def invoke(self, check=False, **flags):
        import shutil
        import subprocess

        folder = TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        root = Path(folder.name) / "original folder"
        root.mkdir()
        (root / "deployment").mkdir()
        (root / "data").mkdir()
        (root / "osint").mkdir()
        (root / "osint/VERSION").write_text("0.3.0")
        source = Path(__file__).resolve().parents[1]
        shutil.copy2(source / "install.py", root / "install.py")
        shutil.copy2(source / "deployment/update.sh", root / "deployment/update.sh")
        shutil.copy2(source / "deployment/Dockerfile.setup", root / "deployment/Dockerfile.setup")
        (root / "data/case.json").write_text("retained")
        binaries = Path(folder.name) / "bin"
        binaries.mkdir()
        docker = binaries / "docker"
        docker.write_text(FAKE_DOCKER)
        docker.chmod(0o755)
        log = Path(folder.name) / "calls.jsonl"
        env = dict(
            os.environ,
            PATH=str(binaries) + os.pathsep + os.environ["PATH"],
            FAKE_LOG=str(log),
            FAKE_ROOT=str(root),
            **flags,
        )
        result = subprocess.run(
            [
                __import__("sys").executable,
                str(root / "install.py"),
                *(["--check"] if check else ["--update", "--no-open"]),
            ],
            env=env,
            capture_output=True,
            text=True,
            timeout=10,
        )
        self.assertFalse((root / "output/update.lock").exists(), result.stderr)
        self.assertEqual((root / "data/case.json").read_text(), "retained")
        return root, result

    def test_success_records_active_config_and_passes_original_data(self):
        root, result = self.invoke()
        self.assertEqual(result.returncode, 0, result.stderr)
        config = Path((root / "output/active-update-config.txt").read_text().strip())
        self.assertTrue(config.is_file())
        self.assertEqual((config.parent / "invoked-data").read_text(), str(root / "data"))
        self.assertEqual((config.parent / "invoked-config").read_text(), str(config))

    def test_no_new_release_and_failures_leave_no_active_pointer(self):
        for flag in ({"FAKE_CURRENT": "1"}, {"FAKE_STAGE_FAIL": "1"}, {"FAKE_INSTALL_RESULT": "1"}):
            with self.subTest(flag=flag):
                root, result = self.invoke(**flag)
                self.assertEqual(
                    result.returncode, 0 if "FAKE_CURRENT" in flag else 1, result.stderr
                )
                self.assertFalse((root / "output/active-update-config.txt").exists())

    def test_entrypoint_check_never_stages_a_release(self):
        root, result = self.invoke(check=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse((root / "output/active-update-config.txt").exists())

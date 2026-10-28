"""Installer orchestration against a fake Docker CLI; never touches live Docker."""
import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from unittest import TestCase

ROOT=Path(__file__).resolve().parents[1]
FAKE=r'''#!/usr/bin/env python3
import json,os,sys
from pathlib import Path
args=sys.argv[1:]
with open(os.environ['FAKE_LOG'],'a') as log:log.write(json.dumps(args)+'\n')
existing=os.environ.get('FAKE_EXISTING')=='1'
if args[:2]==['compose','config']:
 print('osint-menace:0.3.0');sys.exit(0)
if args and args[0]=='inspect':
 if not existing:sys.exit(1)
 if len(args)==2:print('[]');sys.exit(0)
 template=args[-1]
 if '.Mounts' in template:print(os.environ['FAKE_ROOT']+'/data')
 elif '.Image' in template:print('sha256:previous')
 sys.exit(0)
if args[:2]==['compose','build'] and os.environ.get('FAKE_BUILD_FAIL')=='1':sys.exit(1)
if args[:2]==['compose','port']:print('0.0.0.0:8088')
if args[:2]==['compose','exec'] and 'pages' in args and os.environ.get('FAKE_PAGES_FAIL')=='1':sys.exit(1)
if args and args[0]=='run':
 for i,value in enumerate(args):
  if value=='-v' and args[i+1].endswith(':/backup'):
   Path(args[i+1][:-len(':/backup')],'data-before-install.tar.gz').write_bytes(b'fixture backup')
if args and args[0]=='build':sys.stdin.read()
sys.exit(0)
'''


class InstallerTests(TestCase):
    def invoke(self, existing=False, pages_fail=False, build_fail=False):
        temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup)
        base=Path(temp.name);root=base/'project with spaces';root.mkdir();root=root.resolve()
        for name in ('install.sh','VERSION','docker-compose.yml'):
            shutil.copy2(ROOT/name,root/name)
        (root/'scripts').mkdir();shutil.copy2(ROOT/'scripts/Dockerfile.setup',root/'scripts/Dockerfile.setup')
        (root/'addons').mkdir();(root/'addons/fetch.py').write_text('# fixture')
        (root/'data').mkdir();(root/'data/original.txt').write_text('keep me')
        binaries=base/'bin';binaries.mkdir();docker=binaries/'docker';docker.write_text(FAKE);docker.chmod(0o755)
        log=base/'calls.jsonl'
        env=dict(os.environ,PATH=str(binaries)+os.pathsep+os.environ['PATH'],FAKE_LOG=str(log),FAKE_ROOT=str(root),FAKE_EXISTING=str(int(existing)),FAKE_PAGES_FAIL=str(int(pages_fail)),FAKE_BUILD_FAIL=str(int(build_fail)))
        result=subprocess.run(['/bin/bash',str(root/'install.sh'),'--no-open'],cwd=base,env=env,text=True,capture_output=True,timeout=10)
        calls=[json.loads(line) for line in log.read_text().splitlines()]
        return root,base,result,calls

    def test_fresh_install_builds_and_checks_without_host_packages(self):
        root,base,result,calls=self.invoke()
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertIn('http://localhost:8088/cases',result.stdout)
        self.assertTrue(any('addons/fetch.py' in c for c in calls))
        self.assertTrue(any('data' in c and c[0]=='run' for c in calls))
        self.assertFalse((root/'output/setup.lock').exists())
        self.assertEqual((root/'data/original.txt').read_text(),'keep me')

    def test_upgrade_backs_up_before_replacement_and_rolls_back_on_failure(self):
        root,base,result,calls=self.invoke(existing=True,pages_fail=True)
        self.assertNotEqual(result.returncode,0)
        stop=next(i for i,c in enumerate(calls) if c[:3]==['compose','stop','menace'])
        backup=next(i for i,c in enumerate(calls) if any('tar -czf' in a for a in c))
        up=next(i for i,c in enumerate(calls) if c[:3]==['compose','up','-d'])
        self.assertLess(stop,backup);self.assertLess(backup,up)
        self.assertTrue(any('rollback.override.yml' in ' '.join(c) and 'up' in c for c in calls))
        self.assertIn('Previous image restarted',result.stderr)
        self.assertFalse((root/'output/setup.lock').exists())

    def test_build_failure_does_not_stop_the_old_service(self):
        root,base,result,calls=self.invoke(existing=True,build_fail=True)
        self.assertNotEqual(result.returncode,0)
        self.assertFalse(any(c[:2]==['compose','stop'] for c in calls))
        self.assertFalse((root/'output/setup.lock').exists())

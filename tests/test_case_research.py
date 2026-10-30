"""Four research/recovery workflows against temporary cases; no external searches."""
import copy
import hashlib
import io
import json
import re
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import MagicMock, patch

from PIL import Image

import app
import case_backups
import case_features
import case_research as research
import workspace_store
from case_graphs import new_graph


def capture(text):
    return dict(url='https://public.example/source', text=text, sha256=hashlib.sha256(text.encode()).hexdigest())


class ResearchTests(TestCase):
    def setUp(self):
        folder = TemporaryDirectory(); self.addCleanup(folder.cleanup)
        self.root = Path(folder.name)
        for obj, key, value in ((app,'CASES_DIR',self.root/'cases'), (case_features,'EVIDENCE_DIR',self.root/'evidence'),
                                (research,'BACKUPS',self.root/'backups'), (case_backups,'STAGING',self.root/'pending'),
                                (workspace_store,'DB_PATH',self.root/'history.sqlite3')):
            p = patch.object(obj, key, value); p.start(); self.addCleanup(p.stop)
        self.case = app.create_case('Research fixture')
        section = dict(name='Source', findings=[dict(label='Email', value='analyst@example.com', source_url='http://public.example/source')], links=[], notes=[])
        search = app.make_search_record('email', 'analyst@example.com', [section], app.result_summary([section]))
        app.append_search_to_case(self.case, search)
        self.ref = search['id'] + ':0:0'
        self.base = '/cases/' + self.case['id']
        self.client = app.app.test_client()

    def test_navigation_and_preview_do_not_run_searches(self):
        with patch.object(app, 'run_search') as run:
            response = self.client.get(self.base+'/expand', query_string=dict(ref=self.ref))
            self.assertEqual(response.status_code, 200)
            self.assertIn(b'analyst@example.com', response.data)
            run.assert_not_called()
        for route in ('', '/dashboard', '/backups'):
            self.assertEqual(self.client.get(self.base+route).status_code, 200)
        self.assertEqual(self.client.get('/backups').status_code, 200)
        self.assertEqual(self.client.get(self.base+'/expand?ref=missing').status_code, 404)

    def test_console_expansion_keeps_results_in_history_until_reviewed(self):
        original = app.load_case(self.case['id'])['searches']
        result = [dict(name='New source', findings=[dict(label='Lead',value='unverified')], links=[], notes=[])]
        with patch.object(app, 'run_search', return_value=result) as run:
            response = self.client.post(self.base+'/expand', json=dict(kind='email', target='analyst@example.com', tools=['console']))
        self.assertEqual(response.status_code, 202)
        self.assertFalse(run.call_args.args[3])
        history = self.client.get(response.get_json()['url'])
        self.assertEqual(history.status_code, 200)
        self.assertIn(b'Return to originating case', history.data)
        self.assertEqual(app.load_case(self.case['id'])['searches'], original)
        self.assertIn(b'selected', history.data)
        self.assertEqual(self.client.post(self.base+'/expand', json=dict(kind='bad',target='x',tools=['console'])).status_code,400)

    def test_addon_expansion_preserves_origin_and_uses_existing_queue(self):
        import workspace_features
        key = 'a'*32
        workspace_store.put(key, 'unified', dict(id=key, job_ids=[], target='handle', kind='username', timestamp=app.utc_now()))
        with app.app.app_context():
            queued = app.jsonify(id=key,url='/history/'+key)
        with patch.object(workspace_features, 'launch', return_value=(queued,202)):
            response=self.client.post(self.base+'/expand',json=dict(kind='username',target='handle',tools=['sherlock']))
        self.assertEqual(response.status_code,202)
        self.assertEqual(workspace_store.get(key)['origin_case_id'],self.case['id'])

    def test_graph_identifiers_preserve_ip_type(self):
        case=app.load_case(self.case['id']); graph=new_graph('Sources')
        graph['nodes']=[dict(id='a',label='Person',type='Person',fields=[dict(name='Email',value='a@example.com'),dict(name='IP',value='203.0.113.4')])]
        case['graphs']=[graph]
        with app.app.test_request_context():
            candidates=research.identifiers(case,graph_id=graph['id'],node_id='a')
        self.assertIn(('email','a@example.com'),candidates)
        self.assertIn(('ip','203.0.113.4'),candidates)

    def test_source_observations_are_immutable_comparable_and_backed_up(self):
        original=copy.deepcopy(research.locate(app.load_case(self.case['id']),self.ref))
        with patch.object(research,'fetch_public_page',side_effect=[capture('original line'),capture('updated line')]):
            for _ in range(2):
                self.assertEqual(self.client.post(self.base+'/observations/'+self.ref).status_code,302)
        case=app.load_case(self.case['id']); finding=research.locate(case,self.ref)
        self.assertEqual(len(finding['observations']),2)
        self.assertEqual(finding['value'],original['value'])
        response=self.client.get(self.base+'/observations/'+self.ref)
        self.assertIn(b'Text changed',response.data)
        self.assertIn(b'diff-added',response.data)
        self.assertIn(b'original line',response.data)
        self.assertIn(b'updated line',response.data)
        self.assertIn(b'Sources with changed text',self.client.get(self.base+'/dashboard').data)
        with research.CAPTURE_LOCK, research.CAPTURE_LOCK:
            self.assertEqual(self.client.post(self.base+'/observations/'+self.ref).status_code,429)
        finding['observations'][0]['sha256']='bad'
        with self.assertRaises(ValueError):
            case_backups.validate_case(case)

    def test_capture_failure_never_replaces_saved_observations(self):
        with patch.object(research,'fetch_public_page',side_effect=ValueError('blocked')):
            response=self.client.post(self.base+'/observations/'+self.ref)
        self.assertEqual(response.status_code,400)
        self.assertFalse(research.locate(app.load_case(self.case['id']),self.ref).get('observations'))

    def test_public_fetch_rejects_private_and_unsafe_sources(self):
        for address in ('127.0.0.1','169.254.169.254','10.0.0.1','::1','::ffff:127.0.0.1'):
            with patch.object(research.socket,'getaddrinfo',return_value=[(0,0,0,'',(address,80))]), patch.object(research.socket,'create_connection') as connect:
                with self.assertRaises(ValueError):research.fetch_public_page('http://host.example/source')
                connect.assert_not_called()
        for url in ('file:///etc/passwd','http://user:pass@host.example/','http://host.example:8080/'):
            with self.assertRaises(ValueError):research.fetch_public_page(url)

    def test_fetch_pins_validated_ip_strips_scripts_and_checks_redirects(self):
        response=MagicMock(status=200)
        response.getheader.side_effect=lambda name,default=None:{'Content-Type':'text/html','Content-Encoding':'identity'}.get(name,default)
        response.read.return_value=b'<h1>Public facts</h1><script>SECRET</script><p>Text</p>'
        connection=MagicMock();connection.getresponse.return_value=response
        with patch.object(research.socket,'getaddrinfo',return_value=[(0,0,0,'',('93.184.216.34',80))]), patch.object(research.socket,'create_connection') as connect, patch.object(research.http.client,'HTTPConnection',return_value=connection):
            result=research.fetch_public_page('http://host.example/')
            self.assertNotIn('SECRET',result['text'])
            self.assertIn('Public facts',result['text'])
            self.assertEqual(connect.call_args.args[0],('93.184.216.34',80))
        response.status=302
        response.getheader.side_effect=lambda name,default=None:'http://localhost/private' if name=='Location' else default
        with patch.object(research.socket,'getaddrinfo',side_effect=[[(0,0,0,'',('93.184.216.34',80))],[(0,0,0,'',('127.0.0.1',80))]]), patch.object(research.socket,'create_connection'), patch.object(research.http.client,'HTTPConnection',return_value=connection):
            with self.assertRaises(ValueError):research.fetch_public_page('http://host.example/')

    def test_dashboard_counts_and_links(self):
        case=app.load_case(self.case['id'])
        case['investigation']=dict(tasks=[dict(id='t',title='Review source',status='Open',due='2000-01-01')])
        graph=new_graph('Connections');graph['edges']=[dict(id='e',label='May be linked',source='a',target='b',status='hypothesis')]
        case['graphs']=[graph];app.save_case(case)
        response=self.client.get(self.base+'/dashboard')
        self.assertEqual(response.status_code,200)
        self.assertIn(b'Overdue',response.data);self.assertIn(b'May be linked',response.data)
        self.assertIn(b'Email',response.data)

    def test_saved_backup_roundtrip_and_corruption_rejection(self):
        with patch.object(research,'fetch_public_page',return_value=capture('retained source')):
            self.client.post(self.base+'/observations/'+self.ref)
        case=app.load_case(self.case['id']); finding=research.locate(case,self.ref)
        eid='e'*32
        folder=case_features.EVIDENCE_DIR/self.case['id'];folder.mkdir(parents=True)
        image=io.BytesIO();Image.new('RGB',(20,20),'white').save(image,'PNG')
        (folder/(eid+'.png')).write_bytes(image.getvalue())
        finding['evidence']=[dict(id=eid,caption='Capture',sha256=hashlib.sha256(image.getvalue()).hexdigest())]
        app.save_case(case)
        self.assertEqual(self.client.post(self.base+'/backups').status_code,302)
        saved=research.saved_backups(self.case['id']);self.assertEqual(len(saved),1)
        key=saved[0]['id'];path=research.BACKUPS/self.case['id']/(key+'.zip')
        exported,files,_=case_backups.checked_zip(path)
        self.assertIn('retained source',json.dumps(exported));self.assertIn('evidence/'+eid+'.png',files)
        download=self.client.get(self.base+'/backups/'+key+'.zip');self.assertEqual(download.status_code,200);download.close()
        preview=self.client.post(self.base+'/backups/'+key+'/preview')
        self.assertEqual(preview.status_code,200)
        token=re.search(rb'name="token" value="([a-f0-9]+)"',preview.data)[1].decode()
        staged=case_backups.STAGING/(token+'.zip')
        with staged.open('rb') as stream:sha=hashlib.file_digest(stream,'sha256').hexdigest()
        restored=self.client.post('/cases/import/restore',data=dict(token=token,sha256=sha,case_name="Recovered copy"))
        self.assertEqual(restored.status_code,302)
        self.assertNotEqual(restored.location,self.base)
        self.assertTrue((folder/(eid+'.png')).exists())
        self.assertEqual(research.locate(app.load_case(self.case['id']),self.ref)['value'],'analyst@example.com')
        path.write_bytes(path.read_bytes()+b'corruption')
        self.assertEqual(self.client.get(self.base+'/backups/'+key+'.zip').status_code,409)

    def test_demo_new_actions_are_read_only(self):
        from demo import DEMO_ID
        for suffix in ('/expand','/backups','/observations/anything'):
            self.assertEqual(self.client.post('/cases/'+DEMO_ID+suffix,json=dict(kind='email',target='x@y.example',tools=['console'])).status_code,403)

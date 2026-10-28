"""Focused checks for search, entity context, sharing review and starters."""
import copy
import tempfile
from pathlib import Path
from unittest import TestCase
from unittest.mock import patch

import app
import case_tools
from case_graphs import validate_graph
from demo import demo_case


class CaseToolsTests(TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup)
        patcher=patch.object(app,'CASES_DIR',Path(temp.name)/'cases');patcher.start();self.addCleanup(patcher.stop)
        self.case=demo_case();self.case['id']='08abb170-4d96-4a57-868a-32ed21644ff2';self.case['is_demo']=False
        app.save_case(self.case);self.client=app.app.test_client();self.base='/cases/'+self.case['id']

    def test_search_scoped_to_case_and_all_content_types(self):
        for query,expected in [('MAYA','Maya Calder'),('2025550147','Volunteer coordinator contact details'),('theo.bennett@example.net','Workshop collaboration'),('Corroborate','Corroborate Theo account ownership'),('account control','Confidence:')]:
            response=self.client.get(self.base+'/search',query_string={'q':query})
            self.assertEqual(response.status_code,200);self.assertIn(expected.encode(),response.data)
        response=self.client.get(self.base+'/search?q=maya&kind=Entities')
        self.assertIn(b'/entities/',response.data);self.assertNotIn(b'Volunteer coordinator contact details</a>',response.data)
        self.assertIn(b'No matches',self.client.get(self.base+'/search?q=doesnotexist123').data)
        self.assertEqual(self.client.get('/cases/00000000-1111-4000-8000-000000000001/search?q=maya').status_code,404)
        case=copy.deepcopy(self.case);case['notes']='<script>alert(1)</script>';app.save_case(case)
        self.assertNotIn(b'<script>alert',self.client.get(self.base+'/search?q=alert').data)

    def test_entity_explicit_refs_tasks_and_confidence_not_names(self):
        graph=self.case['graphs'][0];gid=graph['id']
        response=self.client.get(self.base+'/entities/'+gid+'/theo')
        self.assertEqual(response.status_code,200)
        for text in (b'theo.bennett@example.net',b'Corroborate Theo account ownership',b'Low confidence',b'Workshop collaboration'):
            self.assertIn(text,response.data)
        self.assertNotIn(b'Similar-name profile ruled out</a>',response.data)
        case=copy.deepcopy(self.case);case['investigation']['tasks'].append(dict(id='unrelated',title='UNRELATED TASK',notes='',target='',due='',status='Open',timestamp=case['created_at']));app.save_case(case)
        response=self.client.get(self.base+'/entities/'+gid+'/theo');self.assertNotIn(b'UNRELATED TASK',response.data)
        self.assertEqual(self.client.get(self.base+'/entities/'+gid+'/missing').status_code,404)
        self.assertIn(b'Maya Calder',self.client.get(self.base+'/entities').data)

    def test_review_selection_hypotheses_sources_and_tasks(self):
        with app.app.test_request_context():
            issues=case_tools.sharing_review(self.case)
        categories={i['category'] for i in issues};self.assertTrue({'Verification','Connections','Tasks'}<=categories)
        case=copy.deepcopy(self.case);case['report_builder']['selected']=['finding:'+case['searches'][0]['id']+':0:0']
        case['searches'][0]['results'][0]['findings'][0].pop('source');case['searches'][0]['results'][0]['findings'][0].pop('source_url')
        with app.app.test_request_context():
            issues=case_tools.sharing_review(case)
        self.assertIn('Sources',{i['category'] for i in issues});self.assertNotIn('Connections',{i['category'] for i in issues})
        self.assertFalse(any(i['title']=='Theo Bennett profile candidate' for i in issues))
        response=self.client.get(self.base+'/sharing-review');self.assertEqual(response.status_code,200)
        self.assertIn(b'Review this item',response.data)

    def test_templates_create_independent_cases_and_leave_existing_intact(self):
        for key in ('footprint','organization','incident'):
            response=self.client.post('/cases',data=dict(case_name='Starter '+key,case_template=key))
            self.assertEqual(response.status_code,302)
            case=app.load_case(response.headers['Location'].split('/')[-1]);self.assertEqual(case['case_template'],key)
            self.assertEqual(len(case['investigation']['tasks']),3);validate_graph(case['graphs'][0])
            self.assertFalse(case['report_builder']['summary']['findings'])
            self.assertEqual(case['searches'],[])
        blank=app.create_case('Blank');self.assertNotIn('graphs',blank)
        with self.assertRaises(ValueError):case_tools.prepare_template(self.case,'incident')
        self.assertEqual(self.client.post('/cases',data=dict(case_name='Invalid',case_template='fake')).status_code,400)
        self.assertIn(b'Starting template',self.client.get('/cases').data)
        self.assertEqual(app.load_case(self.case['id'])['searches'],self.case['searches'])

"""Focused coverage of investigation workflows and redaction boundaries."""
import copy
import tempfile
from pathlib import Path
from unittest import TestCase
from unittest.mock import patch

from docx import Document

import app
import case_backups
import investigation
import report_builder
from demo import demo_case
from word_report import build_word_report


class InvestigationTests(TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(); self.addCleanup(temp.cleanup)
        patcher = patch.object(app, 'CASES_DIR', Path(temp.name)/'cases'); patcher.start(); self.addCleanup(patcher.stop)
        self.case = demo_case(); self.case['id'] = 'd2d44f61-b19c-4d03-8d20-8536ca367333'; self.case['is_demo'] = False
        app.save_case(self.case); self.client=app.app.test_client(); self.base='/cases/'+self.case['id']

    def post(self, action, **data):
        case=app.load_case(self.case['id'])
        return self.client.post(self.base+'/investigation/'+action, data=dict(version=case['updated_at'], **data))

    def test_timeline_notes_links_filters_and_conflicts(self):
        ref=self.case['searches'][0]['id']+':0:0'
        response=self.post('event', title='Reviewed source', notes='Explicit analyst note', timestamp='2026-10-26T10:00', target=ref)
        self.assertEqual(response.status_code,302)
        response=self.client.get(self.base+'/investigation?kind=Analyst+event&from=2026-10-26&to=2026-10-26')
        self.assertIn(b'Explicit analyst note', response.data); self.assertIn(('#finding-'+ref).encode(),response.data)
        response=self.client.post(self.base+'/investigation/task',data=dict(version='stale',title='No overwrite'))
        self.assertEqual(response.status_code,409)
        self.assertEqual(self.client.get(self.base+'/investigation?from=bad').status_code,400)

    def test_tasks_status_and_due_date_validation(self):
        self.assertEqual(self.post('task', title='Review email', due='2026-11-01', notes='Compare sources').status_code,302)
        case=app.load_case(self.case['id']); task=case['investigation']['tasks'][-1]
        self.assertEqual(self.post('task-status',id=task['id'],status='Complete').status_code,302)
        self.assertEqual(app.load_case(self.case['id'])['investigation']['tasks'][-1]['status'],'Complete')
        self.assertEqual(self.post('task',title='Bad date',due='2026-99-01').status_code,400)
        self.assertEqual(self.post('task-status',id='missing',status='Complete').status_code,400)

    def test_assessment_requires_reason_and_valid_source_and_exports(self):
        ref=self.case['searches'][0]['id']+':0:0'
        self.assertEqual(self.post('assessment',target=ref,confidence='High',notes='').status_code,400)
        self.assertEqual(self.post('assessment',target=ref,confidence='Medium',notes='Independent review',refs=[ref]).status_code,302)
        case=app.load_case(self.case['id']); data=report_builder.compose(case)
        self.assertIn('Confidence: Medium',str(data['blocks'])); self.assertIn('Supporting sources: Evidence 1',str(data['blocks']))
        self.assertEqual(self.post('assessment',target=ref,confidence='High',notes='Why',refs=['fake']).status_code,400)
        invalid=copy.deepcopy(case); invalid['investigation']['assessments'][ref]['confidence']='Certain'
        with self.assertRaises(ValueError):case_backups.validate_case(invalid)

    def test_redaction_all_exports_names_metadata_images_and_originals(self):
        self.assertEqual(self.post('redaction',enabled='on',terms='Maya Calder\nmaya.calder@cedartrail.example\n+1 202-555-0147\nCedar Trail Makers').status_code,302)
        case=app.load_case(self.case['id']); originals=copy.deepcopy(case)
        data=report_builder.compose(case)
        self.assertFalse(any('image' in b or 'image_url' in b for b in data['blocks']))
        for value in (data['summary'],data['blocks'],data['appendix'],data['display_name']):
            self.assertNotIn('Maya Calder',str(value));self.assertNotIn('maya.calder@cedartrail.example',str(value))
        self.assertEqual(case, originals)
        html=self.client.get(self.base+'/report.html');self.assertNotIn(b'Maya Calder',html.data);self.assertNotIn(b'data:image',html.data)
        self.assertIn(b'[REDACTED]',self.client.get(self.base+'/report.md').data)
        pdf=self.client.get(self.base+'/report.pdf');self.assertTrue(pdf.data.startswith(b'%PDF'))
        self.assertNotIn('Cedar',pdf.headers['Content-Disposition'])
        doc=Document(build_word_report(case));self.assertEqual(len(doc.inline_shapes),0)
        self.assertNotIn('Maya Calder','\n'.join(p.text for p in doc.paragraphs))
        self.assertIn('Maya Calder',str(app.load_case(self.case['id'])['searches']))
        self.assertEqual(self.post('redaction',terms='Maya Calder').status_code,302)
        self.assertIn('Maya Calder',str(report_builder.compose(app.load_case(self.case['id']))['blocks']))

    def test_demo_read_only_and_investigation_backup(self):
        case=demo_case(); investigation.validate(case['investigation'])
        self.assertEqual(self.client.get('/cases/'+case['id']+'/investigation').status_code,200)
        self.assertEqual(self.client.post('/cases/'+case['id']+'/investigation/task',data={}).status_code,403)
        case_backups.validate_case(self.case)
        invalid=copy.deepcopy(self.case);invalid['investigation']['redaction']['terms']=[{}]
        with self.assertRaises(ValueError):case_backups.validate_case(invalid)

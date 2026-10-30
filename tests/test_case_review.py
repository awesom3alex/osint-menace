"""Analyst decisions, chronology privacy, recovery, and advisory health checks."""
import copy
from io import BytesIO
from unittest import TestCase

from docx import Document

import app
import case_backups
import case_review as review
import report_builder
import tests.test_case_research as fixtures
import workspace_store
from case_graphs import new_graph


class ReviewTests(TestCase):
    setUp = fixtures.ResearchTests.setUp

    def history(self, target_case=None):
        key='f'*32
        workspace_store.put(key,'console',dict(id=key,kind='email',target='lead@example.com',timestamp=app.utc_now(),origin_case_id=target_case or self.case['id'],results=[dict(name='Public source',module=dict(name='Fixture',mode='passive'),findings=[dict(label='Candidate account',value='candidate@example.com')],links=[],notes=[])]))
        return key

    def items(self):
        with app.app.test_request_context():
            return review.inbox_items(app.load_case(self.case['id']))

    def decision(self, item, action, **extra):
        case=app.load_case(self.case['id'])
        return self.client.post(self.base+'/inbox',data=dict(key=item['key'],action=action,updated_at=case['updated_at'],notes='Analyst reviewed.',**extra))

    def graph_case(self):
        case=app.load_case(self.case['id']);graph=new_graph('Identity comparison')
        graph['nodes']=[dict(id=key,label=label,type='Person',position=dict(x=i*100,y=0),fields=[dict(name='Email',type='text',value='shared@example.com',options='',visible=True),dict(name='Location',type='text',value=city,options='',visible=True)],source=self.ref) for i,(key,label,city) in enumerate([('a','Morgan A','North'),('b','Morgan B','South')])]
        graph['edges']=[dict(id='edge1',source='a',target='b',label='Worked together',status='hypothesis',date='2026-01-02',notes='Claim needs review.',evidenceRefs=[self.ref])]
        case['graphs']=[graph];app.save_case(case)
        return case,graph

    def test_inbox_case_scope_accept_and_duplicate_prevention(self):
        self.history('another-case')
        self.assertEqual(self.items(),[])
        self.history();item=self.items()[0]
        before=app.load_case(self.case['id'])['searches']
        self.assertEqual(self.decision(item,'accept').status_code,302)
        current=app.load_case(self.case['id'])
        self.assertEqual(current['searches'][:-1],before)
        self.assertEqual(current['searches'][-1]['results'][0]['findings'][0]['verification_status'],'Unverified')
        self.assertEqual(self.decision(item,'accept').status_code,409)
        self.assertEqual(len(app.load_case(self.case['id'])['searches']),len(before)+1)
        self.assertIn(b'Candidate account',self.client.get(self.base+'/inbox?state=reviewed').data)

    def test_inbox_link_dismiss_and_stale_decisions(self):
        self.history();item=self.items()[0]
        original=copy.deepcopy(app.load_case(self.case['id'])['searches'])
        self.assertEqual(self.decision(item,'link',ref=self.ref).status_code,302)
        self.assertEqual(app.load_case(self.case['id'])['searches'],original)
        self.assertIn(b'Linked review source',self.client.get(self.base).data)
        self.assertEqual(self.client.post(self.base+'/inbox',data=dict(key=item['key'],action='dismiss',updated_at='stale')).status_code,409)

    def test_changed_source_acceptance_does_not_overwrite_evidence(self):
        case=app.load_case(self.case['id']);finding=case['searches'][0]['results'][0]['findings'][0]
        finding['observations']=[dict(fixtures.capture(text),id=key*32,timestamp='2026-01-01T00:00:00+00:00') for text,key in [('old text','a'),('new text','b')]]
        original=copy.deepcopy(finding);app.save_case(case)
        item=self.items()[0];self.assertEqual(item['kind'],'Source change')
        self.assertEqual(self.decision(item,'accept').status_code,302)
        self.assertEqual(app.load_case(self.case['id'])['searches'][0]['results'][0]['findings'][0],original)
        self.assertNotIn(b'new text',self.client.get(self.base+'/inbox').data)
        self.assertIn(b'new text',self.client.get(self.base+'/inbox?state=reviewed').data)

    def test_identity_suggestions_and_retained_conflicting_fields(self):
        case,graph=self.graph_case();left=graph['id']+':a';right=graph['id']+':b'
        self.assertEqual(len(review.identity_suggestions(review.entities(case))),1)
        response=self.client.get(self.base+'/resolve',query_string=dict(left=left,right=right))
        self.assertEqual(response.status_code,200);self.assertIn(b'North',response.data);self.assertIn(b'South',response.data)
        saved=self.client.post(self.base+'/resolve',data=dict(left=left,right=right,decision='related',reason='Shared mailbox alone does not establish identity.',updated_at=case['updated_at']))
        self.assertEqual(saved.status_code,302)
        result=app.load_case(case['id']);self.assertEqual(result['graphs'],case['graphs'])
        self.assertEqual(result['entity_resolutions'][0]['left_snapshot']['node']['fields'][1]['value'],'North')
        self.assertEqual(result['entity_resolutions'][0]['right_snapshot']['node']['fields'][1]['value'],'South')
        for item in graph['nodes']:item['fields']=[];item['label']='Same name'
        self.assertEqual(review.identity_suggestions(review.entities(case)),[])
        with self.assertRaises(ValueError):
            invalid=copy.deepcopy(result);invalid['entity_resolutions'][0]['left_snapshot']['node']['fields']='bad';case_backups.validate_case(invalid)

    def test_chronology_date_semantics_report_selection_and_redaction(self):
        case,graph=self.graph_case()
        case['investigation']=dict(timeline=[dict(id='event',title='SECRET-NAME event',timestamp='2026-01-01T12:30:00+00:00',notes='Observed event',target=self.ref)],redaction=dict(enabled=True,terms=['SECRET-NAME','analyst@example.com']))
        app.save_case(case);rows=review.timeline_rows(case)
        self.assertTrue(any(row['basis']=='Collection time' for row in rows))
        self.assertTrue(any(row['basis'].startswith('Relationship event') for row in rows))
        response=self.client.post(self.base+'/timeline-export',data=dict(selected=[row['id'] for row in rows],updated_at=case['updated_at'],include_report='on'))
        self.assertEqual(response.status_code,302)
        saved=app.load_case(case['id']);data=report_builder.compose(saved)
        block=next(block for block in data['blocks'] if block['label']=='Investigation chronology')
        self.assertIn('Event time',str(block['details']))
        self.assertIn('Evidence 1',str(block['details']))
        self.assertNotIn('SECRET-NAME',str(block))
        pdf=self.client.get(self.base+'/timeline.pdf');word=self.client.get(self.base+'/timeline.docx')
        self.assertEqual(pdf.status_code,200);self.assertTrue(pdf.data.startswith(b'%PDF'))
        self.assertEqual(word.status_code,200)
        text='\n'.join(p.text for p in Document(BytesIO(word.data)).paragraphs)
        self.assertIn('Collection time',text);self.assertIn('Event time',text);self.assertNotIn('SECRET-NAME',text)
        self.assertIn('[REDACTED]',text)
        saved['searches'][0]['results'][0]['findings'][0]['include_in_report']=False
        self.assertEqual(review.timeline_rows(saved),[])

    def test_unselected_and_excluded_chronology_never_exports(self):
        case=app.load_case(self.case['id'])
        self.assertEqual(self.client.get(self.base+'/timeline.pdf').status_code,400)
        response=self.client.post(self.base+'/timeline-export',data=dict(updated_at=case['updated_at'],selected=['a'*64]))
        self.assertEqual(response.status_code,400)
        self.assertFalse(app.load_case(case['id']).get('timeline_export'))

    def test_health_flags_provenance_attachments_tasks_and_claims(self):
        case,graph=self.graph_case();finding=case['searches'][0]['results'][0]['findings'][0]
        finding['source_url']='';finding['evidence']=[dict(id='e'*32,caption='Missing screenshot')]
        graph['edges'][0]['evidenceRefs']=[]
        case['investigation']=dict(tasks=[dict(id='task',title='Late review',status='Open',due='2000-01-01')],assessments={self.ref:dict(confidence='High',reason='Needs support',refs=[])})
        app.save_case(case)
        with app.app.test_request_context():
            kinds={issue['kind'] for issue in review.health_issues(case)}
        self.assertTrue({'Source provenance','Missing attachment','Overdue task','Unsupported connection','Unsupported assessment'}<=kinds)
        response=self.client.get(self.base+'/health');self.assertEqual(response.status_code,200);self.assertIn(b'Missing screenshot',response.data)

    def test_review_data_survives_case_backup(self):
        self.history();self.decision(self.items()[0],'dismiss')
        case,graph=self.graph_case()
        self.client.post(self.base+'/resolve',data=dict(left=graph['id']+':a',right=graph['id']+':b',decision='different_entities',reason='Conflicting identifiers corroborated independently.',updated_at=case['updated_at']))
        case=app.load_case(case['id'])
        with case_backups.archive_case(case) as stream:
            path=self.root/'review-backup.zip';path.write_bytes(stream.read())
        restored,_,_=case_backups.checked_zip(path)
        self.assertEqual(restored['review_inbox'],case['review_inbox'])
        self.assertEqual(restored['entity_resolutions'],case['entity_resolutions'])
        invalid=copy.deepcopy(case);invalid['review_inbox']={'x':dict(action='wrong')}
        with self.assertRaises(ValueError):case_backups.validate_case(invalid)

    def test_new_review_actions_protect_demo(self):
        from demo import DEMO_ID
        for suffix in ('/inbox','/resolve','/timeline-export'):
            self.assertEqual(self.client.post('/cases/'+DEMO_ID+suffix,data={}).status_code,403)

"""Exactly three focused tests for persistent saved status and reviewed imports."""
import copy
import json
from unittest import TestCase

import app
import case_backups
import research_hub as hub
import tests.test_case_research as fixtures
import workspace_store as store


class PreviewTests(TestCase):
    setUp=fixtures.ResearchTests.setUp

    def results(self):
        key='e'*32
        entries=[dict(id=letter*32,queries=['fictional query'],finding=hub.finding('Original '+letter,dict(title='Original '+letter,snippet='Original source content'),'Fixture','https://example.org/'+letter)) for letter in ('a','b')]
        hub.finish(dict(id=key,record_type='global_search',collector='ddgs',kind='global:web',target='fictional query',timestamp=store.now(),context_case_id=self.case['id']),entries)
        return '/research/results/'+key

    def test_saved_state_is_durable_case_specific_and_includes_inbox_acceptance(self):
        url=self.results()
        response=self.client.get(url+'/saved',query_string=dict(case_id=self.case['id']))
        self.assertEqual(response.get_json()['saved_ids'],[])
        self.assertEqual(response.headers['Cache-Control'],'no-store')
        self.assertEqual(self.client.post(url+'/action',data=dict(single_entry='a'*32,case_id=self.case['id'])).status_code,302)
        self.assertEqual(self.client.get(url+'/saved',query_string=dict(case_id=self.case['id'])).get_json()['saved_ids'],['a'*32])
        other=app.create_case('Other destination')
        self.assertEqual(self.client.get(url+'/saved',query_string=dict(case_id=other['id'])).get_json()['saved_ids'],[])
        # The durable source metadata also identifies findings accepted by other workflows.
        case=app.load_case(self.case['id']);section=hub.section_for(store.get('e'*32)['entries'][1],'e'*32)
        case['searches'].append(app.make_search_record('web','fictional query',[section],app.result_summary([section])))
        app.save_case(case)
        client=app.app.test_client()
        self.assertEqual(client.get(url+'/saved',query_string=dict(case_id=self.case['id'])).get_json()['saved_ids'],['a'*32,'b'*32])
        self.assertEqual(client.get(url).status_code,200)

    def test_single_and_batch_reviews_keep_originals_provenance_and_backup_metadata(self):
        url=self.results();original=copy.deepcopy(store.get('e'*32))
        edits={'a'*32:dict(title='Reviewed phone lead',notes='Requires follow-up.',tags=['Public','public',' Phone '],type='Phone')}
        response=self.client.post(url+'/action',data=dict(single_entry='a'*32,case_id=self.case['id'],review_edits=json.dumps(edits)),headers={'Accept':'application/json'})
        self.assertEqual(response.status_code,200,response.data)
        case=app.load_case(self.case['id']);finding=case['searches'][-1]['results'][0]['findings'][0]
        self.assertEqual(finding['label'],'Reviewed phone lead')
        self.assertEqual(finding['research_original_label'],'Original a')
        self.assertEqual(finding['value']['title'],'Original a')
        self.assertEqual(finding['analyst_notes'],'Requires follow-up.')
        self.assertEqual(finding['tags'],['Public','Phone'])
        self.assertEqual(finding['finding_type'],'Phone')
        self.assertEqual(finding['verification_status'],'Unverified')
        self.assertEqual(finding['research_source'],dict(record_id='e'*32,entry_id='a'*32))
        edits={'b'*32:dict(title='Second reviewed lead',notes='Batch note.',tags=['Follow-up'],type='URL')}
        response=self.client.post(url+'/action',data=dict(action='case',selected=['a'*32,'b'*32],case_id=self.case['id'],review_edits=json.dumps(edits)),headers={'Accept':'application/json'})
        self.assertEqual(response.status_code,200,response.data)
        self.assertEqual(response.get_json()['added'],1)
        case=app.load_case(self.case['id']);case_backups.validate_case(case)
        self.assertEqual(case['searches'][-1]['results'][0]['findings'][0]['label'],'Second reviewed lead')
        self.assertEqual(store.get('e'*32),original)
        self.assertIn(b'Type: Phone',self.client.get(self.base).data)

    def test_invalid_review_is_atomic_and_preview_has_safe_editable_controls(self):
        url=self.results();before=app.load_case(self.case['id'])
        for edits in ({'a'*32:dict(title='')},{'a'*32:dict(title='Lead',type='unsupported')},{'a'*32:dict(title='Lead',tags=['x'*41])},{'b'*32:dict(title='Wrong selected result')},{'a'*32:dict(title='Lead',source_url='https://tampered.example/')}):
            response=self.client.post(url+'/action',data=dict(single_entry='a'*32,case_id=self.case['id'],review_edits=json.dumps(edits)),headers={'Accept':'application/json'})
            self.assertEqual(response.status_code,400,response.data)
        self.assertEqual(app.load_case(self.case['id']),before)
        page=self.client.get(url)
        for marker in (b'research-save-preview',b'review_title',b'review_notes',b'review_type',b'review_tags',b'data-saved-url'):
            self.assertIn(marker,page.data)
        self.assertEqual(self.client.get('/research/results/'+'f'*32+'/saved').status_code,404)

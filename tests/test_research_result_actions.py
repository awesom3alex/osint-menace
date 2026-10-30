"""Three focused checks for individual and batch Add To Case actions."""
from unittest import TestCase

import app
import research_hub as hub
import tests.test_case_research as fixtures
import workspace_store as store


class ResultActionTests(TestCase):
    setUp=fixtures.ResearchTests.setUp

    def results(self):
        key='e'*32
        entries=[dict(id=letter*32,queries=['fictional query'],finding=hub.finding('Fictional '+letter,dict(snippet='Public fixture '+letter),'Fixture','https://example.org/'+letter)) for letter in ('a','b')]
        record=dict(id=key,record_type='global_search',collector='ddgs',kind='global:web',target='fictional query',timestamp=store.now(),context_case_id=self.case['id'])
        hub.finish(record,entries)
        return '/research/results/'+key

    def test_individual_button_saves_only_its_result_even_with_other_checkboxes(self):
        url=self.results()
        response=self.client.post(url+'/action',data=dict(single_entry='a'*32,selected='b'*32,case_id=self.case['id']),headers={'Accept':'application/json'})
        self.assertEqual(response.status_code,200)
        self.assertEqual(response.get_json()['selected_ids'],['a'*32])
        self.assertIn('Added 1 result',response.get_json()['message'])
        case=app.load_case(self.case['id'])
        saved=case['searches'][-1]['results']
        self.assertEqual(len(saved),1)
        self.assertEqual(saved[0]['findings'][0]['label'],'Fictional a')
        self.assertEqual(saved[0]['findings'][0]['verification_status'],'Unverified')
        self.assertEqual(saved[0]['findings'][0]['source_url'],'https://example.org/a')
        self.assertEqual(self.client.post(url+'/action',data=dict(single_entry='a'*32,case_id=self.case['id'])).status_code,409)

    def test_batch_add_preserves_provenance_and_skips_already_saved_results(self):
        url=self.results()
        self.client.post(url+'/action',data=dict(single_entry='a'*32,case_id=self.case['id']))
        response=self.client.post(url+'/action',data=dict(action='case',selected=['a'*32,'b'*32],case_id=self.case['id']),headers={'Accept':'application/json'})
        self.assertEqual(response.status_code,200)
        self.assertEqual(response.get_json()['added'],1)
        case=app.load_case(self.case['id'])
        self.assertEqual(len(case['searches']),3)
        finding=case['searches'][-1]['results'][0]['findings'][0]
        self.assertEqual(finding['research_source'],dict(record_id='e'*32,entry_id='b'*32))
        self.assertEqual(finding['label'],'Fictional b')
        self.assertEqual(self.client.post(url+'/action',data=dict(action='case',selected=['a'*32,'b'*32],case_id=self.case['id'])).status_code,409)

    def test_controls_and_invalid_requests_do_not_change_cases(self):
        url=self.results()
        page=self.client.get(url)
        self.assertEqual(page.status_code,200)
        self.assertEqual(page.data.count(b'name="single_entry"'),2)
        self.assertIn(b'Add Selected To Case (0)',page.data)
        self.assertIn(b'research-results.js',page.data)
        before=app.load_case(self.case['id'])
        for data in (dict(single_entry='bad',case_id=self.case['id']),dict(single_entry='a'*32),dict(action='case',case_id=self.case['id']),dict(single_entry=['a'*32,'b'*32],case_id=self.case['id'])):
            response=self.client.post(url+'/action',data=data,headers={'Accept':'application/json'})
            self.assertEqual(response.status_code,400)
            self.assertIn('error',response.get_json())
        self.assertEqual(app.load_case(self.case['id']),before)
        fallback=self.client.post(url+'/action',data=dict(single_entry='b'*32,case_id=self.case['id'],return_page=2,return_domain='example.org'))
        self.assertEqual(fallback.status_code,302)
        self.assertTrue(fallback.location.startswith(url+'?'))
        self.assertIn('page=2',fallback.location)

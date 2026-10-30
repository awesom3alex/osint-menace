"""Focused research workflows using temporary storage and offline providers."""
import copy
import hashlib
from unittest import TestCase
from unittest.mock import MagicMock, patch

import app
import case_backups
import case_review
import research_hub as hub
import tests.test_case_research as fixtures
import workspace_store as store


class ResearchHubTests(TestCase):
    setUp = fixtures.ResearchTests.setUp

    def preview(self, **settings):
        response = self.client.post('/api/global-search/preview', json=dict(q='Example research', **settings))
        self.assertEqual(response.status_code, 200, response.data)
        return response.get_json()

    def search(self):
        entry = dict(id='a'*32, domain='example.org', queries=['Example research'], finding=hub.finding('Example result', dict(title='Example result', snippet='Public snippet', url='https://example.org/'), 'DDGS / duckduckgo', 'https://example.org/'))
        with patch.object(hub, 'run_ddgs', return_value=([entry], [], [])):
            response = self.client.post('/api/global-search/run', json=dict(token=self.preview(case_id=self.case['id'])['token']))
        self.assertEqual(response.status_code, 200)
        return response.get_json()['url'], entry

    def test_preview_bookmarks_navigation_and_token_validation(self):
        with patch.object(hub, 'run_ddgs') as run:
            preview = self.preview(mode='social')
            self.assertIn('site:linkedin.com', preview['plan']['queries'][0])
            for route in ('/global-search', '/research-tools'):
                response = self.client.get(route)
                self.assertEqual(response.status_code, 200, response.data)
            saved = self.client.post('/api/global-search/bookmarks', json=dict(token=preview['token']))
            self.assertEqual(saved.status_code, 200)
            self.assertEqual(self.client.get(saved.get_json()['url']).status_code, 200)
            self.assertEqual(store.history(), [])
            run.assert_not_called()
        self.assertEqual(self.client.post('/api/global-search/run', json=dict(token='tampered')).status_code, 400)
        self.assertEqual(self.client.post('/api/global-search/preview', json=dict(q='x', sites='https://example.org')).status_code, 400)
        self.assertEqual(self.client.post('/api/global-search/preview', json=dict(q='x', mode='news', backend='brave')).status_code, 400)
        phone = hub.search_plan(dict(q='+1 202-555-0147', mode='phone'))
        self.assertGreater(len(phone['queries']), 1)
        self.assertLessEqual(len(phone['queries']), 3)

    def test_adapter_deduplicates_filters_and_retains_partial_failures(self):
        plan = hub.search_plan(dict(q='+1 202-555-0147', mode='phone', sites='example.org'))
        sdk = MagicMock()
        sdk.text.side_effect = [[dict(title='A', href='https://example.org/a#fragment', body='text'), dict(title='Duplicate', href='https://example.org/a'), dict(href='https://other.example/a'), dict(href='javascript:alert(1)')], RuntimeError('private provider detail'), []]
        with patch('ddgs.DDGS', return_value=sdk):
            entries, errors, ledger = hub.run_ddgs(plan)
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]['finding']['source_url'], 'https://example.org/a')
        self.assertTrue(errors)
        self.assertNotIn('private provider detail', str(errors))
        self.assertEqual(ledger[1]['status'], 'failed')
        self.assertEqual(sdk.text.call_args.kwargs['backend'], 'duckduckgo')

    def test_results_exports_and_direct_save_preserve_provenance(self):
        url, entry = self.search()
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200, response.data)
        self.assertIn(b'Public snippet', response.data)
        action = url+'/action'
        self.assertEqual(self.client.post(action, data=dict(action='case', case_id=self.case['id'], selected='invalid')).status_code, 400)
        exported = self.client.post(action, data=dict(action='json', selected=entry['id']))
        self.assertEqual(exported.get_json()['entries'][0]['finding']['value']['snippet'], 'Public snippet')
        csv = self.client.post(action, data=dict(action='csv', selected=entry['id']))
        self.assertIn(b'Example result', csv.data)
        self.assertEqual(self.client.post(action, data=dict(action='case', case_id=self.case['id'], selected=entry['id'])).status_code, 302)
        self.assertEqual(self.client.post(action, data=dict(action='case', case_id=self.case['id'], selected=entry['id'])).status_code, 409)
        case = app.load_case(self.case['id'])
        finding = case['searches'][-1]['results'][0]['findings'][0]
        self.assertEqual(finding['verification_status'], 'Unverified')
        self.assertEqual(finding['research_source']['entry_id'], entry['id'])
        case_backups.validate_case(case)
        self.assertEqual(self.client.get('/history/'+url.rsplit('/',1)[-1]).status_code, 302)

    def test_review_inbox_requires_acceptance_and_prevents_duplicate_save(self):
        url, entry = self.search()
        before = copy.deepcopy(app.load_case(self.case['id'])['searches'])
        data = dict(action='inbox', case_id=self.case['id'], selected=entry['id'])
        self.assertEqual(self.client.post(url+'/action', data=data).status_code, 302)
        self.assertEqual(app.load_case(self.case['id'])['searches'], before)
        self.assertEqual(self.client.post(url+'/action', data=data).status_code, 409)
        with app.app.test_request_context():
            item = case_review.inbox_items(app.load_case(self.case['id']))[0]
        case = app.load_case(self.case['id'])
        accepted = self.client.post(self.base+'/inbox', data=dict(action='accept', key=item['key'], updated_at=case['updated_at'], notes='Reviewed'))
        self.assertEqual(accepted.status_code, 302, accepted.data)
        data['action'] = 'case'
        self.assertEqual(self.client.post(url+'/action', data=data).status_code, 409)

    def test_address_original_is_exact_and_local(self):
        original = ' 123 Main St Apt 4, Springfield IL 62704 '
        with patch.object(hub, 'address_location') as remote:
            response = self.client.post('/api/research-tools/run', json=dict(tool='address_breakdown', original=original))
            remote.assert_not_called()
        item = store.get(response.get_json()['url'].rsplit('/',1)[-1])
        self.assertEqual(item['status'], 'completed', item)
        value = item['entries'][0]['finding']['value']
        self.assertEqual(value['original'], original)
        self.assertEqual(value['components']['AddressNumber'], '123')
        self.assertIn('not verify', value['limitations'])
        self.assertEqual(self.client.get(response.get_json()['url']).status_code, 200)

    def test_geocoder_confirmation_candidates_and_attribution(self):
        with patch.dict('os.environ', {'MENACE_GEOCODER_URL':''}):
            with self.assertRaises(ValueError):hub.address_location('Public landmark', {})
            location = MagicMock(latitude=48.8584, longitude=2.2945, address='Public landmark', raw=dict(osm_type='way', osm_id=123, licence='Fixture attribution', address=dict(city='Paris')))
            with patch('geopy.geocoders.Nominatim') as provider, patch.object(hub, 'LAST_GEOCODE', 0):
                provider.return_value.geocode.return_value = [location]
                entries = hub.address_location('Public landmark', dict(public_location=True, language='en', country='FR'))
                provider.return_value.geocode.assert_called_once_with('Public landmark', exactly_one=False, limit=5, addressdetails=True, language='en', country_codes='fr')
            value = entries[0]['finding']['value']
            self.assertEqual(value['attribution'], 'Fixture attribution')
            self.assertEqual(value['original'], 'Public landmark')
            self.assertIn('Candidate', value['limitations'])

    def test_profile_fetch_is_bounded_parsed_locally_and_not_auto_saved(self):
        body = b'<html>Public profile fixture</html>'
        result = MagicMock(returncode=0, stdout=b'{"username":"fictional_user","name":"Morgan Example"}')
        before = copy.deepcopy(app.load_case(self.case['id'])['searches'])
        with patch('collectors.fetch', return_value=dict(status='found', url='https://example.org/profile', body=body, headers={'content-type':'text/html'})) as fetch, patch.object(hub.subprocess, 'run', return_value=result) as worker:
            response = self.client.post('/api/research-tools/run', json=dict(tool='profile_details', original='https://example.org/profile', case_id=self.case['id']))
            self.assertEqual(fetch.call_args.kwargs['max_bytes'], 1_000_000)
            self.assertEqual(worker.call_args.kwargs['timeout'], 12)
        item = store.get(response.get_json()['url'].rsplit('/',1)[-1])
        self.assertEqual(item['status'], 'completed', item)
        self.assertEqual(item['entries'][0]['finding']['value']['page_sha256'], hashlib.sha256(body).hexdigest())
        self.assertEqual(app.load_case(self.case['id'])['searches'], before)
        with patch('collectors.fetch') as fetch:
            with self.assertRaises(ValueError):hub.profile_details('https://user:password@example.org/')
            fetch.assert_not_called()

    def test_failed_provider_and_restart_retained_without_case_changes(self):
        with patch.object(hub, 'profile_details', side_effect=ValueError('No supported public fields')):
            response = self.client.post('/api/research-tools/run', json=dict(tool='profile_details', original='https://example.org/'))
        item = store.get(response.get_json()['url'].rsplit('/',1)[-1])
        self.assertEqual(item['status'], 'failed')
        self.assertIn('No supported public fields', item['errors'][0])
        store.put('b'*32, 'global_search', dict(id='b'*32, record_type='global_search', target='Retained input', status='running', timestamp=store.now(), results=[]))
        store.recover_research()
        recovered = store.get('b'*32)
        self.assertEqual(recovered['target'], 'Retained input')
        self.assertEqual(recovered['status'], 'interrupted')
        self.assertTrue(recovered['errors'])

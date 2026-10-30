"""Exactly three focused tests for the research-tool expansion."""
import copy
import importlib.util
import json
from unittest import TestCase, skipUnless
from unittest.mock import MagicMock, patch
from urllib.parse import parse_qs, urlsplit

import app
import research_extensions as ext
import research_hub as hub
import tests.test_case_research as fixtures
import workspace_store as store


class ExtensionTests(TestCase):
    setUp=fixtures.ResearchTests.setUp

    def run_tool(self,tool,original,**options):
        response=self.client.post('/api/research-tools/run',json=dict(tool=tool,original=original,case_id=self.case['id'],**options))
        self.assertEqual(response.status_code,200,response.data)
        url=response.get_json()['url'];item=store.get(url.rsplit('/',1)[-1])
        self.assertEqual(self.client.get(url).status_code,200)
        return item,url

    def test_telephone_panel_sources_provenance_and_selected_case_save(self):
        original='(202) 555-0147'
        before=copy.deepcopy(app.load_case(self.case['id'])['searches'])
        with patch.object(hub,'run_ddgs') as web,patch.object(ext.subprocess,'run') as scanner:
            item,url=self.run_tool('telephone',original,phone_region='US')
            self.assertEqual(item['status'],'completed',item)
            web.assert_not_called();scanner.assert_not_called()
        value=item['entries'][0]['finding']['value']
        self.assertEqual(value['original'],original)
        self.assertEqual(value['e164'],'+12025550147')
        self.assertIn('not a live location',value['limitations'])
        self.assertEqual(app.load_case(self.case['id'])['searches'],before)
        with patch('addon_tools.executable') as binary,patch.object(ext.subprocess,'run',return_value=MagicMock(returncode=0,stdout=b'Fixture PhoneInfoga lead')) as scanner,patch.object(hub,'run_ddgs',return_value=([],['Provider rate limit'],[])) as web:
            binary.return_value.is_file.return_value=True
            external,_=self.run_tool('telephone',original,phone_region='US',phoneinfoga=True,phone_web=True,phone_engine='duckduckgo')
            self.assertEqual(external['status'],'partial')
            self.assertEqual(len(external['entries']),2)
            self.assertEqual(scanner.call_args.kwargs['timeout'],30)
            self.assertNotIn('INSTAGRAM_SESSION_ID',scanner.call_args.kwargs['env'])
            self.assertEqual(web.call_args.args[0]['config']['mode'],'phone')
        data=dict(action='case',case_id=self.case['id'],selected=item['entries'][0]['id'])
        self.assertEqual(self.client.post(url+'/action',data=data).status_code,302)
        self.assertEqual(self.client.post(url+'/action',data=data).status_code,409)
        finding=app.load_case(self.case['id'])['searches'][-1]['results'][0]['findings'][0]
        self.assertEqual(finding['verification_status'],'Unverified')
        self.assertEqual(finding['value']['original'],original)
        self.assertTrue(finding['research_source'])

    def test_nearby_places_preserves_original(self):
        with patch.object(ext,'request_json') as provider:
            with self.assertRaises(ValueError):ext.nearby_places('48.8584, 2.2945',dict(radius=250,category='amenities'))
            provider.assert_not_called()
        raw=dict(version=0.6,generator='Fixture',elements=[dict(type='node',id=1,lat=48.8585,lon=2.2945,tags=dict(name='Fictional Cafe',amenity='cafe')),dict(type='way',id=2,center=dict(lat=48.859,lon=2.2945),nodes=[],tags=dict(name='Fictional Hall',amenity='community_centre'))])
        with patch.object(ext,'request_json',return_value=raw) as provider,patch.object(ext,'LAST_NEARBY',0):
            item,url=self.run_tool('nearby_places','48.8584, 2.2945',radius='250',category='amenities',nearby_confirm=True)
        self.assertEqual(item['status'],'completed',item)
        self.assertEqual(len(item['entries']),2)
        value=item['entries'][0]['finding']['value']
        self.assertEqual(value['tags']['name'],'Fictional Cafe')
        self.assertEqual(value['approximate_distance_m'],11)
        self.assertIn('OpenStreetMap',value['attribution'])
        self.assertIn('around:250,48.8584,2.2945',parse_qs(urlsplit(provider.call_args.args[0]).query)['data'][0])
        queued=self.client.post(url+'/action',data=dict(action='inbox',case_id=self.case['id'],selected=item['entries'][0]['id']))
        self.assertEqual(queued.status_code,302)
        self.assertEqual(len(app.load_case(self.case['id'])['searches']),1)

    @skipUnless(importlib.util.find_spec('postal'), 'Requires libpostal models and postal bindings (Docker)')
    def test_real_international_parser_preserves_original(self):
        original=' 10 Downing Street, London SW1A 2AA, United Kingdom '
        parsed,url=self.run_tool('international_address',original)
        self.assertEqual(parsed['status'],'completed',parsed)
        value=parsed['entries'][0]['finding']['value']
        self.assertEqual(value['original'],original)
        self.assertTrue(any(c['label']=='house_number' and c['value']=='10' for c in value['components']))
        self.assertTrue(value['normalized_suggestions'])
        self.assertLessEqual(len(value['normalized_suggestions']),10)
        self.assertEqual(parsed['entries'][0]['mode'],'local')
        self.assertIn(b'International Address Breakdown',self.client.get('/research-tools?tool=international_address').data)

    def test_archive_dates_exact_matching_and_review_before_save(self):
        columns='urlkey,timestamp,original,mimetype,statuscode,digest,length'.split(',')
        row=['org,example)/about','20240102030405','https://example.org/about','text/html','200','DIGEST','123']
        with patch.object(ext,'request_json',return_value=[columns,row,row,['x','20240102030405','https://other.example/about','text/html','200','OTHER','1']]) as provider:
            item,url=self.run_tool('archive_history','https://example.org/about',archive_confirm=True,archive_from='2024-01-01',archive_to='2024-12-31')
        self.assertEqual(item['status'],'completed',item)
        self.assertEqual(len(item['entries']),1)
        value=item['entries'][0]['finding']['value']
        self.assertEqual(value['capture_time'],'2024-01-02T03:04:05Z')
        self.assertIn('/20240102030405/https://example.org/about',value['archive_url'])
        params=parse_qs(urlsplit(provider.call_args.args[0]).query)
        self.assertEqual(params['matchType'],['exact'])
        self.assertEqual(params['to'],['20241231235959'])
        self.assertEqual(len(app.load_case(self.case['id'])['searches']),1)
        exported=self.client.post(url+'/action',data=dict(action='json',selected=item['entries'][0]['id']))
        self.assertEqual(json.loads(exported.data)['entries'][0]['finding']['value']['digest'],'DIGEST')
        with patch.object(ext,'request_json') as provider:
            with self.assertRaises(ValueError):ext.archive_history('http://127.0.0.1/private',dict(archive_confirm=True))
            with self.assertRaises(ValueError):ext.archive_history('https://example.org/about',dict(archive_confirm=True,archive_from='2025-01-01',archive_to='2024-01-01'))
            with self.assertRaises(ValueError):ext.archive_history('https://example.org/about',{})
            provider.assert_not_called()

"""Exactly three focused tests for readable telephone output and local API settings."""
import json
from unittest import TestCase
from unittest.mock import MagicMock, patch

import addon_tools as addons
import telephone_output
import tests.test_case_research as fixtures
import tool_credentials as credentials
import workspace_features
import workspace_store as store


class TelephoneCredentialTests(TestCase):
    def setUp(self):
        fixtures.ResearchTests.setUp(self)
        setting=patch.object(credentials,'PATH',self.root/'private'/'credentials.json');setting.start();self.addCleanup(setting.stop)

    def test_readable_phone_results_provider_gaps_and_ignorant_signals(self):
        text='time="now" level=debug msg="Scanner was ignored" reason="API key is not defined" scanner=numverify\nResults for googlesearch\nSocial media:\n URL: https://www.google.com/search?q=site%3Ainstagram.com+%22fictional%22\n'
        job=dict(id='a'*32,tool='phoneinfoga',target='+12025550147',kind='phone',timestamp=store.now(),created=0,status='completed',output=text)
        summary=telephone_output.view(job)
        self.assertEqual(summary['providers'][0]['status'],'Not configured')
        self.assertEqual(summary['groups'][0]['links'][0]['label'],'Search instagram.com')
        section=workspace_features.finding_section(job)
        self.assertIn('search shortcut',section['links'][0]['label'])
        self.assertNotIn('level=debug',json.dumps(section))
        store.put(job['id'],'addon',job)
        response=self.client.get('/history/'+job['id'])
        self.assertEqual(response.status_code,200)
        self.assertIn(b'Raw tool output',response.data)
        self.assertIn(b'Configure API',response.data)
        noisy='Twitter : @author\nFor BTC Donations : wallet\n[+] instagram.com\n[-] amazon.com\n[x] snapchat.com\n[+] Phone number used, [-] Phone number not used, [x] Rate limit'
        rows=telephone_output.view(dict(job,tool='ignorant',output=noisy))['accounts']
        self.assertEqual(len(rows),3)
        self.assertEqual(rows[2]['status'],'Rate limited — not checked')
        self.assertTrue(addons.observed_rate_limit(noisy))
        self.assertFalse(addons.observed_rate_limit(noisy.replace('[x] snapchat.com','[-] snapchat.com')))

    def test_credentials_are_masked_persistent_csrf_protected_and_removable(self):
        token=credentials.SIGNER.dumps('phoneinfoga')
        route='/tools/phoneinfoga/credentials'
        self.assertEqual(self.client.post(route,data={'NUMVERIFY_API_KEY':'test-private-key'}).status_code,400)
        self.assertEqual(self.client.post(route,data=dict(csrf=token,NUMVERIFY_API_KEY='test-private-key'),headers={'Origin':'https://other.example'}).status_code,403)
        response=self.client.post(route,data=dict(csrf=token,NUMVERIFY_API_KEY='test-private-key',GOOGLECSE_CX='engine-fixture'))
        self.assertEqual(response.status_code,200,response.data)
        self.assertNotIn(b'test-private-key',response.data)
        self.assertEqual(credentials.values('phoneinfoga')['NUMVERIFY_API_KEY'],'test-private-key')
        self.assertEqual(credentials.PATH.stat().st_mode&0o777,0o600)
        self.assertEqual(credentials.PATH.parent.stat().st_mode&0o777,0o700)
        page=self.client.get('/tools')
        self.assertEqual(page.status_code,200,page.data)
        self.assertIn(b'API Information',page.data)
        self.assertNotIn(b'test-private-key',page.data)
        self.assertNotIn(b'engine-fixture',page.data)
        self.client.post(route,data=dict(csrf=token,NUMVERIFY_API_KEY=''))
        self.assertEqual(credentials.values('phoneinfoga')['NUMVERIFY_API_KEY'],'test-private-key')
        with patch.dict('os.environ',{'NUMVERIFY_API_KEY':''}):
            self.client.post(route,data=dict(csrf=token,remove_NUMVERIFY_API_KEY='on'))
            self.assertEqual(credentials.values('phoneinfoga')['NUMVERIFY_API_KEY'],'')
        self.assertEqual(credentials.values('phoneinfoga')['GOOGLECSE_CX'],'engine-fixture')

    def test_runtime_injects_only_matching_keys_redacts_logs_and_normalizes_number(self):
        credentials.save('phoneinfoga',{'NUMVERIFY_API_KEY':'private-fixture-key'})
        credentials.save('toutatis',{'INSTAGRAM_SESSION_ID':'private-fixture-session'})
        phone_env=credentials.environment('phoneinfoga',{'PATH':'/bin','INSTAGRAM_SESSION_ID':'other-session'})
        self.assertEqual(phone_env['NUMVERIFY_API_KEY'],'private-fixture-key')
        self.assertNotIn('INSTAGRAM_SESSION_ID',phone_env)
        self.assertNotIn('NUMVERIFY_API_KEY',credentials.environment('ignorant',phone_env))
        args=addons.command('phoneinfoga','2025550147','phone','1')
        self.assertEqual(args[-1],'+12025550147')
        self.assertEqual(addons.command('clank','2025550147','phone','1')[-1],'+12025550147')
        key='b'*32;job=dict(id=key,tool='phoneinfoga',target='+12025550147',kind='phone',timestamp=store.now(),created=0,status='queued',output='')
        proc=MagicMock(returncode=0);proc.poll.return_value=0
        def launch(*args,**kwargs):
            self.assertEqual(kwargs['env']['NUMVERIFY_API_KEY'],'private-fixture-key')
            kwargs['stdout'].write(b'Provider echoed private-fixture-key and private-fixture-session')
            return proc
        with patch.dict(addons.JOBS,{key:job},clear=True),patch.object(addons.subprocess,'Popen',side_effect=launch):
            addons.execute(key,args)
        saved=store.get(key)
        self.assertEqual(saved['status'],'completed')
        self.assertNotIn('private-fixture-key',json.dumps(saved))
        self.assertNotIn('private-fixture-session',json.dumps(saved))
        self.assertIn('[redacted]',saved['output'])

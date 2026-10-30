"""Three grouped checks: installed startups, all-tool presentation, active credential modes."""
import json
import os
import subprocess
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest import TestCase, skipUnless
from unittest.mock import patch

from bs4 import BeautifulSoup

import addon_tools as addons
import tests.test_case_research as fixtures
import tool_credentials as credentials
import workspace_store as store

SAMPLES={
 'sherlock':'[*] Checking fixture\n[+] Example: https://example.org/fictional_user\n',
 'maigret':'[+] Example: https://example.org/fictional_user\nSearch completed\n',
 'naminter':'Example: https://example.org/fictional_user\n',
 'social-analyzer':json.dumps({'detected':[{'site':'Example','url':'https://example.org/u/fictional_user','status':'reported'}]}),
 'aliens_eye':json.dumps({'results':[{'platform':'Example','url':'https://example.org/u/fictional_user','found':True}]}),
 'toutatis':'Username : fictional_user\nFull Name : Morgan Example\nNumber of followers : 10\nBiography : Fictional fixture\n',
 'socialscan':json.dumps({'fictional_user':[{'platform':'Example','available':True,'valid':True,'success':True,'message':'Available'}]}),
 'blackbird':'[+] Example: https://example.org/fictional_user\n',
 'holehe':'[+] example.org\n[-] other.example\n[x] limited.example\n',
 'phoneinfoga':'Results for local\nE164: +12025550147\nCountry: US\nResults for googlesearch\nSocial media:\n URL: https://www.google.com/search?q=site%3Aexample.org\n',
 'ignorant':'[+] example.org\n[-] other.example\n[x] limited.example\n',
 'clank':json.dumps({'e164':'+12025550147','valid':True,'geo':'Numbering region','operators_in_country':['Example operator']}),
}

for tool in addons.GITHUB_TOOLS:
    SAMPLES[tool] = json.dumps(dict(menace_github_tool=tool, records=[
        dict(label="Fictional lead", value="fixture.example", source_url="https://example.org")
    ]))


class ToolThemeAuditTests(TestCase):
    def setUp(self):
        fixtures.ResearchTests.setUp(self)
        p=patch.object(credentials,'PATH',self.root/'private'/'credentials.json');p.start();self.addCleanup(p.stop)

    @skipUnless(all(Path(addons.startup_command(tool)[0]).is_file() for tool in addons.TOOLS),
                "Requires the complete installed addon runtime (Docker)")
    def test_1_all_installed_tools_start_offline_and_local_phone_metadata_runs(self):
        def startup(tool):
            args=addons.startup_command(tool)
            with tempfile.TemporaryDirectory() as work:
                try:
                    result=subprocess.run(args,cwd=work,capture_output=True,timeout=30,env={'PATH':os.environ['PATH'],'HOME':work,'NO_COLOR':'1','TERM':'dumb'})
                    return tool,dict(startup_check='passed' if result.returncode==0 else 'failed',checked_at=store.now(),diagnostic='' if result.returncode==0 else result.stderr.decode(errors='replace')[-1500:])
                except (OSError,subprocess.TimeoutExpired) as error:return tool,dict(startup_check='failed',checked_at=store.now(),diagnostic=type(error).__name__)
        with ThreadPoolExecutor(max_workers=4) as pool:results=dict(pool.map(startup,addons.TOOLS))
        if Path('/audit-output').is_dir():Path('/audit-output/tool-startup-audit.json').write_text(json.dumps(results,indent=2))
        self.assertEqual({key:value for key,value in results.items() if value['startup_check']!='passed'},{})
        with tempfile.TemporaryDirectory() as work:
            result=subprocess.run([str(addons.executable('clank')),'--json','--local','+12025550147'],cwd=work,capture_output=True,timeout=20)
        self.assertEqual(result.returncode,0)
        self.assertTrue(result.stdout)

    def test_2_each_tool_renders_with_theme_and_collapsed_raw_logs(self):
        self.assertEqual(set(SAMPLES),set(addons.TOOLS))
        for index,(tool,output) in enumerate(SAMPLES.items()):
            key=f'{index+1:032x}'
            store.put(key,'addon',dict(id=key,tool=tool,target='fictional fixture',kind=addons.TOOLS[tool][2].split(',')[0],timestamp=store.now(),created=0,status='completed',output=output))
            response=self.client.get('/history/'+key)
            self.assertEqual(response.status_code,200,(tool,response.data[:500]))
            soup=BeautifulSoup(response.data,'html.parser')
            presentation=soup.select_one('.addon-readable-presentation')
            self.assertIsNotNone(presentation,tool)
            raw_label='Original tool output and diagnostics' if tool in addons.GITHUB_TOOLS else 'Raw tool output'
            summary=next((node for node in presentation.select('details > summary') if node.get_text(strip=True)==raw_label),None)
            self.assertIsNotNone(summary,tool)
            self.assertNotIn('open',summary.parent.attrs,tool)
            self.assertTrue(presentation.select('.output-facts,.phone-account-table,.addon-link-grid,.structured-finding,.output-group'),tool)
            self.assertIn(b'styles.css',response.data)
        self.assertEqual(self.client.get('/addons').status_code,200)

    def test_3_credentials_cover_enabled_modes_and_machine_output_keeps_availability(self):
        self.assertEqual(set(credentials.SCHEMA),{'phoneinfoga','toutatis','blackbird'})
        fields={tool:{field['key'] for field in credentials.fields(tool)} for tool in credentials.SCHEMA}
        self.assertEqual(fields['phoneinfoga'],{'NUMVERIFY_API_KEY','GOOGLE_API_KEY','GOOGLECSE_CX'})
        self.assertEqual(fields['toutatis'],{'INSTAGRAM_SESSION_ID'})
        for tool in addons.TOOLS:
            for field in credentials.fields(tool):self.assertTrue(field['url'].startswith('https://'))
        self.assertIn('--json',addons.command('socialscan','fictional_user','username'))
        self.assertIn('--local',addons.command('clank','+12025550147','phone'))
        self.assertNotIn('--ai',addons.command('maigret','fictional_user','username'))
        self.assertEqual(self.client.get('/tools').status_code,200)
        self.assertIn(b'API Information',self.client.get('/tools').data)
        self.assertIn(b'Optional upstream AI features are not enabled',self.client.get('/tools').data)

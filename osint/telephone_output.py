"""Readable summaries for pinned telephone addons; keep original logs separate."""
import re
from urllib.parse import parse_qs, urlsplit


def view(job):
    tool=job.get('tool');text=job.get('output','')
    if tool not in ('phoneinfoga','ignorant'):return None
    result=dict(accounts=[],providers=[],facts=[],groups=[],notes=[])
    if tool=='ignorant':
        states={'+':'Reported registered','-':'Not reported registered','x':'Rate limited — not checked'}
        rows={}
        for line in text.splitlines():
            match=re.fullmatch(r'\s*\[([+\-x])\]\s*([a-zA-Z0-9.-]+)\s*',line)
            if match:rows[match[2]]=dict(platform=match[2],status=states[match[1]],state=match[1])
        result['accounts']=list(rows.values())
        result['notes']=['These are unverified registration signals, not identified profiles or proof of account ownership. A negative response is not proof that no account exists.']
    else:
        group='Search shortcuts';provider='';groups={};seen=set()
        names={'googlecse':'Google Custom Search','numverify':'Numverify','ovh':'OVH','googlesearch':'Google search shortcuts','local':'Local metadata'}
        for line in text.splitlines():
            stripped=line.strip()
            if re.search(r'\blevel=(debug|info|warning|error)\b',stripped):
                skipped=re.search(r'reason="([^"]+)"\s+scanner=([\w-]+)',stripped)
                if skipped:
                    reason,scanner=skipped.groups();missing='key' in reason.lower() or 'engine id' in reason.lower()
                    result['providers'].append(dict(name=names.get(scanner,scanner),status='Not configured' if missing else 'Not available',message='Add provider credentials under Tools.' if missing else reason,needs_credentials=missing))
                continue
            match=re.fullmatch(r'Results for ([\w-]+)',stripped)
            if match:
                provider=match[1];group=names.get(provider,provider)
                result['providers'].append(dict(name=names.get(provider,provider),status='Output returned',message='Unverified provider output.',needs_credentials=False));continue
            if stripped.endswith(':') and not stripped.startswith('URL:'):group=stripped[:-1];continue
            match=re.fullmatch(r'URL:\s*(https?://\S+)',stripped)
            if match:
                url=match[1];parsed=urlsplit(url)
                if not parsed.hostname or parsed.username or parsed.password or url in seen:continue
                seen.add(url);query=parse_qs(parsed.query).get('q',[''])[0]
                site=re.search(r'\bsite:([\w.-]+)',query)
                label=('Search '+site[1]) if site else ('Search the web' if query else parsed.hostname)
                groups.setdefault(group,[]).append(dict(label=label,url=url,query=query[:1500]));continue
            fact=re.fullmatch(r'(Valid|Number|Raw local|Local|E164|International|Country|Local format|International format|Country prefix|Country code|Country name|Location|Carrier|Line type|Results shown|Total number of results|Requests made|Title):\s*(.+)',stripped)
            if fact:result['facts'].append(dict(label=fact[1],value=fact[2]))
        result['groups']=[dict(label=label,links=links) for label,links in groups.items()]
        result['notes']=['Generated search links are shortcuts to run a search, not confirmed matches. Numbering geography is not a live location and does not identify a subscriber.']
    result['has_results']=bool(result['accounts'] or result['facts'] or result['groups'])
    return result


def section(job,summary):
    import addon_tools
    findings=[];source=addon_tools.TOOLS[job['tool']][1]
    for row in summary['accounts']:
        findings.append(dict(label=row['platform'],value=dict(reported_status=row['status'],unverified=True),source=source,verification_status='Unverified',collected_at=job['timestamp']))
    for fact in summary['facts']:
        findings.append(dict(label=fact['label'],value=fact['value'],source=source,verification_status='Unverified',collected_at=job['timestamp']))
    links=[dict(label=link['label']+' (search shortcut)',value=link['url'],source=source) for group in summary['groups'] for link in group['links']]
    if not findings:findings=[dict(label='Provider coverage',value=dict(providers=summary['providers'],search_shortcuts=len(links)),source=source,include_in_report=False)]
    return dict(name=addon_tools.TOOLS[job['tool']][0]+': '+job['target'],module_type='addon:'+job['tool'],module=dict(name=source,mode='analyst selected'),findings=findings,links=links,notes=summary['notes']+['Execution status: '+job['status']])

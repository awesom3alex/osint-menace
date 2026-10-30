"""Consistent themed presentation for addon text/JSON, with original logs retained."""
import re
from urllib.parse import urlsplit

from readable_results import structured_value


def view(job):
    import addon_tools
    from research_hub import safe_url
    text=job.get('output','')
    parsed=structured_value(text)
    result=dict(structured=parsed['structured'],value=parsed['value'],facts=[],signals=[],links=[],messages=[])
    if parsed['structured']:return result
    seen=set();signals={}
    for raw in text.splitlines():
        line=addon_tools.ANSI.sub('',raw).strip()
        if not line or re.search(r'\d+%\||\bit/s\b|\blevel=(debug|info)\b',line):continue
        # Upstream credits, installation notices and donation links are not investigation findings.
        if re.search(r'donat|buy.?me.?a.?coffee|github\.com/(?:sherlock-project/sherlock|soxoj/maigret|megadose/(?:holehe|toutatis)|3xp0rt/naminter|iojw/socialscan)|^Twitter\s*:',line,re.I):continue
        signal=re.fullmatch(r'\[([+\-x])\]\s*([\w.-]+)',line)
        if signal:
            signals[signal[2]]=dict(platform=signal[2],status={'+':'Reported registered','-':'Not reported registered','x':'Rate limited — not checked'}[signal[1]]);continue
        availability=re.fullmatch(r'([\w .@+-]{1,150}):\s*(Available|Taken|Reserved|Taken/Reserved|Invalid|Error)(?:\s*[-–:]\s*(.{0,300}))?',line,re.I)
        if availability:
            signals[availability[1]]=dict(platform=availability[1],status=availability[2]);continue
        urls=re.findall(r'https?://[^\s<>"\]\}]+',line)
        for candidate in urls:
            url=safe_url(candidate.rstrip('.,)'))
            if not url or url in seen:continue
            if urlsplit(url).hostname in ('pypi.org',):continue
            seen.add(url)
            label=re.sub(r'^\[[^\]]+\]\s*','',line.split(candidate)[0]).strip(' :|│')
            result['links'].append(dict(label=label[:160] or urlsplit(url).hostname,url=url,status='Reported match' if line.startswith('[+]') else 'Reported link'))
        if urls:continue
        fact=re.fullmatch(r'([A-Za-z][A-Za-z 0-9_()/.-]{1,65})\s*:\s*(.{1,1500})',line)
        if fact and not re.search(r'error|warning|completed|scanning|checking|version|author',fact[1],re.I):
            result['facts'].append(dict(label=fact[1].strip(),value=fact[2]));continue
        if re.search(r'error|failed|rate.limit|blocked|not.configured|no (?:result|match)|not found',line,re.I):
            result['messages'].append(line[:500])
    result['signals']=list(signals.values())[:200]
    result['facts']=result['facts'][:100];result['links']=result['links'][:250]
    result['messages']=list(dict.fromkeys(result['messages']))[:10]
    return result

"""Installation-local credentials; never return saved values to the browser."""
import json
import os
import secrets
import tempfile
import threading
from urllib.parse import quote, quote_plus

from itsdangerous import URLSafeTimedSerializer

from paths import DATA_ROOT

PATH=DATA_ROOT / "private/tool-credentials.json"
LOCK=threading.RLock()
SIGNER=URLSafeTimedSerializer(secrets.token_hex(32),salt='tool-credentials')
SCHEMA={
 'phoneinfoga':[
  dict(key='NUMVERIFY_API_KEY',label='Numverify / APILayer API key',url='https://apilayer.com/marketplace/number_verification-api',note='Optional number-verification provider. Provider plans and quotas apply.'),
  dict(key='GOOGLE_API_KEY',label='Google Custom Search API key',url='https://developers.google.com/custom-search/v1/overview',note='Optional legacy scanner. Google Custom Search JSON API is closed to new customers; existing customers must transition by January 1, 2027.'),
  dict(key='GOOGLECSE_CX',label='Google search engine ID (CX)',url='https://programmablesearchengine.google.com/controlpanel/all',note='Required together with the Google Custom Search key. This is a search engine ID, not a Firebase measurement ID.')],
 'toutatis':[dict(key='INSTAGRAM_SESSION_ID',label='Instagram session ID',url='https://github.com/megadose/toutatis#usage',note='Required authenticated Instagram session. Treat it as a password; use only an account you are authorized to use.')],
 'blackbird':[dict(key='INSTAGRAM_SESSION_ID',label='Instagram session ID',url='https://github.com/p1ngul1n0/blackbird#readme',note='Optional Instagram enrichment session; other public searches work without it.')],
}


def load():
    with LOCK:
        if not PATH.exists():return {}
        return json.loads(PATH.read_text())


def values(tool):
    stored=load().get(tool,{})
    return {field['key']:stored.get(field['key']) or os.environ.get(field['key'],'') for field in SCHEMA.get(tool,[])}


def fields(tool):
    stored=load().get(tool,{})
    return [dict(field,configured=bool(stored.get(field['key']) or os.environ.get(field['key'])),local=bool(stored.get(field['key']))) for field in SCHEMA.get(tool,[])]


def save(tool,form):
    if tool not in SCHEMA:raise ValueError('This tool has no credential fields in its current mode.')
    allowed={field['key'] for field in SCHEMA[tool]}
    if set(form)-allowed-{'csrf'}-{'remove_'+key for key in allowed}:raise ValueError('Unsupported credential field.')
    with LOCK:
        data=load();current=data.setdefault(tool,{})
        for key in allowed:
            value=form.get(key,'')
            if not isinstance(value,str) or len(value)>4000 or any(ord(char)<32 for char in value):raise ValueError('Credential values must be single-line text of at most 4,000 characters.')
            if form.get('remove_'+key):current.pop(key,None)
            elif value.strip():current[key]=value.strip()
        PATH.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
        os.chmod(PATH.parent,0o700)
        handle,name=tempfile.mkstemp(prefix='.credentials-',dir=PATH.parent)
        try:
            with os.fdopen(handle,'w') as out:
                os.fchmod(out.fileno(),0o600);json.dump(data,out);out.flush();os.fsync(out.fileno())
            os.replace(name,PATH)
        finally:
            if os.path.exists(name):os.unlink(name)


def redact(text,extra=()):
    secrets_set=set(extra)
    for tool in SCHEMA:secrets_set.update(values(tool).values())
    for value in sorted(filter(None,secrets_set),key=len,reverse=True):
        for variant in {value,quote(value,safe=''),quote_plus(value)}:text=text.replace(variant,'[redacted]')
    return text


def environment(tool,base=None):
    env=dict(os.environ if base is None else base)
    for field in {field['key'] for fields_ in SCHEMA.values() for field in fields_}:env.pop(field,None)
    env.update({key:value for key,value in values(tool).items() if value})
    return env

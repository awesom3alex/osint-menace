"""Previewed global searches and reviewed address/profile enrichment."""
import copy
import csv
import hashlib
import io
import json
import math
import os
import re
import secrets
import subprocess
import sys
import threading
import time
import uuid
from pathlib import Path
from urllib.parse import urlencode, urlsplit, urlunsplit

import phonenumbers
from flask import Blueprint, abort, jsonify, redirect, render_template, request, send_file, url_for
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from werkzeug.exceptions import HTTPException

import workspace_store as store

bp = Blueprint('research_hub', __name__)


@bp.errorhandler(HTTPException)
def api_error(error):
    if request.path.startswith('/api/') or request.accept_mimetypes.best=='application/json':
        return jsonify(error=error.description), error.code
    return error
SIGNER = URLSafeTimedSerializer(secrets.token_hex(32), salt='global-search-preview')
CAPACITY = threading.BoundedSemaphore(2)
GEOCODER_LOCK = threading.Lock()
LAST_GEOCODE = 0.0
MODES = ('web', 'news', 'phone', 'address', 'social')
REGIONS = {'wt-wt':'Worldwide', 'us-en':'United States / English', 'uk-en':'United Kingdom / English', 'ca-en':'Canada / English', 'au-en':'Australia / English', 'de-de':'Germany / German', 'fr-fr':'France / French', 'es-es':'Spain / Spanish', 'in-en':'India / English'}
BACKENDS = {'web':('duckduckgo','brave','mojeek','yahoo'), 'news':('duckduckgo','bing','yahoo')}
DEFAULTS = dict(q='', mode='web', region='us-en', phone_region='US', backend='duckduckgo', safesearch='moderate', period='', sites='', exact=False, variants=True, limit=20, case_id='')


def safe_url(value):
    if not isinstance(value, str) or len(value)>4096 or any(ord(c)<32 for c in value):
        return ''
    try:
        parsed=urlsplit(value)
        if parsed.scheme not in ('http','https') or not parsed.hostname or parsed.username or parsed.password:
            return ''
        return urlunsplit((parsed.scheme.lower(),parsed.netloc.lower(),parsed.path or '/',parsed.query,''))
    except ValueError:
        return ''


def context_case(case_id):
    if not isinstance(case_id,str) or len(case_id)>40:
        raise ValueError('Choose a valid case.')
    if case_id:
        import app
        case=app.load_case(case_id)
        if case.get('is_demo'):
            abort(403,'The demo cannot receive searches or findings.')
    return case_id


def search_plan(data):
    if not isinstance(data,dict):
        raise ValueError('Send search settings.')
    config={key:data.get(key,value) for key,value in DEFAULTS.items()}
    if any(not isinstance(config[key],str) for key in ('q','mode','region','phone_region','backend','safesearch','period','sites','case_id')):
        raise ValueError('Search settings must be text.')
    config['q']=config['q'].strip()
    if not 1<=len(config['q'])<=500 or any(ord(c)<32 for c in config['q']):
        raise ValueError('Enter a query of 1–500 characters without line breaks.')
    if config['mode'] not in MODES or config['region'] not in REGIONS or config['safesearch'] not in ('on','moderate','off'):
        raise ValueError('Choose a supported mode, region/language, and SafeSearch setting.')
    category='news' if config['mode']=='news' else 'web'
    if config['backend'] not in BACKENDS[category]:
        raise ValueError('Choose an engine supported for this search mode.')
    if config['period'] not in ('','d','w','m','y') or (category=='news' and config['period']=='y'):
        raise ValueError('News supports day, week, month, or any time; web also supports year.')
    try:
        limit=int(config['limit'])
    except (ValueError,TypeError):
        raise ValueError('Choose a result limit.') from None
    if limit not in (10,20,30) or type(config['exact']) is not bool or type(config['variants']) is not bool:
        raise ValueError('Invalid query options or result limit.')
    config['limit']=limit
    context_case(config['case_id'])
    domains=[]
    for domain in config['sites'].split(','):
        domain=domain.strip().lower()
        if not domain:
            continue
        if not re.fullmatch(r'(?:[a-z0-9](?:[a-z0-9-]*[a-z0-9])?\.)+[a-z]{2,63}',domain) or len(domain)>253:
            raise ValueError('Enter website domains separated by commas, without URLs or paths.')
        if domain not in domains:domains.append(domain)
    if len(domains)>5:
        raise ValueError('Use up to five website domains.')
    if config['mode']=='social' and not domains:
        domains=['facebook.com','instagram.com','linkedin.com','reddit.com','x.com']
    query=config['q']
    terms=[query]
    if config['mode']=='phone':
        if config['phone_region'] not in phonenumbers.SUPPORTED_REGIONS:
            raise ValueError('Use a supported phone region such as US or GB.')
        try:
            number=phonenumbers.parse(query,config['phone_region'])
            if not phonenumbers.is_possible_number(number):raise ValueError('Number length is not plausible.')
            if config['variants']:
                terms=list(dict.fromkeys([phonenumbers.format_number(number,style) for style in (phonenumbers.PhoneNumberFormat.E164,phonenumbers.PhoneNumberFormat.NATIONAL,phonenumbers.PhoneNumberFormat.INTERNATIONAL)]))[:3]
        except phonenumbers.NumberParseException:
            raise ValueError('Enter a plausible telephone number with its country code or region.') from None
    queries=[]
    for term in terms:
        if config['exact'] or config['mode']=='phone':term='"'+term.replace('"','')+'"'
        if domains:term+=' ('+' OR '.join('site:'+domain for domain in domains)+')'
        queries.append(term)
    return dict(config=config,queries=queries,category=category,domains=domains)


def records_of_type(kind,limit=20):
    with store.connect() as db:
        return [json.loads(row[0]) for row in db.execute('SELECT payload FROM records WHERE type=? ORDER BY created DESC LIMIT ?', (kind,limit))]


@bp.get('/global-search')
def global_search():
    import app
    config=dict(DEFAULTS)
    bookmark=request.args.get('bookmark','')
    if bookmark:
        item=store.get(bookmark)
        if not item or item.get('record_type')!='saved_query':abort(404)
        config.update(item['config'])
    for key in ('q','mode','case_id'):
        if key in request.args:config[key]=request.args[key][:500]
    if config['mode'] not in MODES:config['mode']='web'
    return render_template('global_search.html', config=config, cases=app.list_cases(), regions=REGIONS, modes=MODES,
                           bookmarks=records_of_type('saved_query'), recent=records_of_type('global_search',10))


@bp.post('/api/global-search/preview')
def preview():
    try:
        plan=search_plan(request.get_json(silent=True))
        return jsonify(plan=plan,token=SIGNER.dumps(plan))
    except ValueError as exc:
        return jsonify(error=str(exc)),400


def confirmed_plan():
    payload=request.get_json(silent=True)
    if not isinstance(payload,dict):raise ValueError('Preview the queries first.')
    try:
        plan=SIGNER.loads(payload.get('token',''),max_age=900)
    except (BadSignature,SignatureExpired,TypeError):
        raise ValueError('The query preview expired. Preview it again.') from None
    if search_plan(plan['config'])!=plan:
        raise ValueError('Search settings changed. Preview them again.')
    return plan


def finding(label,value,source,url='',method=''):
    return dict(label=str(label)[:1000],value=value,source=source,source_url=safe_url(url),collected_at=store.now(),
                collection_method=method,verification_status='Unverified',include_in_report=True)


def section_for(entry,record_id):
    f=copy.deepcopy(entry['finding'])
    f['research_source']=dict(record_id=record_id,entry_id=entry['id'])
    return dict(name=f['label'],module=dict(name=f['source'],mode=entry.get('mode','passive')),findings=[f],links=[],notes=entry.get('notes',[]))


def finish(record,entries,errors=()):
    record['entries']=entries
    record['errors']=list(errors)
    record['status']='partial' if entries and errors else 'failed' if errors else 'completed' if entries else 'empty'
    record['finished_at']=store.now()
    record['results']=[section_for(entry,record['id']) for entry in entries]
    store.put(record['id'],record['record_type'],record)
    return record


def run_ddgs(plan):
    from ddgs import DDGS
    from ddgs.ddgs import ENGINES
    config=plan['config']
    category='news' if plan['category']=='news' else 'text'
    if config['backend'] not in ENGINES[category]:
        raise ValueError('This engine is unavailable in the installed DDGS version. Choose another engine.')
    client=DDGS(timeout=10)
    entries=[];by_url={};errors=[];ledger=[]
    per_query=max(5,math.ceil(config['limit']/len(plan['queries'])))
    for query in plan['queries']:
        if len(entries)>=config['limit']:
            ledger.append(dict(query=query,status='not run — result limit reached'));continue
        try:
            rows=getattr(client,'news' if category=='news' else 'text')(query,region=config['region'],safesearch=config['safesearch'],timelimit=config['period'] or None,max_results=per_query,backend=config['backend'])
            ledger.append(dict(query=query,status='completed'))
            for row in rows:
                url=safe_url(row.get('url') or row.get('href',''))
                if not url:continue
                host=urlsplit(url).hostname
                if plan['domains'] and not any(host==domain or host.endswith('.'+domain) for domain in plan['domains']):continue
                if url in by_url:
                    by_url[url]['queries'].append(query);continue
                if len(entries)>=config['limit']:break
                snippet=str(row.get('body') or row.get('description') or row.get('excerpt') or '')[:12000]
                value=dict(title=str(row.get('title') or url)[:1000],snippet=snippet,url=url,published=str(row.get('date',''))[:1000],publisher=str(row.get('source',''))[:1000])
                entry=dict(id=hashlib.sha256(url.encode()).hexdigest()[:32],domain=urlsplit(url).hostname,queries=[query],
                           finding=finding(value['title'],value,'DDGS / '+config['backend'],url,'Search-engine result and snippet; not a captured source page.'))
                entries.append(entry);by_url[url]=entry
        except Exception as exc:
            errors.append('A query could not complete: '+type(exc).__name__+'. The engine may be rate-limited or unavailable.')
            ledger.append(dict(query=query,status='failed'))
    for entry in entries:
        entry['finding']['value']['matched_queries']=entry['queries']
    return entries,errors,ledger


@bp.post('/api/global-search/run')
def run_search():
    try:plan=confirmed_plan()
    except ValueError as exc:return jsonify(error=str(exc)),400
    if not CAPACITY.acquire(blocking=False):return jsonify(error='Two research requests are running. Try again shortly.'),429
    key=uuid.uuid4().hex
    record=dict(id=key,record_type='global_search',collector='ddgs',target=plan['config']['q'],kind='global:'+plan['config']['mode'],
                timestamp=store.now(),status='running',plan=plan,context_case_id=plan['config']['case_id'],results=[])
    try:
        store.put(key,'global_search',record)
        entries,errors,ledger=run_ddgs(plan)
        record['queries_executed']=ledger
        finish(record,entries,errors)
    except Exception as exc:
        finish(record,[],['Search could not complete: '+type(exc).__name__+'.'])
    finally:CAPACITY.release()
    return jsonify(url=url_for('research_hub.result',record_id=key))


@bp.post('/api/global-search/bookmarks')
def bookmark():
    try:plan=confirmed_plan()
    except ValueError as exc:return jsonify(error=str(exc)),400
    key=hashlib.sha256(json.dumps(plan['config'],sort_keys=True).encode()).hexdigest()[:32]
    store.put(key,'saved_query',dict(id=key,record_type='saved_query',target=plan['config']['q'],timestamp=store.now(),config=plan['config']))
    return jsonify(url=url_for('research_hub.global_search',bookmark=key))


@bp.post('/global-search/bookmarks/<key>/delete')
def delete_bookmark(key):
    with store.connect() as db:db.execute("DELETE FROM records WHERE id=? AND type='saved_query'",(key,))
    return redirect(url_for('research_hub.global_search'))


def geocoder_settings():
    value=(os.environ.get('MENACE_GEOCODER_URL') or 'https://nominatim.openstreetmap.org').rstrip('/')
    parsed=urlsplit(value)
    if parsed.scheme not in ('http','https') or not parsed.netloc or parsed.path or parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError('Administrator must configure MENACE_GEOCODER_URL as a geocoder origin without credentials or a path.')
    public=parsed.hostname=='nominatim.openstreetmap.org'
    if public and parsed.scheme!='https':raise ValueError('The public geocoder requires HTTPS.')
    return dict(url=value,domain=parsed.netloc,scheme=parsed.scheme,public=public)


@bp.get('/research-tools')
def tools():
    import app
    try:geocoder=geocoder_settings()
    except ValueError:geocoder=dict(url='Not configured correctly',public=True)
    return render_template('research_tools.html',cases=app.list_cases(),case_id=request.args.get('case_id','')[:40],geocoder=geocoder,selected_tool=request.args.get('tool','address_breakdown'),prefill=request.args.get('original','')[:2000])


def breakdown(original):
    import usaddress
    tokens=usaddress.parse(original)
    try:
        components,kind=usaddress.tag(original)
        warning='Parsing does not verify address validity, deliverability, ownership, or residency.'
    except usaddress.RepeatedLabelError:
        components={};kind='Ambiguous';warning='Repeated address labels: review token labels manually. No normalization or validity check was performed.'
    value=dict(original=original,address_type=kind,components=dict(components),tokens=[dict(text=text,label=label) for text,label in tokens],limitations=warning)
    return [dict(id=uuid.uuid4().hex,mode='local',finding=finding('Address breakdown',value,'usaddress 0.5.16',method='Local U.S. address parsing; original input retained.'))]


def address_location(original,data):
    from geopy.geocoders import Nominatim
    global LAST_GEOCODE
    settings=geocoder_settings()
    if settings['public'] and data.get('public_location') is not True:
        raise ValueError('The public geocoder accepts public places only. Confirm that no personal/confidential address is being submitted, or configure a self-hosted geocoder.')
    language=data.get('language','en')
    if language not in ('en','es','fr','de'):raise ValueError('Choose a supported output language.')
    country=data.get('country','')
    if not isinstance(country,str):raise ValueError('Country filter must be a two-letter code.')
    country=country.lower()
    if country and not re.fullmatch('[a-z]{2}',country):raise ValueError('Country filter must be a two-letter code.')
    geocoder=Nominatim(domain=settings['domain'],scheme=settings['scheme'],user_agent='OSINT-Menace/0.4-development',timeout=10)
    with GEOCODER_LOCK:
        delay=1.1-(time.monotonic()-LAST_GEOCODE)
        if delay>0:time.sleep(delay)
        try:
            if data.get('coordinates'):
                parts=original.split(',')
                if len(parts)!=2:raise ValueError('Enter latitude, longitude.')
                lat,lon=map(float,parts)
                if not math.isfinite(lat) or not math.isfinite(lon) or not -90<=lat<=90 or not -180<=lon<=180:raise ValueError('Coordinates are outside valid ranges.')
                locations=geocoder.reverse((lat,lon),exactly_one=False,language=language,addressdetails=True)
            else:
                locations=geocoder.geocode(original,exactly_one=False,limit=5,addressdetails=True,language=language,country_codes=country or None)
        finally:LAST_GEOCODE=time.monotonic()
    entries=[]
    for candidate in (locations or [])[:5]:
        raw=candidate.raw
        lat,lon=float(candidate.latitude),float(candidate.longitude)
        if not math.isfinite(lat) or not math.isfinite(lon) or not -90<=lat<=90 or not -180<=lon<=180:continue
        osm_type,osm_id=raw.get('osm_type'),str(raw.get('osm_id',''))
        source='https://www.openstreetmap.org/'+osm_type+'/'+osm_id if osm_type in ('node','way','relation') and osm_id.isdigit() else settings['url']
        value=dict(original=original,formatted_address=candidate.address,latitude=lat,longitude=lon,bounding_box=raw.get('boundingbox',[]),
                   address_components=raw.get('address',{}),provider=settings['url'],attribution=raw.get('licence','© OpenStreetMap contributors, ODbL'),
                   map_url='https://www.openstreetmap.org/?'+urlencode(dict(mlat=lat,mlon=lon))+'#map=17/'+str(lat)+'/'+str(lon),
                   limitations='Candidate location only; this does not establish residency, ownership, or an exact entrance.')
        entries.append(dict(id=uuid.uuid4().hex,finding=finding('Address location candidate: '+str(candidate.address)[:200],value,'Nominatim via geopy',source,'User-requested geocoding candidate; provider attribution retained.')))
    return entries


def profile_details(original):
    from collectors import fetch
    url=safe_url(original)
    if not url:raise ValueError('Enter a public HTTP(S) profile URL without credentials.')
    response=fetch(url,timeout=10,headers={'Accept':'text/html,application/json'},max_bytes=1_000_000)
    if response['status']!='found':raise ValueError('Profile was unavailable, blocked, rate-limited, or not a permitted public destination. No login or bypass was attempted.')
    content_type=response.get('headers',{}).get('content-type','text/html').split(';')[0].lower()
    if content_type not in ('text/html','application/xhtml+xml','application/json','text/plain'):
        raise ValueError('Profile details require an HTML, JSON, or plain-text response.')
    if response.get('headers',{}).get('content-encoding','identity')!='identity':raise ValueError('The profile returned an unsupported compressed response.')
    worker=Path(__file__).parent/'scripts/profile_extract.py'
    try:
        result=subprocess.run([sys.executable,str(worker)],input=response['body'],capture_output=True,timeout=12,
                              env={'PATH':os.environ.get('PATH',''),'PYTHONIOENCODING':'utf-8','PYTHONDONTWRITEBYTECODE':'1'})
    except subprocess.TimeoutExpired:
        raise ValueError('Profile parsing exceeded its time limit.') from None
    if result.returncode or len(result.stdout)>1_000_000:raise ValueError('This page could not be parsed by the installed extractor.')
    fields=json.loads(result.stdout)
    if not isinstance(fields,dict) or not fields:raise ValueError('No supported public profile fields were found. The page may require login, scripts, or a different extractor.')
    fields={str(key)[:100]:value if isinstance(value,(int,float,bool)) and not (isinstance(value,float) and not math.isfinite(value)) else str(value)[:10000] for key,value in list(fields.items())[:80]}
    value=dict(original=original,fetched_url=response['url'],page_sha256=hashlib.sha256(response['body']).hexdigest(),fields=fields,
               limitations='Reported public profile fields are unverified. No inferred email addresses or ownership associations are added.')
    return [dict(id=uuid.uuid4().hex,finding=finding('Public social profile details',value,'socid-extractor 0.1.1',response['url'],'Protected public-page fetch and local parser; no login, AI fallback, or secondary network requests.'))]


@bp.post('/api/research-tools/run')
def run_tool():
    data=request.get_json(silent=True)
    if not isinstance(data,dict) or data.get('tool') not in ('address_breakdown','address_location','profile_details','telephone','nearby_places','international_address','archive_history'):
        return jsonify(error='Choose a supported research tool.'),400
    if any(key in data and type(data[key]) is not bool for key in ('coordinates','public_location','nearby_confirm','archive_confirm','phoneinfoga','phone_web')):
        return jsonify(error='Location options must be true or false.'),400
    original=data.get('original','')
    if not isinstance(original,str) or not 1<=len(original)<=2000 or not original.strip():return jsonify(error='Enter an input of 1–2,000 characters.'),400
    try:case_id=context_case(data.get('case_id',''))
    except ValueError as exc:return jsonify(error=str(exc)),400
    if not CAPACITY.acquire(blocking=False):return jsonify(error='Two research requests are running. Try again shortly.'),429
    key=uuid.uuid4().hex;tool=data['tool']
    record=dict(id=key,record_type='research_tool',collector=tool,target=original,kind=tool,timestamp=store.now(),status='running',
                context_case_id=case_id,results=[],settings={k:data.get(k) for k in ('language','country','coordinates','radius','category','phone_region','phoneinfoga','phone_web','phone_engine','archive_from','archive_to')})
    try:
        store.put(key,'research_tool',record)
        from research_extensions import TOOLS
        if tool in TOOLS:
            entries,errors=TOOLS[tool](original,data)
        else:
            entries=breakdown(original) if tool=='address_breakdown' else address_location(original,data) if tool=='address_location' else profile_details(original)
            errors=[]
        finish(record,entries,errors)
    except Exception as exc:
        message=str(exc) if isinstance(exc,ValueError) else 'Tool unavailable or request failed: '+type(exc).__name__+'.'
        finish(record,[],[message[:1000]])
    finally:CAPACITY.release()
    return jsonify(url=url_for('research_hub.result',record_id=key))


def run_record(key):
    item=store.get(key)
    if not item or item.get('record_type') not in ('global_search','research_tool'):abort(404)
    return item


FINDING_TYPES=('Other','Person','Organization','Phone','Email','Username','Address','Domain','URL','Document')


def saved_entries(record_id,case):
    from case_workflow import findings
    return {f['research_source']['entry_id'] for _,_,_,f in findings(case)
            if isinstance(f.get('research_source'),dict) and f['research_source'].get('record_id')==record_id}


@bp.get('/research/results/<record_id>/saved')
def saved_status(record_id):
    import app
    run_record(record_id)
    try:case_id=context_case(request.args.get('case_id',''))
    except ValueError as exc:return jsonify(error=str(exc)),400
    if not case_id:return jsonify(saved_ids=[])
    with app.CASE_LOCK:ids=sorted(saved_entries(record_id,app.load_case(case_id)))
    response=jsonify(saved_ids=ids,case_id=case_id)
    response.headers['Cache-Control']='no-store'
    return response


def reviewed_edits(selected):
    raw=request.form.get('review_edits','{}')
    if len(raw)>1_100_000:abort(400,'Review details exceed the size limit.')
    try:edits=json.loads(raw)
    except (ValueError,TypeError):abort(400,'Review details must be valid JSON.')
    if not isinstance(edits,dict) or not set(edits)<=set(selected):abort(400,'Review only selected results.')
    clean={}
    for key,value in edits.items():
        if not isinstance(value,dict) or set(value)-{'title','notes','tags','type'}:abort(400,'Unsupported review details.')
        title=value.get('title');notes=value.get('notes','');tags=value.get('tags',[]);kind=value.get('type','Other')
        if not isinstance(title,str) or not title.strip() or len(title)>1000:abort(400,'Use a title of 1–1,000 characters.')
        if not isinstance(notes,str) or len(notes)>20000:abort(400,'Notes are limited to 20,000 characters.')
        if not isinstance(kind,str) or kind not in FINDING_TYPES:abort(400,'Choose a supported finding type.')
        if not isinstance(tags,list) or len(tags)>20 or any(not isinstance(tag,str) or not tag.strip() or len(tag)>40 for tag in tags):abort(400,'Use up to 20 tags of 1–40 characters each.')
        unique=[];seen=set()
        for tag in tags:
            tag=tag.strip()
            if tag.casefold() not in seen:unique.append(tag);seen.add(tag.casefold())
        clean[key]=dict(label=title.strip(),analyst_notes=notes,tags=unique,finding_type=kind,reviewed_at=store.now())
    return clean


@bp.get('/research/results/<record_id>')
def result(record_id):
    import app
    item=run_record(record_id)
    domain=request.args.get('domain','')
    entries=item.get('entries',[])
    domains=sorted({entry.get('domain','') for entry in entries if entry.get('domain')})
    filtered=[entry for entry in entries if not domain or entry.get('domain')==domain]
    page=max(1,request.args.get('page',1,type=int) or 1)
    previews={entry['id']:dict(title=entry['finding']['label'],source_url=entry['finding'].get('source_url',''),summary=str(entry['finding'].get('value',''))[:2000]) for entry in filtered[(page-1)*10:page*10]}
    return render_template('research_results.html',item=item,entries=filtered[(page-1)*10:page*10],count=len(filtered),page=page,has_next=len(filtered)>page*10,
                           cases=app.list_cases(),domains=domains,domain=domain,previews=previews,finding_types=FINDING_TYPES)


@bp.post('/research/results/<record_id>/action')
def result_action(record_id):
    import app
    from case_review import save_review_case
    item=run_record(record_id)
    single=request.form.getlist('single_entry')
    if len(single)>1:abort(400,'Choose one result for Add To Case.')
    selected=single or request.form.getlist('selected')
    available={entry['id']:entry for entry in item.get('entries',[])}
    if not selected or len(selected)!=len(set(selected)) or not set(selected)<=set(available):abort(400,'Select current results before continuing.')
    entries=[available[key] for key in selected]
    action='case' if single else request.form.get('action')
    if action in ('json','csv'):
        if action=='json':
            data=json.dumps(dict(original=item['target'],collector=item['collector'],collected=item['timestamp'],plan=item.get('plan'),entries=entries),ensure_ascii=False,indent=2).encode()
        else:
            out=io.StringIO();writer=csv.writer(out);writer.writerow(['Title','Source URL','Collected','Source','Value'])
            def cell(value):
                value=str(value)
                return "'"+value if value.lstrip().startswith(('=','+','-','@')) else value
            for entry in entries:
                f=entry['finding'];writer.writerow([cell(f['label']),cell(f['source_url']),cell(f['collected_at']),cell(f['source']),cell(json.dumps(f['value'],ensure_ascii=False))])
            data=('\ufeff'+out.getvalue()).encode('utf-8')
        return send_file(io.BytesIO(data),mimetype='application/json' if action=='json' else 'text/csv',as_attachment=True,download_name='research-results.'+action)
    if action not in ('case','inbox'):abort(400,'Choose a valid destination.')
    edits=reviewed_edits(selected) if action=='case' else {}
    case_id=context_case(request.form.get('case_id',''))
    if not case_id:abort(400,'Choose a case.')
    with app.CASE_LOCK:
        case=app.load_case(case_id)
        if action=='inbox':
            key=hashlib.sha256((record_id+case_id+':review').encode()).hexdigest()[:32]
            bundle=store.get(key) or dict(id=key,record_type='review_bundle',source_record_id=record_id,collector=item['collector'],kind=item['kind'],target=item['target'],timestamp=store.now(),origin_case_id=case_id,results=[],queued_entries=[])
            fresh=[entry for entry in entries if entry['id'] not in bundle['queued_entries']]
            if not fresh:abort(409,'These results are already in this case’s review inbox.')
            bundle['results'].extend(section_for(entry,record_id) for entry in fresh)
            bundle['queued_entries'].extend(entry['id'] for entry in fresh)
            store.put(key,'review_bundle',bundle)
            return redirect(url_for('case_review.inbox',case_id=case_id))
        from case_workflow import enrich, findings
        existing={json.dumps(f.get('research_source'),sort_keys=True) for _,_,_,f in findings(case) if f.get('research_source')}
        fresh=[entry for entry in entries if json.dumps(dict(record_id=record_id,entry_id=entry['id']),sort_keys=True) not in existing]
        if not fresh:abort(409,'These results have already been saved to this case.')
        sections=[section_for(entry,record_id) for entry in fresh]
        for entry,section in zip(fresh,sections):
            if entry['id'] in edits:
                f=section['findings'][0]
                f['research_original_label']=f['label']
                f.update(edits[entry['id']])
        record=app.make_search_record(item['kind'],item['target'],sections,app.result_summary(sections))
        enrich(record);case.setdefault('searches',[]).append(record)
        save_review_case(case,'research_saved','Saved selected research results as unverified findings.')
    if request.accept_mimetypes.best=='application/json':
        count=len(fresh)
        return jsonify(message=f'Added {count} result'+('s' if count!=1 else '')+' to '+case['name']+'.',added=count,selected_ids=selected)
    return redirect(url_for('research_hub.result',record_id=record_id,page=max(1,request.form.get('return_page',1,type=int) or 1),domain=request.form.get('return_domain','')[:253]))

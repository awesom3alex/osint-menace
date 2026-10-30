"""Additional reviewed research tools; external calls are explicit and bounded."""
import datetime as dt
import hashlib
import ipaddress
import json
import math
import os
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path
from urllib.parse import quote, urlencode, urlsplit

import phonenumbers

import tool_credentials as credentials
from collectors import Options, fetch, phone

NEARBY_LOCK = threading.Lock()
LAST_NEARBY = 0.0
CATEGORIES = {'businesses':'["shop"]', 'amenities':'["amenity"]', 'landmarks':'["tourism"]'}


def entry(label, value, source, url='', method='', key='', local=False):
    from research_hub import finding
    return dict(id=key or hashlib.sha256((source+json.dumps(value,sort_keys=True)).encode()).hexdigest()[:32],
                mode='local' if local else 'passive',finding=finding(label,value,source,url,method))


def request_json(url):
    response=fetch(url,timeout=15,max_bytes=2_000_000)
    if response['status']!='found':
        raise ValueError('Provider unavailable, blocked, or rate-limited. No findings were inferred.')
    try:return json.loads(response['body'])
    except (ValueError,UnicodeError):raise ValueError('Provider returned an unreadable response.') from None


def coordinates(original):
    try:
        parts=original.split(',')
        if len(parts)!=2:raise ValueError
        lat,lon=map(float,parts)
        if not math.isfinite(lat) or not math.isfinite(lon) or not -90<=lat<=90 or not -180<=lon<=180:raise ValueError
        return lat,lon
    except (ValueError,TypeError):raise ValueError('Enter latitude, longitude in valid coordinate ranges.') from None


def distance(lat,lon,other_lat,other_lon):
    a,b=map(math.radians,(lat,other_lat))
    dlat,dlon=math.radians(other_lat-lat),math.radians(other_lon-lon)
    h=math.sin(dlat/2)**2+math.cos(a)*math.cos(b)*math.sin(dlon/2)**2
    return round(6371000*2*math.asin(math.sqrt(min(1,max(0,h)))))


def nearby_places(original,data):
    import overpy
    global LAST_NEARBY
    lat,lon=coordinates(original)
    radius=data.get('radius','250');category=data.get('category','amenities')
    if str(radius) not in ('100','250','500','1000') or category not in CATEGORIES:
        raise ValueError('Choose a radius of 100–1,000 metres and a supported category.')
    if data.get('nearby_confirm') is not True:
        raise ValueError('Confirm that the coordinates may be sent to the public Overpass provider.')
    radius=int(radius)
    query=f'[out:json][timeout:12][maxsize:2000000];nwr(around:{radius},{lat},{lon}){CATEGORIES[category]};out center tags 100;'
    provider='https://overpass-api.de/api/interpreter'
    with NEARBY_LOCK:
        delay=1.1-(time.monotonic()-LAST_NEARBY)
        if delay>0:time.sleep(delay)
        try:raw=request_json(provider+'?'+urlencode(dict(data=query)))
        finally:LAST_NEARBY=time.monotonic()
    if not isinstance(raw,dict) or raw.get('remark'):
        raise ValueError('Overpass could not complete this query. Try a smaller radius later.')
    result=overpy.Overpass().parse_json(json.dumps(raw))
    entries=[]
    for kind,items in (('node',result.nodes),('way',result.ways),('relation',result.relations)):
        for place in items:
            a=getattr(place,'lat',None) if kind=='node' else place.center_lat
            b=getattr(place,'lon',None) if kind=='node' else place.center_lon
            if a is None or b is None:continue
            a,b=float(a),float(b)
            if not math.isfinite(a) or not math.isfinite(b) or not -90<=a<=90 or not -180<=b<=180:continue
            tags={str(k)[:100]:str(v)[:2000] for k,v in list(place.tags.items())[:60]}
            value=dict(original=original,latitude=a,longitude=b,approximate_distance_m=distance(lat,lon,a,b),radius_m=radius,category=category,
                       tags=tags,provider=provider,attribution='© OpenStreetMap contributors, ODbL',
                       map_url=f'https://www.openstreetmap.org/{kind}/{place.id}',
                       limitations='Mapped places only. Distances use a point or geometry centre, not walking distance. Proximity does not establish an association. Coverage may be incomplete.')
            entries.append(entry(tags.get('name') or 'Mapped '+kind,value,'OpenStreetMap / Overpass',value['map_url'],'Explicit radius query; no resident or ownership lookup.',key=hashlib.sha256(f'{kind}:{place.id}'.encode()).hexdigest()[:32]))
    entries.sort(key=lambda e:e['finding']['value']['approximate_distance_m'])
    return entries[:50], ['Provider result cap reached; nearby coverage may be incomplete.'] if len(raw.get('elements',[]))>=100 else []


def international_address(original,data):
    if len(original)>500:raise ValueError('International addresses are limited to 500 characters.')
    worker=Path(__file__).parent/'scripts/address_extract.py'
    try:
        parsed=subprocess.run([sys.executable,str(worker)],input=original.encode(),capture_output=True,timeout=45,
                              env={'PATH':os.environ.get('PATH',''),'PYTHONDONTWRITEBYTECODE':'1'})
    except subprocess.TimeoutExpired:raise ValueError('International parsing exceeded its time limit.') from None
    if parsed.returncode or len(parsed.stdout)>1_000_000:
        raise ValueError('International parser unavailable or input exceeded its limits. Install libpostal models and postal bindings with the supplied Docker build.')
    value=json.loads(parsed.stdout)
    value['original']=original
    value['limitations']='Suggested components and normalized forms only; original input is unchanged. This does not validate deliverability, residency, or ownership.'
    return [entry('International address breakdown',value,'libpostal / postal 1.1.11',method='Local international address parsing and normalization; no external geocoding.',local=True)],[]


def telephone(original,data):
    from research_hub import run_ddgs, search_plan
    region=data.get('phone_region','US')
    if not isinstance(region,str) or region.upper() not in phonenumbers.SUPPORTED_REGIONS:
        raise ValueError('Choose a supported two-letter telephone region.')
    try:number=phonenumbers.parse(original,region.upper())
    except phonenumbers.NumberParseException:raise ValueError('The telephone number could not be parsed.') from None
    if not phonenumbers.is_possible_number(number):raise ValueError('The telephone number has an impossible length for its numbering plan.')
    canonical=phonenumbers.format_number(number,phonenumbers.PhoneNumberFormat.E164)
    sections=phone(original,Options(region=region.upper()))
    metadata=sections[0]['findings'][0]['value']['data']
    metadata=dict(original=original,**metadata)
    metadata['limitations']='Numbering-plan metadata only. Carrier allocation may be outdated after porting; region is not a live location and metadata does not identify the subscriber.'
    entries=[entry('Telephone numbering metadata',metadata,'libphonenumber '+phonenumbers.__version__,method='Offline numbering-plan analysis.',local=True)]
    errors=[]
    if data.get('phoneinfoga'):
        import addon_tools
        binary=addon_tools.executable('phoneinfoga')
        if not binary.is_file():errors.append('PhoneInfoga is not installed in this runtime; local metadata remains available.')
        else:
            try:
                # No inherited API keys, .env, sessions, or paid-provider credentials.
                with tempfile.TemporaryDirectory(prefix='menace-phone-') as cwd:
                    output=subprocess.run([str(binary),'scan','-n',canonical],cwd=cwd,capture_output=True,timeout=30,
                                          env=credentials.environment('phoneinfoga',{'PATH':os.environ.get('PATH',''),'HOME':cwd,'NO_COLOR':'1','TERM':'dumb'}))
                if output.returncode:errors.append('PhoneInfoga could not complete this number; other selected sources remain available.')
                else:
                    text=credentials.redact(addon_tools.ANSI.sub('',output.stdout.decode('utf-8',errors='replace')))[:30000]
                    if text.strip():entries.append(entry('PhoneInfoga results',dict(original=original,e164=canonical,output=text,limitations='Upstream output and search links are unverified leads; no subscriber identity is confirmed.'),'PhoneInfoga',method='Explicit optional scanner request; API credentials are not inherited.'))
            except subprocess.TimeoutExpired:errors.append('PhoneInfoga exceeded its 30-second time limit.')
    if data.get('phone_web'):
        try:
            plan=search_plan(dict(q=canonical,mode='phone',phone_region=region.upper(),backend=data.get('phone_engine','duckduckgo'),limit=10))
            found,failures,ledger=run_ddgs(plan)
            for item in found:
                item['finding']['value']['query_status']=ledger
                item['finding']['value']['original_input']=original
            entries.extend(found);errors.extend(failures)
        except ValueError as exc:errors.append(str(exc))
    return entries,errors


def archive_history(original,data):
    from waybackpy.cdx_snapshot import CDXSnapshot

    from research_hub import safe_url
    target=safe_url(original)
    if not target:raise ValueError('Enter a public HTTP(S) page URL without credentials.')
    host=urlsplit(target).hostname
    if host=='localhost' or host.endswith(('.localhost','.local','.internal')) or '.' not in host:
        raise ValueError('Use a public page URL.')
    try:address=ipaddress.ip_address(host)
    except ValueError:address=None
    if address and not address.is_global:raise ValueError('Use a public page URL.')
    if data.get('archive_confirm') is not True:raise ValueError('Confirm that this public URL may be sent to the Internet Archive.')
    params=dict(url=target,matchType='exact',output='json',fl='urlkey,timestamp,original,mimetype,statuscode,digest,length',filter='statuscode:200',collapse='digest',limit=50)
    dates={}
    for field in ('archive_from','archive_to'):
        value=data.get(field,'')
        if value:
            try:dates[field]=dt.date.fromisoformat(value)
            except (TypeError,ValueError):raise ValueError('Choose valid archive dates.') from None
    if len(dates)==2 and dates['archive_from']>dates['archive_to']:raise ValueError('Archive start date must precede the end date.')
    if 'archive_from' in dates:params['from']=dates['archive_from'].strftime('%Y%m%d')+'000000'
    if 'archive_to' in dates:params['to']=dates['archive_to'].strftime('%Y%m%d')+'235959'
    provider='https://web.archive.org/cdx/search/cdx'
    rows=request_json(provider+'?'+urlencode(params))
    if not isinstance(rows,list):raise ValueError('Archive returned an unexpected index response.')
    if not rows:return [],[]
    expected=params['fl'].split(',')
    if rows[0]!=expected:raise ValueError('Archive index columns could not be recognized.')
    entries=[];seen=set()
    for row in rows[1:51]:
        if not isinstance(row,list) or len(row)!=len(expected):continue
        props=dict(zip(expected,map(str,row)))
        source=safe_url(props['original'])
        if not source or urlsplit(source)[1:4]!=urlsplit(target)[1:4] or props['statuscode']!='200':continue
        try:snapshot=CDXSnapshot(props)
        except ValueError:continue
        key=hashlib.sha256((snapshot.timestamp+source).encode()).hexdigest()[:32]
        if key in seen:continue
        seen.add(key)
        value=dict(original=original,archived_original=source,capture_time=snapshot.datetime_timestamp.isoformat()+'Z',archive_timestamp=snapshot.timestamp,
                   archive_url=safe_url('https://web.archive.org/web/'+snapshot.timestamp+'/'+quote(source,safe=':/?=&%')),
                   mimetype=snapshot.mimetype,status_code=snapshot.statuscode,digest=snapshot.digest,provider=provider,
                   filters=dict(from_date=data.get('archive_from',''),to_date=data.get('archive_to',''),matching='exact URL',collapse='content digest'),
                   limitations='Archive index metadata only; capture date is not a publication date. Availability may change. Opening a capture is explicit; no new public snapshot is created.')
        entries.append(entry('Archived page — '+value['capture_time'],value,'Internet Archive / Wayback CDX',value['archive_url'],'Exact-URL archive index lookup; content not fetched or automatically published.',key=key))
    entries.sort(key=lambda e:e['finding']['value']['capture_time'],reverse=True)
    return entries,['Archive index reached the 50-capture limit. Narrow the date window for more focused results.'] if len(rows)>50 else []


TOOLS={'telephone':telephone,'nearby_places':nearby_places,'international_address':international_address,'archive_history':archive_history}

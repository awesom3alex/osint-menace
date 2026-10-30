"""Analyst-controlled review queues, identity decisions, report chronologies, and case health."""
import copy
import datetime as dt
import hashlib
import json
import re
import uuid
from collections import defaultdict

from flask import Blueprint, abort, redirect, render_template, request, url_for

from case_workflow import event, findings
from investigation import target_url

bp = Blueprint('case_review', __name__)


def save_review_case(case, kind, description):
    import app
    from case_backups import MAX_CASE, encode
    event(case, kind, description)
    case['updated_at'] = app.utc_now()
    if len(encode(case)) > MAX_CASE:
        abort(400, 'Case exceeds the backup size limit; no changes were saved.')
    app.save_case(case)


def require_version(case):
    if request.form.get('updated_at') != case['updated_at']:
        abort(409, 'This case changed. Reload the page before recording a decision.')


def inbox_items(case):
    """Only explicitly case-associated searches and retained changed observations."""
    import addon_tools
    import workspace_features
    import workspace_store
    output = []
    with workspace_store.connect() as db:
        rows = db.execute("SELECT payload FROM records WHERE type IN ('console','unified','global_search','research_tool','review_bundle','addon') AND json_extract(payload,'$.origin_case_id')=? ORDER BY created DESC", (case['id'],))
        for (payload,) in rows:
            search = json.loads(payload)
            sections = []
            if search.get('tool') in addon_tools.GITHUB_TOOLS and search.get('status') in ('completed','limited'):
                sections = [(search['id'], workspace_features.finding_section(search))]
            elif 'job_ids' in search:
                for job_id in search['job_ids']:
                    job = workspace_store.get(job_id)
                    if job and job.get('status') in ('completed', 'limited', 'rate-limited'):
                        sections.append((job_id, workspace_features.finding_section(job)))
            else:
                sections = [(str(i), section) for i, section in enumerate(search.get('results', []))]
            for sid, section in sections:
                for index, finding in enumerate(section.get('findings', [])):
                    content = json.dumps(finding, sort_keys=True, ensure_ascii=False)
                    key = 'search:' + search['id'] + ':' + sid + ':' + str(index) + ':' + hashlib.sha256(content.encode()).hexdigest()[:16]
                    output.append(dict(key=key, kind='Search result', label=finding.get('label', 'Finding'), timestamp=search.get('timestamp', ''),
                                       text=str(finding.get('value', ''))[:1500], finding=finding, section=section,
                                       search=search, url=url_for('research_hub.result',record_id=search['source_record_id']) if search.get('source_record_id') else url_for('workspace.history_detail', record_id=search['id'])))
    for ref, _, _, finding in findings(case):
        observations = finding.get('observations', [])
        for previous, latest in zip(observations, observations[1:]):
            if previous['sha256'] != latest['sha256']:
                output.append(dict(key='change:' + ref + ':' + latest['id'], kind='Source change', ref=ref,
                                   label=finding['label'], timestamp=latest['timestamp'], text=latest['text'][:1500],
                                   url=url_for('case_research.observations', case_id=case['id'], ref=ref, before=previous['id'], after=latest['id'])))
    return sorted(output, key=lambda item:item['timestamp'], reverse=True)


@bp.get('/cases/<case_id>/inbox')
def inbox(case_id):
    import app
    case = app.load_case(case_id)
    items = inbox_items(case)
    decisions = case.get('review_inbox', {})
    reviewed = request.args.get('state') == 'reviewed'
    filtered = [item for item in items if (item['key'] in decisions) == reviewed]
    ref_filter = request.args.get('ref', '')
    if reviewed and ref_filter:
        filtered = [item for item in filtered if decisions[item['key']]['ref'] == ref_filter]
    page = max(1, request.args.get('page', 1, type=int) or 1)
    return render_template('review_inbox.html', case=case, items=filtered[(page-1)*30:page*30], total=len(filtered), page=page,
                           has_next=len(filtered)>page*30, reviewed=reviewed, decisions=decisions, ref_filter=ref_filter,
                           targets=[(ref, f['label']) for ref, _, _, f in findings(case)])


@bp.post('/cases/<case_id>/inbox')
def decide_inbox(case_id):
    import app
    with app.CASE_LOCK:
        case = app.load_case(case_id)
        require_version(case)
        item = next((i for i in inbox_items(case) if i['key'] == request.form.get('key')), None)
        if not item:
            abort(404, 'This review item is no longer available.')
        decisions = case.setdefault('review_inbox', {})
        if item['key'] in decisions:
            abort(409, 'This item already has a recorded decision.')
        action, notes = request.form.get('action'), request.form.get('notes', '').strip()
        if action not in ('accept', 'dismiss', 'link') or len(notes) > 5000 or len(decisions) >= 10000:
            abort(400, 'Choose a valid decision and keep notes under 5,000 characters.')
        ref = request.form.get('ref', '') if action == 'link' else item.get('ref', '')
        if action == 'link' and ref not in {r for r, _, _, _ in findings(case)}:
            abort(400, 'Choose an existing finding to link.')
        if action == 'accept' and item['kind'] == 'Search result':
            origin = item['finding'].get('research_source')
            if origin and any(f.get('research_source') == origin for _,_,_,f in findings(case)):
                abort(409, 'This research result is already in the case. Link it to the existing finding instead.')
            section = copy.deepcopy(item['section'])
            section.update(findings=[copy.deepcopy(item['finding'])], links=[], notes=['Accepted from the review inbox. Original search remains in History.'])
            section['findings'][0]['verification_status'] = 'Unverified'
            record = app.make_search_record(item['search'].get('kind', 'auto'), item['search'].get('target', ''), [section], app.result_summary([section]))
            from case_workflow import enrich
            enrich(record)
            record['review_origin'] = item['key']
            case.setdefault('searches', []).append(record)
            ref = record['id'] + ':0:0'
        decisions[item['key']] = dict(action=action, ref=ref, notes=notes, timestamp=app.utc_now(), label=str(item['label'])[:2000])
        save_review_case(case, 'inbox_reviewed', 'Reviewed ' + item['kind'].lower() + ': ' + action + '.')
    return redirect(url_for('case_review.inbox', case_id=case_id))


def entities(case):
    return {g['id'] + ':' + n['id']: dict(graph=g, node=n) for g in case.get('graphs', []) for n in g['nodes'] if not n.get('annotation')}


def identity_keys(node):
    keys = set()
    for field in [dict(name=node['type'], value=node['label']), *node.get('fields', [])]:
        name, value = field['name'].casefold(), str(field.get('value', '')).strip().casefold()
        if not value:
            continue
        if re.search(r'email|e-mail', name):
            keys.add(('email', value))
        elif re.search(r'phone|telephone|mobile', name):
            digits = re.sub(r'\D', '', value)
            if len(digits) >= 7:
                keys.add(('phone', digits))
        elif re.search(r'username|handle', name):
            keys.add(('username', value.lstrip('@')))
        elif re.search(r'domain', name):
            keys.add(('domain', value.rstrip('.')))
    return keys


def identity_suggestions(lookup):
    index = defaultdict(list)
    pairs = set()
    output = []
    for key, item in lookup.items():
        for token in identity_keys(item['node']):
            for other in index[token][:30]:
                pair = tuple(sorted((key, other)))
                if pair not in pairs:
                    pairs.add(pair)
                    output.append(dict(left=other, right=key, reason='Matching ' + token[0]))
                    if len(output) >= 100:
                        return output
            index[token].append(key)
    return output


def entity_snapshot(item):
    node = copy.deepcopy(item['node'])
    photo = node.pop('photo', '')
    node.pop('position', None)
    return dict(graph_id=item['graph']['id'], graph_name=item['graph']['name'], node=node,
                photo_sha256=hashlib.sha256(photo.encode()).hexdigest() if photo else '')


@bp.get('/cases/<case_id>/resolve')
def resolve(case_id):
    import app
    case = app.load_case(case_id)
    lookup = entities(case)
    left, right = request.args.get('left', ''), request.args.get('right', '')
    if (left and left not in lookup) or (right and right not in lookup):
        abort(404)
    query = request.args.get('q', '').strip()[:200].casefold()
    options = {key:item for key,item in lookup.items() if not query or query in json.dumps(item['node'], ensure_ascii=False).casefold()}
    options = dict(list(options.items())[:500])
    for key in (left, right):
        if key:
            options[key] = lookup[key]
    pair = (lookup[left], lookup[right]) if left and right else None
    return render_template('entity_resolution.html', case=case, options=options, lookup=lookup, left=left, right=right, pair=pair,
                           suggestions=identity_suggestions(lookup), resolutions=case.get('entity_resolutions', []), query=query)


@bp.post('/cases/<case_id>/resolve')
def decide_identity(case_id):
    import app
    with app.CASE_LOCK:
        case = app.load_case(case_id)
        require_version(case)
        lookup = entities(case)
        left, right = request.form.get('left'), request.form.get('right')
        decision, reason = request.form.get('decision'), request.form.get('reason', '').strip()
        if left == right or left not in lookup or right not in lookup or decision not in ('same_entity', 'different_entities', 'related') or not 1 <= len(reason) <= 5000:
            abort(400, 'Compare two different objects and record a decision with supporting reasoning.')
        records = case.setdefault('entity_resolutions', [])
        if len(records) >= 1000:
            abort(400, 'This case already has 1,000 retained identity decisions.')
        records.append(dict(id=uuid.uuid4().hex, left=left, right=right, decision=decision, reason=reason, timestamp=app.utc_now(),
                            left_snapshot=entity_snapshot(lookup[left]), right_snapshot=entity_snapshot(lookup[right])))
        save_review_case(case, 'identity_reviewed', 'Recorded an analyst identity assessment; original objects retained.')
    return redirect(url_for('case_review.resolve', case_id=case_id, left=left, right=right))


def timeline_rows(case):
    """Report-safe chronology with explicit date semantics, stable IDs, and exclusions."""
    from case_workflow import report_case
    eligible = {ref for ref, _, _, f in findings(report_case(case)) if f.get('include_in_report', True)}
    all_refs = {ref for ref, _, _, _ in findings(case)}
    rows = []
    def add(key, timestamp, basis, label, notes='', refs=()):
        if not timestamp:
            return
        rows.append(dict(id=hashlib.sha256(key.encode()).hexdigest(), timestamp=timestamp, basis=basis,
                         label=label, notes=notes, refs=[ref for ref in refs if ref in eligible]))
    for ref, search, _, finding in findings(report_case(case)):
        if ref not in eligible:
            continue
        add('finding:' + ref, finding.get('collected_at') or search.get('created_at', ''), 'Collection time', finding['label'], str(finding.get('source') or ''), [ref])
        for attachment in finding.get('evidence', []):
            if attachment.get('captured_at'):
                add('capture:' + ref + ':' + attachment['id'], attachment['captured_at'], 'Capture time (analyst supplied)', attachment.get('caption') or 'Screenshot', refs=[ref])
            add('attachment:' + ref + ':' + attachment['id'], attachment.get('created_at', ''), 'Attachment time', attachment.get('caption') or 'Screenshot attached', refs=[ref])
    for graph in case.get('graphs', []):
        for edge in graph['edges']:
            refs = edge.get('evidenceRefs', [])
            if any(ref not in eligible for ref in refs):
                continue
            nodes = {node['id']:node for node in graph['nodes']}
            linked = [ref for key in (edge['source'],edge['target']) for ref in [nodes.get(key,{}).get('source',''),*nodes.get(key,{}).get('sourceRefs',[])] if ref]
            if any(ref not in eligible for ref in linked):
                continue
            add('edge:' + graph['id'] + ':' + edge['id'], edge.get('date', ''), 'Relationship event date (analyst supplied)',
                edge['label'] + ' — ' + edge.get('status', 'hypothesis'), edge.get('notes', ''), refs)
    for entry in case.get('investigation', {}).get('timeline', []):
        target = entry.get('target', '')
        if target in all_refs and target not in eligible:
            continue
        if target.startswith('edge:'):
            # Reuse the same exclusion checks applied to dated relationship entries.
            if not any(row['id'] == hashlib.sha256(target.encode()).hexdigest() for row in rows):
                continue
        add('analyst:' + entry['id'], entry.get('timestamp', ''), 'Event time (analyst supplied)', entry['title'], entry.get('notes', ''), [target] if target in eligible else [])
    def sortkey(row):
        try:
            value = dt.datetime.fromisoformat(row['timestamp'].replace('Z', '+00:00'))
            return value.replace(tzinfo=value.tzinfo or dt.timezone.utc).timestamp()
        except ValueError:
            return float('-inf')
    return sorted(rows, key=sortkey)


def timeline_item(case):
    selected = set(case.get('timeline_export', {}).get('selected', []))
    rows = [row for row in timeline_rows(case) if row['id'] in selected]
    if not rows:
        return None
    return dict(id='timeline', kind='notes', label='Investigation chronology', text='', default=case.get('timeline_export', {}).get('include_report', False),
                timeline_rows=rows, timeline_refs=list(dict.fromkeys(ref for row in rows for ref in row['refs'])))


def readable_time(value):
    try:
        if len(value) == 10:
            return dt.date.fromisoformat(value).strftime('%d %b %Y') + ' (date only)'
        parsed = dt.datetime.fromisoformat(value.replace('Z', '+00:00'))
        if parsed.tzinfo is None:
            return parsed.strftime('%d %b %Y, %H:%M') + ' (no UTC offset recorded)'
        return parsed.astimezone(dt.timezone.utc).strftime('%d %b %Y, %H:%M UTC')
    except ValueError:
        return value


def timeline_text(rows, numbers):
    lines = ['Dates distinguish event time from collection/attachment time. Analyst-supplied dates require corroboration.']
    for row in rows:
        lines.extend(['', row['timestamp'] + ' | ' + row['basis'], row['label']])
        if row['notes']:
            lines.append(row['notes'])
        refs = [numbers[ref] for ref in row['refs'] if ref in numbers]
        if refs:
            lines.append('Sources: ' + ', '.join(refs))
    return '\n'.join(lines)


@bp.route('/cases/<case_id>/timeline-export', methods=['GET', 'POST'])
def select_timeline(case_id):
    import app
    if request.method == 'POST':
        with app.CASE_LOCK:
            case = app.load_case(case_id)
            require_version(case)
            selected = request.form.getlist('selected')
            allowed = {row['id'] for row in timeline_rows(case)}
            if len(selected) != len(set(selected)) or not set(selected) <= allowed:
                abort(400, 'Timeline content changed. Reload and select current events.')
            include = request.form.get('include_report') == 'on' and bool(selected)
            case['timeline_export'] = dict(selected=selected, include_report=include)
            builder = case.get('report_builder')
            if builder is not None:
                builder['selected'] = [key for key in builder['selected'] if key != 'timeline']
                if include:
                    if 'timeline' not in builder['order']:
                        builder['order'].append('timeline')
                    builder['selected'].append('timeline')
            save_review_case(case, 'timeline_selected', 'Updated selected report chronology events.')
        return redirect(url_for('case_review.select_timeline', case_id=case_id))
    case = app.load_case(case_id)
    return render_template('timeline_export.html', case=case, rows=timeline_rows(case), config=case.get('timeline_export', {}))


@bp.get('/cases/<case_id>/timeline.<kind>')
def export_timeline(case_id, kind):
    from flask import Response

    import app
    import report_builder
    if kind not in ('pdf', 'docx'):
        abort(404)
    case = copy.deepcopy(app.load_case(case_id))
    if timeline_item(case) is None:
        abort(400, 'Select and save chronology events before exporting.')
    case['name'] += ' — Investigation chronology'
    case['report_builder'] = dict(order=['timeline'], selected=['timeline'], summary=dict(purpose='Selected investigation chronology.', findings='Event dates are distinguished from collection and attachment dates.', questions='Analyst-supplied dates require corroboration.'))
    body = report_builder.pdf(case) if kind == 'pdf' else report_builder.word(case).getvalue()
    return Response(body, mimetype='application/pdf' if kind == 'pdf' else 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
                    headers={'Content-Disposition': 'attachment; filename="investigation-timeline.'+kind+'"', 'Cache-Control':'no-store'})


def health_issues(case):
    from pathlib import Path

    import case_features
    from demo import DEMO_ID
    issues = []
    refs = {ref for ref, _, _, _ in findings(case)}
    today = dt.datetime.now(dt.timezone.utc).date().isoformat()
    for ref, _, section, finding in findings(case):
        link = target_url(case, ref)
        if not finding.get('source_url') and section.get('module', {}).get('mode') != 'local':
            issues.append(dict(kind='Source provenance', title=finding['label'], detail='No source URL recorded. Add a source or document a local derivation in analyst notes.', url=link))
        for attachment in finding.get('evidence', []):
            path = case_features.EVIDENCE_DIR / case['id'] / (attachment['id'] + '.png')
            if case['id'] == DEMO_ID:
                path = Path(__file__).parent/'static/demo'/(attachment['id']+'.png')
            if not path.is_file():
                issues.append(dict(kind='Missing attachment', title=attachment.get('caption') or finding['label'], detail='The referenced screenshot file is missing from this host.', url=link))
    for graph in case.get('graphs', []):
        for edge in graph['edges']:
            support = edge.get('evidenceRefs', [])
            if not support or any(ref not in refs for ref in support):
                issues.append(dict(kind='Unsupported connection', title=edge['label'], detail='No supporting findings are linked, or a linked finding no longer exists.', url=url_for('case_graphs.workspace', case_id=case['id'], graph=graph['id'], focus=edge['id'])))
    for task in case.get('investigation', {}).get('tasks', []):
        if task['status'] != 'Complete' and task.get('due') and task['due'] < today:
            issues.append(dict(kind='Overdue task', title=task['title'], detail='Due '+task['due'], url=url_for('investigation.workspace', case_id=case['id'], _anchor='tasks')))
    for key, assessment in case.get('investigation', {}).get('assessments', {}).items():
        if assessment.get('confidence') in ('Medium', 'High') and (not assessment.get('refs') or any(ref not in refs for ref in assessment['refs'])):
            issues.append(dict(kind='Unsupported assessment', title=key, detail='Confidence is recorded without valid supporting findings.', url=url_for('investigation.workspace', case_id=case['id'], _anchor='confidence')))
    return issues


@bp.get('/cases/<case_id>/health')
def health(case_id):
    import app
    case = app.load_case(case_id)
    issues = health_issues(case)
    counts = {kind:sum(item['kind'] == kind for item in issues) for kind in sorted({item['kind'] for item in issues})}
    return render_template('case_health.html', case=case, issues=issues, counts=counts)


def validate_review_data(case):
    reviews = case.get('review_inbox', {})
    if not isinstance(reviews, dict) or len(reviews) > 10000:
        raise ValueError('Invalid review inbox decisions.')
    for key, item in reviews.items():
        if (not isinstance(key, str) or len(key)>300 or not isinstance(item, dict) or item.get('action') not in ('accept','dismiss','link')
                or any(not isinstance(item.get(field), str) or len(item[field])>limit for field,limit in [('ref',200),('notes',5000),('timestamp',100),('label',2000)])):
            raise ValueError('Invalid inbox decision.')
    resolutions = case.get('entity_resolutions', [])
    if not isinstance(resolutions, list) or len(resolutions)>1000:
        raise ValueError('Invalid identity decisions.')
    for record in resolutions:
        if (not isinstance(record, dict) or record.get('decision') not in ('same_entity','different_entities','related')
                or any(not isinstance(record.get(key), str) or len(record[key])>limit for key,limit in [('id',32),('left',200),('right',200),('reason',5000),('timestamp',100)])):
            raise ValueError('Invalid identity decision.')
        for key in ('left_snapshot','right_snapshot'):
            snap=record.get(key)
            if not isinstance(snap,dict) or not isinstance(snap.get('node'),dict) or not isinstance(snap['node'].get('label'),str) or not isinstance(snap['node'].get('fields'),list):
                raise ValueError('Invalid identity comparison snapshot.')
            from case_graphs import fields_valid
            fields_valid(snap['node']['fields'])
    selection = case.get('timeline_export', {})
    if (not isinstance(selection,dict) or not isinstance(selection.get('selected',[]),list) or len(selection.get('selected',[]))>10000
            or type(selection.get('include_report',False)) is not bool or not all(isinstance(key,str) and re.fullmatch('[a-f0-9]{64}',key) for key in selection.get('selected',[]))):
        raise ValueError('Invalid selected chronology.')
    if len(selection.get('selected',[])) != len(set(selection.get('selected',[]))):
        raise ValueError('Duplicate chronology event selections.')

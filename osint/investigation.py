"""Case chronology, reviewed confidence, tasks and shareable report redaction."""
import copy
import datetime as dt
import uuid
from urllib.parse import urlencode

from flask import Blueprint, abort, redirect, render_template, request, url_for

from case_workflow import event, findings

bp = Blueprint('investigation', __name__)
LEVELS = ('Not assessed', 'Low', 'Medium', 'High')


def targets(case):
    output = {ref: f.get('label', 'Finding') for ref, _, _, f in findings(case)}
    for graph in case.get('graphs', []):
        for edge in graph['edges']:
            output['edge:' + graph['id'] + ':' + edge['id']] = graph['name'] + ' / ' + edge['label']
    return output


def validate(data):
    """Validate imported investigation settings before any template/export consumes them."""
    if not isinstance(data, dict):
        raise ValueError('Invalid investigation settings.')
    for key in ('tasks', 'timeline'):
        records = data.get(key, [])
        if not isinstance(records, list) or len(records) > 2000:
            raise ValueError('Invalid investigation records.')
        for record in records:
            if not isinstance(record, dict) or not isinstance(record.get('id'), str):
                raise ValueError('Invalid investigation record.')
            for field in ('id', 'title', 'notes', 'timestamp', 'due', 'target', 'status'):
                if not isinstance(record.get(field, ''), str) or len(record.get(field, '')) > 20000:
                    raise ValueError('Invalid investigation text.')
            try:
                if record.get('due'):
                    dt.date.fromisoformat(record['due'])
                if record.get('timestamp'):
                    dt.datetime.fromisoformat(record['timestamp'].replace('Z', '+00:00'))
            except ValueError:
                raise ValueError('Invalid investigation date.')
            if key == 'tasks' and record.get('status') not in ('Open', 'In progress', 'Complete'):
                raise ValueError('Invalid task status.')
    assessments = data.get('assessments', {})
    if not isinstance(assessments, dict) or len(assessments) > 5000:
        raise ValueError('Invalid confidence assessments.')
    for key, value in assessments.items():
        if (not isinstance(key, str) or not isinstance(value, dict) or value.get('confidence') not in LEVELS
            or not isinstance(value.get('reason'), str) or len(value['reason']) > 20000
            or not isinstance(value.get('refs'), list) or len(value['refs']) > 100
            or not all(isinstance(ref, str) and len(ref) < 200 for ref in value['refs'])):
            raise ValueError('Invalid confidence assessment.')
    redaction = data.get('redaction', {})
    if (not isinstance(redaction, dict) or type(redaction.get('enabled', False)) is not bool
        or not isinstance(redaction.get('terms', []), list) or len(redaction.get('terms', [])) > 200
        or not all(isinstance(term, str) and 1 <= len(term) <= 500 for term in redaction.get('terms', []))):
        raise ValueError('Invalid report redaction.')


def target_url(case, target):
    if target.startswith('edge:') and target.count(':') == 2:
        _, graph_id, edge_id = target.split(':', 2)
        return url_for('case_graphs.workspace', case_id=case['id']) + '?' + urlencode(dict(graph=graph_id, focus=edge_id))
    if target.count(':') == 2:
        return url_for('case_detail', case_id=case['id']) + '#finding-' + target
    return url_for('case_detail', case_id=case['id'])


def chronology(case):
    from case_workflow import timeline
    output = [dict(timestamp=e.get('timestamp', ''), title=e['description'], notes='', kind='Activity', target=e.get('search_id', '')) for e in timeline(case)]
    for ref, search, _, finding in findings(case):
        output.append(dict(timestamp=finding.get('collected_at') or search.get('created_at', ''), title=finding.get('label', 'Finding'), notes=finding.get('source', ''), kind='Evidence', target=ref))
        for attachment in finding.get('evidence', []):
            output.append(dict(timestamp=attachment.get('captured_at') or attachment.get('created_at', ''), title=attachment.get('caption') or 'Screenshot captured', notes='Captured or attached evidence', kind='Capture', target=ref))
    for graph in case.get('graphs', []):
        for edge in graph['edges']:
            if edge.get('date'):
                output.append(dict(timestamp=edge['date'], title=edge['label'], notes=edge.get('notes', ''), kind='Relationship', target='edge:' + graph['id'] + ':' + edge['id']))
    for item in case.get('investigation', {}).get('timeline', []):
        output.append(dict(timestamp=item.get('timestamp', ''), title=item.get('title', ''), notes=item.get('notes', ''), target=item.get('target', ''), kind='Analyst event'))
    for item in output:
        target = item.get('target', '')
        if target.startswith('edge:') and target.count(':') == 2:
            _, graph_id, edge_id = target.split(':', 2)
            item['url'] = url_for('case_graphs.workspace', case_id=case['id']) + '?' + urlencode(dict(graph=graph_id, focus=edge_id))
        elif target.count(':') == 2:
            item['url'] = url_for('case_detail', case_id=case['id']) + '#finding-' + target
        elif target:
            ref = next((r for r, s, _, _ in findings(case) if s['id'] == target), '')
            item['url'] = url_for('case_detail', case_id=case['id']) + ('#finding-' + ref if ref else '')
    def timekey(item):
        try:
            date = dt.datetime.fromisoformat(item['timestamp'].replace('Z', '+00:00'))
            return date.replace(tzinfo=date.tzinfo or dt.timezone.utc).timestamp()
        except (ValueError, TypeError):
            return float('-inf')
    return sorted(output, key=timekey)


@bp.get('/cases/<case_id>/investigation')
def workspace(case_id):
    import app
    case = app.load_case(case_id)
    entries = chronology(case)
    kind = request.args.get('kind', '')
    start, end = request.args.get('from', ''), request.args.get('to', '')
    for date in (start, end):
        if date:
            try:
                dt.date.fromisoformat(date)
            except ValueError:
                abort(400, 'Use a valid date filter.')
    entries = [e for e in entries if (not kind or e['kind'] == kind) and (not start or e['timestamp'][:10] >= start) and (not end or e['timestamp'][:10] <= end)]
    return render_template('investigation.html', case=case, state=case.get('investigation', {}),
                           entries=entries, targets=targets(case), target_links={key: target_url(case, key) for key in targets(case)}, evidence={r: f.get('label', 'Finding') for r, _, _, f in findings(case)}, levels=LEVELS,
                           today=dt.datetime.now(dt.timezone.utc).date().isoformat())


@bp.post('/cases/<case_id>/investigation/<action>')
def update(case_id, action):
    import app
    with app.CASE_LOCK:
        case = app.load_case(case_id)
        if request.form.get('version') != case.get('updated_at'):
            abort(409, 'The case changed. Reload the investigation workspace before saving.')
        state = copy.deepcopy(case.get('investigation', {}))
        target = request.form.get('target', '')
        if target and target not in targets(case):
            abort(400, 'The linked finding or connection no longer exists.')
        title, notes = request.form.get('title', '').strip(), request.form.get('notes', '').strip()
        if len(title) > 500 or len(notes) > 20000:
            abort(400, 'The title or notes are too long.')
        if action == 'event':
            timestamp = request.form.get('timestamp', '')
            try:
                moment = dt.datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
                timestamp = moment.replace(tzinfo=moment.tzinfo or dt.timezone.utc).astimezone(dt.timezone.utc).isoformat()
            except ValueError:
                abort(400, 'Enter a valid event date and time in UTC.')
            if not title:
                abort(400, 'An event title is required.')
            state.setdefault('timeline', []).append(dict(id=uuid.uuid4().hex, title=title, notes=notes, timestamp=timestamp, target=target))
            description = 'Added timeline event: ' + title
        elif action == 'task':
            due = request.form.get('due', '')
            if due:
                try:
                    dt.date.fromisoformat(due)
                except ValueError:
                    abort(400, 'Enter a valid due date.')
            if not title:
                abort(400, 'A task title is required.')
            state.setdefault('tasks', []).append(dict(id=uuid.uuid4().hex, title=title, notes=notes, target=target, due=due, status='Open', timestamp=app.utc_now()))
            description = 'Created task: ' + title
        elif action == 'task-status':
            task = next((t for t in state.get('tasks', []) if t['id'] == request.form.get('id')), None)
            if task is None or request.form.get('status') not in ('Open', 'In progress', 'Complete'):
                abort(400, 'Invalid task or status.')
            task['status'] = request.form['status']; description = 'Task ' + task['status'].lower() + ': ' + task['title']
        elif action == 'assessment':
            confidence = request.form.get('confidence')
            refs = request.form.getlist('refs')
            available = {r for r, _, _, _ in findings(case)}
            if not target or confidence not in LEVELS or not set(refs) <= available or (confidence != 'Not assessed' and not notes):
                abort(400, 'Choose a target and explain the confidence assessment with valid evidence references.')
            state.setdefault('assessments', {})[target] = dict(confidence=confidence, reason=notes, refs=list(dict.fromkeys(refs)), timestamp=app.utc_now())
            description = 'Reviewed confidence: ' + targets(case)[target]
        elif action == 'redaction':
            terms = list(dict.fromkeys(t.strip() for t in request.form.get('terms', '').splitlines() if t.strip()))
            state['redaction'] = dict(enabled=request.form.get('enabled') == 'on', terms=terms)
            description = 'Updated shareable report redaction'
        else:
            abort(404)
        try:
            validate(state)
        except ValueError as error:
            abort(400, str(error))
        case['investigation'] = state
        event(case, 'investigation_' + action, description)
        case['updated_at'] = app.utc_now(); app.save_case(case)
    return redirect(url_for('investigation.workspace', case_id=case_id, _anchor={'event':'timeline','task':'tasks','task-status':'tasks','assessment':'confidence','redaction':'redaction'}[action]))


def assessment_text(case, target, numbers):
    assessment = case.get('investigation', {}).get('assessments', {}).get(target)
    if not assessment:
        return ''
    labels = [numbers[r] for r in assessment['refs'] if r in numbers]
    return '\nConfidence: ' + assessment['confidence'] + '\nReasoning: ' + assessment['reason'] + ('\nSupporting sources: ' + ', '.join(labels) if labels else '')


def redact_report(data):
    """Redact only derived report material, never the saved case or original captures."""
    settings = data['case'].get('investigation', {}).get('redaction', {})
    data['display_name'] = data['case']['name']
    if not settings.get('enabled'):
        return data
    import re
    terms = sorted(settings.get('terms', []), key=len, reverse=True)
    pattern = re.compile('|'.join(re.escape(t) for t in terms), re.IGNORECASE) if terms else None
    def scrub(value):
        if isinstance(value, str):
            return pattern.sub('[REDACTED]', value) if pattern else value
        if isinstance(value, list):
            return [scrub(v) for v in value]
        if isinstance(value, tuple):
            return tuple(scrub(v) for v in value)
        if isinstance(value, dict):
            return {k: scrub(v) for k, v in value.items()}
        return value
    data['summary'] = scrub(data['summary']); data['appendix'] = scrub(data['appendix'])
    data['warnings'] = scrub(data['warnings'])
    data['display_name'] = scrub(data['display_name'])
    for block in data['blocks']:
        had_image = bool(block.pop('image', None)); block.pop('image_url', None)
        if had_image:
            block['text'] += '\n[Image omitted from this shareable report.]'
        for key in ('text', 'label', 'details', 'legend'):
            if key in block:
                # Keep validated color values intact while redacting legend text.
                if key == 'legend':
                    block[key] = [dict(e, type=scrub(e['type']), description=scrub(e['description'])) for e in block[key]]
                else:
                    block[key] = scrub(block[key])
    data['warnings'].append('Redaction is enabled. Matching text is replaced and all images are omitted. Review the PDF before sharing. Case JSON and backups contain the originals.')
    return data

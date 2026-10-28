"""Case search, graph entity profiles, sharing review, and starter templates."""
import copy
import json
import re
import unicodedata
import uuid

from flask import Blueprint, abort, render_template, request, url_for

from case_workflow import findings
from investigation import target_url

bp = Blueprint('case_tools', __name__)
TEMPLATES = {
    'blank': dict(name='Blank case', description='Start without predefined tasks or a graph.', tasks=[]),
    'footprint': dict(name='Digital footprint review', description='People and account fields, source review tasks, and a report outline.',
                      tasks=['Record the investigation scope and known identifiers', 'Corroborate candidate accounts with independent identifiers', 'Review exclusions and the shareable report']),
    'organization': dict(name='Organization research', description='Organization, website, and contact fields with research tasks.',
                         tasks=['Record the organization and relevant domains', 'Document published contacts and supporting sources', 'Review relationship claims and outstanding questions']),
    'incident': dict(name='Incident research', description='Incident fields, a dated evidence graph, and incident review tasks.',
                     tasks=['Record incident scope and the known event times', 'Attach evidence and distinguish event time from collection time', 'Review unsupported connections and draft the report']),
}


def prepare_template(case, key):
    """Apply a starter only to a newly created in-memory case."""
    from case_graphs import new_graph
    from report_builder import inventory
    if key not in TEMPLATES:
        raise ValueError('Choose a valid case template.')
    if key == 'blank':
        return case
    if case.get('searches') or case.get('graphs') or case.get('investigation'):
        raise ValueError('Templates apply only when creating a new case.')
    spec = TEMPLATES[key]
    case['case_template'] = key
    case['dossier'] = dict(reference='', subject_name='', analyst='', summary='', methodology='', tasks='', observations='')
    graph = new_graph(spec['name'])
    graph['report'] = dict(include=False)
    extra = {
        'footprint': ('Person', ['Known identifier', 'Identity association reasoning']),
        'organization': ('Organization', ['Published contact email', 'Published contact phone', 'Source date']),
        'incident': ('Evidence', ['Event time UTC', 'Collection time UTC', 'Incident reference']),
    }
    kind, names = extra[key]
    graph['templates'][kind].extend(dict(name=name, type='text', value='', options='', visible=False) for name in names)
    case['graphs'] = [graph]
    case['investigation'] = dict(tasks=[dict(id=uuid.uuid4().hex, title=title, notes='', due='', target='', status='Open', timestamp=case['created_at']) for title in spec['tasks']])
    items = inventory(case)
    case['report_builder'] = dict(summary=dict(purpose='', findings='', questions=''), order=[item['id'] for item in items], selected=[item['id'] for item in items if item.get('default', True)])
    return case


def graph_link(case, graph, item):
    if case.get('is_demo'):
        return url_for('report_builder.preview', case_id=case['id'])
    return url_for('case_graphs.workspace', case_id=case['id'], graph=graph['id'], focus=item['id'])


def records(case):
    from dossier import SECTIONS, dossier_values
    from readable_results import readable_text
    yield dict(kind='Notes', title='Case notes', text=case.get('notes', ''), url=url_for('case_detail', case_id=case['id']))
    values = dossier_values(case)
    for title, fields in SECTIONS:
        for key, label in fields:
            if values[key]:
                yield dict(kind='Notes', title=label, text=values[key], url=url_for('case_detail', case_id=case['id']))
    for ref, search, section, finding in findings(case):
        text = json.dumps(finding, ensure_ascii=False) + ' ' + search.get('query', '') + ' ' + section.get('name', '')
        yield dict(kind='Evidence', title=finding.get('label', 'Finding'), text=text, excerpt=readable_text(finding.get('value', '')) + '\n' + finding.get('analyst_notes', ''),
                   url=target_url(case, ref), status=finding.get('verification_status', 'Unverified'))
    for graph in case.get('graphs', []):
        for node in graph['nodes']:
            yield dict(kind='Entities', title=node['label'], text=json.dumps(node, ensure_ascii=False),
                       excerpt=node['type'] + ' · ' + graph['name'], url=url_for('case_tools.entity', case_id=case['id'], graph_id=graph['id'], node_id=node['id']))
        for edge in graph['edges']:
            yield dict(kind='Connections', title=edge['label'], text=json.dumps(edge, ensure_ascii=False), excerpt=edge.get('notes', ''), url=graph_link(case, graph, edge), status=edge.get('status', 'hypothesis'))
    state = case.get('investigation', {})
    for task in state.get('tasks', []):
        yield dict(kind='Tasks', title=task['title'], text=json.dumps(task, ensure_ascii=False), excerpt=task.get('notes', ''), url=url_for('investigation.workspace', case_id=case['id'], _anchor='tasks'), status=task['status'])
    for entry in state.get('timeline', []):
        yield dict(kind='Notes', title=entry['title'], text=entry.get('notes', ''), url=url_for('investigation.workspace', case_id=case['id'], _anchor='timeline'))
    labels = {ref: finding.get('label', 'Finding') for ref, _, _, finding in findings(case)}
    for key, assessment in state.get('assessments', {}).items():
        yield dict(kind='Notes', title='Confidence: ' + labels.get(key, 'Graph connection'), text=assessment['reason'], status=assessment['confidence'], url=url_for('investigation.workspace', case_id=case['id'], _anchor='confidence'))


@bp.get('/cases/<case_id>/search')
def search(case_id):
    import app
    case = app.load_case(case_id)
    query = request.args.get('q', '').strip()[:500]
    kind = request.args.get('kind', '')
    def normalize(value):
        return unicodedata.normalize('NFKC', value).casefold()
    tokens = normalize(query).split()
    digits = re.sub(r'\D', '', query)
    results = []
    if query:
        for item in records(case):
            if kind and item['kind'] != kind:
                continue
            text = normalize(item['title'] + ' ' + item['text'])
            phone_match = len(digits) >= 7 and re.fullmatch(r'[\d\s+().-]+', query) and any(digits in re.sub(r'\D', '', candidate) for candidate in re.findall(r'\+?\d[\d ()+.-]{5,}\d', text))
            if all(token in text for token in tokens) or phone_match:
                item.setdefault('excerpt', item['text'])
                excerpt = item['excerpt']
                match = normalize(excerpt).find(normalize(query))
                start = max(0, match - 70) if match >= 0 else 0
                item['excerpt'] = ('…' if start else '') + excerpt[start:start+260] + ('…' if len(excerpt)>start+260 else '')
                results.append(item)
    page = max(1, request.args.get('page', 1, type=int) or 1)
    return render_template('case_search.html', case=case, query=query, kind=kind, count=len(results), page=page,
                           results=results[(page-1)*25:page*25], has_next=len(results)>page*25)


@bp.get('/cases/<case_id>/entities')
def entities(case_id):
    import app
    case = app.load_case(case_id)
    items = [dict(node=node, graph=graph) for graph in case.get('graphs', []) for node in graph['nodes']]
    return render_template('entities.html', case=case, items=items)


@bp.get('/cases/<case_id>/entities/<graph_id>/<node_id>')
def entity(case_id, graph_id, node_id):
    import app
    case = app.load_case(case_id)
    graph = next((g for g in case.get('graphs', []) if g['id']==graph_id), None)
    node = next((n for n in graph['nodes'] if n['id']==node_id), None) if graph else None
    if node is None:
        abort(404)
    edges = [edge for edge in graph['edges'] if node_id in (edge['source'], edge['target'])]
    nodes = {n['id']:n for n in graph['nodes']}
    refs = set([node.get('source', ''), *node.get('sourceRefs', [])])
    keys = {'edge:' + graph_id + ':' + edge['id'] for edge in edges}
    for edge in edges:
        refs.update(edge.get('evidenceRefs', []))
    refs.discard('')
    keys.update(refs)
    state=case.get('investigation', {})
    assessments=[dict(key=key, **value) for key,value in state.get('assessments', {}).items() if key in keys]
    for assessment in assessments:
        refs.update(assessment['refs'])
    evidence=[dict(ref=ref, finding=finding, source=finding.get('source') or section.get('name', ''), url=target_url(case,ref)) for ref, _, section, finding in findings(case) if ref in refs]
    tasks=[task for task in state.get('tasks', []) if task.get('target') in keys | refs]
    return render_template('entity.html', case=case, graph=graph, node=node, edges=edges, nodes=nodes,
                           evidence=evidence, assessments=assessments, tasks=tasks,
                           graph_url=graph_link(case,graph,node))


def sharing_review(case):
    """Review only selected report findings and visible graph connections."""
    from graph_reports import sections
    from report_builder import compose, inventory, settings
    config=settings(case); selected=set(config['selected']); items=inventory(case)
    active_refs={item['ref'] for item in items if item['kind'] in ('finding','screenshot') and item['id'] in selected}
    graph_case=copy.deepcopy(case)
    for graph in graph_case.get('graphs', []):
        graph.setdefault('report', {})['include']='graph:'+graph['id'] in selected
    graphs=sections(graph_case)
    for section in graphs:
        active_refs.update(e['ref'] for e in section['evidence'])
    assessment_keys=set(active_refs)
    for section in graphs:
        assessment_keys.update('edge:'+section['graph']['id']+':'+e['id'] for e in section['graph']['edges'])
    allowed={ref:f for ref,_,_,f in findings(case) if f.get('include_in_report', True)}
    for key in assessment_keys:
        active_refs.update(ref for ref in case.get('investigation', {}).get('assessments', {}).get(key, {}).get('refs', []) if ref in allowed)
    issues=[]
    def add(category, title, detail, url):
        issues.append(dict(category=category,title=title,detail=detail,url=url))
    # Compose checks summary, captures and graph visibility using the same report selections.
    for warning in compose(case)['warnings']:
        add('Report', 'Report preparation', warning, url_for('report_builder.editor',case_id=case['id']))
    for ref in sorted(active_refs):
        finding=allowed.get(ref)
        if finding is None:
            add('Sources','Unavailable evidence','A selected graph refers to a source that is unavailable or excluded.',url_for('report_builder.editor',case_id=case['id']));continue
        label=finding.get('label','Finding'); link=target_url(case,ref)
        if finding.get('verification_status','Unverified')=='Unverified':
            add('Verification',label,'This selected finding is unverified. Review it or explain its limits.',link)
        if finding.get('verification_status')=='False positive':
            add('Verification',label,'A false-positive finding is included. Confirm that the report clearly explains its exclusion.',link)
        if not finding.get('source') and not finding.get('source_url'):
            add('Sources',label,'No source attribution or source URL is recorded.',link)
    for section in graphs:
        for edge in section['graph']['edges']:
            refs=[r for r in edge.get('evidenceRefs',[]) if r in allowed]
            if edge.get('status','hypothesis')=='hypothesis' or not refs:
                add('Connections',edge['label'], 'This connection is a hypothesis.' if edge.get('status','hypothesis')=='hypothesis' else 'This supported connection has no linked case finding.',url_for('case_tools.entities',case_id=case['id']) if case.get('is_demo') else target_url(case,'edge:'+section['graph']['id']+':'+edge['id']))
    for task in case.get('investigation',{}).get('tasks',[]):
        if task['status']!='Complete':
            add('Tasks',task['title'],'This task is '+task['status'].lower()+'.',url_for('investigation.workspace',case_id=case['id'],_anchor='tasks'))
    return issues


@bp.get('/cases/<case_id>/sharing-review')
def review(case_id):
    import app
    case=app.load_case(case_id)
    # The review is an internal workspace, not a redacted document.
    return render_template('sharing_review.html',case=case,issues=sharing_review(case))

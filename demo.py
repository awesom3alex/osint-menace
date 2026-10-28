"""Read-only fictional investigation. No live searches or real personal data."""

DEMO_ID = '00000000-0000-4000-8000-000000000001'
STAMP = '2026-10-27T15:00:00+00:00'


def demo_case():
    from case_graphs import new_graph
    from report_builder import inventory

    records = [
        ('Volunteer directory', 'https://cedartrail.example/volunteers',
         'Volunteer coordinator contact details',
         {'Name': 'Maya Calder', 'Role': 'Volunteer coordinator', 'Organization': 'Cedar Trail Makers',
          'Email': 'maya.calder@cedartrail.example', 'Phone': '+1 202-555-0147', 'Username': 'maya_calder_demo'},
         'Confirmed', 'The fictional directory explicitly lists these contact details. This confirms the contents of the training record, not a real identity.', 'a' * 32),
        ('Demo Social profile', 'https://social.example/maya_calder_demo',
         'Maya Calder social profile',
         {'Display name': 'Maya Calder', 'Username': 'maya_calder_demo', 'Platform': 'Demo Social',
          'Bio': 'Volunteer coordinator at Cedar Trail Makers', 'Website': 'https://cedartrail.example',
          'Public email': 'maya.calder@cedartrail.example'},
         'Confirmed', 'The sample profile and directory share the exact email and organization website. The association is supported within this fictional scenario.', 'b' * 32),
        ('Organization website', 'https://cedartrail.example/about',
         'Organization and website details',
         {'Organization': 'Cedar Trail Makers', 'Domain': 'cedartrail.example', 'Contact email': 'hello@cedartrail.example',
          'Office phone': '+1 202-555-0186', 'Activity': 'Community maker workshops and volunteer events'},
         'Confirmed', 'The fictional about page lists the organization, contact address, and phone. No domain ownership lookup was performed.', None),
        ('Event announcement', 'https://cedartrail.example/events/autumn-workshop',
         'Workshop collaboration',
         {'Event': 'Autumn Workshop', 'Event date': '2026-10-24', 'Coordinator': 'Maya Calder',
          'Workshop lead': 'Theo Bennett', 'Contact email': 'theo.bennett@example.net', 'Username': 'theo_builds_demo'},
         'Confirmed', 'The announcement names both participants in their event roles. It supports a professional collaboration, not a family or personal relationship.', None),
        ('Demo Photo profile', 'https://photos.example/theo_builds_demo',
         'Theo Bennett profile candidate',
         {'Display name': 'Theo Bennett', 'Username': 'theo_builds_demo', 'Platform': 'Demo Photo',
          'Bio': 'Building things and teaching workshops', 'Website': 'https://cedartrail.example/events/autumn-workshop'},
         'Unverified', 'The handle and event link match the announcement, but an independent identifier is still needed before attributing account control to Theo Bennett.', None),
        ('Similar-name profile', 'https://social.example/maya_calder_art_demo',
         'Similar-name profile ruled out',
         {'Display name': 'Maya Calder', 'Username': 'maya_calder_art_demo', 'Contact email': 'maya.art@example.org',
          'Profile context': 'Illustrator; no Cedar Trail Makers reference'},
         'False positive', 'Training brief identifies this as a different fictional person. Keep the record to document why it was ruled out; do not merge it with the coordinator.', None),
    ]
    searches = []
    for index, (source, url, label, value, status, notes, eid) in enumerate(records, 1):
        finding = dict(label=label, value=value, source=source + ' (synthetic)', source_url=url,
                       collected_at=STAMP, verification_status=status, analyst_notes=notes,
                       include_in_report=True, reviewed_at=STAMP)
        if eid:
            finding['evidence'] = [dict(id=eid, caption=source + ' — synthetic training capture', created_at=STAMP)]
        searches.append(dict(id=f'00000000-0000-4000-8000-{index + 100:012d}', created_at=STAMP, search_type='demo:synthetic', query=source,
                             summary=dict(targets=1, findings=1, links=1, notes=1),
                             results=[dict(name=source, module=dict(name='Synthetic training record'), findings=[finding],
                                           links=[dict(label='Fictional source', value=url)],
                                           notes=['Prepared locally for demonstration. No external site was queried.'])]))
    ref = lambda n: f'00000000-0000-4000-8000-{n + 100:012d}:0:0'
    graph = new_graph('Cedar Trail people and account relationships')
    graph['id'] = 'd' * 32
    graph['report'] = dict(include=True)
    graph['legend'] = [dict(type='Person', color='#64b5f6', description='Fictional people named in the source records'),
                       dict(type='Account', color='#ba9cff', description='Synthetic social media accounts'),
                       dict(type='Organization', color='#75d6a0', description='Fictional community organization'),
                       dict(type='Domain/IP', color='#ffcd70', description='Reserved example domain')]
    graph['templates'] = {k: v for k, v in graph['templates'].items() if k in {'Person', 'Account', 'Organization', 'Domain/IP'}}
    def node(id, label, type, x, y, source, fields):
        return dict(id=id, label=label, type=type, position=dict(x=x, y=y), source=ref(source),
                    fields=[dict(name=k, value=v, type='text', options='', visible=False) for k, v in fields.items()])
    graph['nodes'] = [
        node('maya', 'Maya Calder', 'Person', 0, 0, 1, {'Email': 'maya.calder@cedartrail.example', 'Phone': '+1 202-555-0147', 'Role': 'Volunteer coordinator'}),
        node('theo', 'Theo Bennett', 'Person', 0, 450, 4, {'Email': 'theo.bennett@example.net', 'Role': 'Workshop lead'}),
        node('maya_account', '@maya_calder_demo', 'Account', 500, 0, 2, {'Platform': 'Demo Social', 'Profile URL': 'https://social.example/maya_calder_demo'}),
        node('theo_account', '@theo_builds_demo', 'Account', 500, 450, 5, {'Platform': 'Demo Photo', 'Attribution': 'Unverified candidate'}),
        node('organization', 'Cedar Trail Makers', 'Organization', 1000, 0, 3, {'Office phone': '+1 202-555-0186', 'Email': 'hello@cedartrail.example'}),
        node('domain', 'cedartrail.example', 'Domain/IP', 1000, 450, 3, {'Website': 'https://cedartrail.example', 'Domain status': 'Reserved fictional example domain'}),
    ]
    def edge(id, source, target, label, status, evidence, notes):
        return dict(id=id, source=source, target=target, label=label, status=status, date='2026-10-24',
                    evidenceRefs=[ref(evidence)], notes=notes)
    graph['edges'] = [
        edge('e1', 'maya', 'maya_account', 'Associated profile', 'supported', 2, 'Exact email and organization website match in the synthetic records.'),
        edge('e2', 'theo', 'theo_account', 'May operate', 'hypothesis', 5, 'Candidate attribution requires another independent identifier.'),
        edge('e3', 'maya_account', 'organization', 'Names organization', 'supported', 2, 'Organization appears in the profile biography.'),
        edge('e4', 'organization', 'domain', 'Uses website', 'supported', 3, 'Website published in the fictional organization record.'),
        edge('e5', 'theo_account', 'domain', 'Links to event page', 'supported', 5, 'The visible link is supported; account ownership remains unverified.'),
        edge('e6', 'maya', 'theo', 'Workshop collaboration', 'supported', 4, 'The event names Maya as coordinator and Theo as workshop lead.'),
    ]
    case = dict(id=DEMO_ID, name='Demo investigation — Cedar Trail Makers', is_demo=True,
                created_at=STAMP, updated_at=STAMP, searches=searches, graphs=[graph],
                notes='FICTIONAL TRAINING CASE. Every person, account, organization, contact detail, and source record was invented for this demonstration. URLs use reserved example domains. Phone numbers use the fictional 202-555-01xx range. No live searches were run.',
                dossier=dict(subject_name='Maya Calder and Theo Bennett — fictional training subjects',
                             analyst='Morgan Ellis / Training Analyst DEMO-01', reference='TRAINING-CTM-2026-001',
                             aliases='Maya C.; Theo B. (fictional display-name variants)',
                             handles='maya_calder_demo; theo_builds_demo', phones='+1 202-555-0147; +1 202-555-0186',
                             methodology='Review six locally prepared source records. Compare exact identifiers, separate visible links from account attribution, and record a ruled-out similar-name profile.',
                             tasks='Independently corroborate the Theo Bennett account candidate. Record the source and reasoning before changing the assessment.',
                             observations='A shared name alone is insufficient. A visible link confirms that the link appears in a record; it does not establish who controls an account.'),
                summary=dict(searches=6, findings=6, links=6, notes=6))
    case['investigation'] = dict(
        timeline=[dict(id='demo-brief', title='Training brief received', timestamp='2026-10-23T14:00:00+00:00', notes='Scope: connect the supplied workshop records and identify unresolved account attribution.', target=ref(1))],
        tasks=[dict(id='demo-task-1', title='Corroborate Theo account ownership', notes='Find an independent identifier before upgrading attribution.', due='2026-11-03', status='Open', timestamp=STAMP, target='edge:' + graph['id'] + ':e2'),
               dict(id='demo-task-2', title='Document the similar-name exclusion', notes='Recorded the distinct contact email and the training-brief exclusion.', due='2026-10-27', status='Complete', timestamp=STAMP, target=ref(6))],
        assessments={ref(2): dict(confidence='High', reason='The exact email and organization website agree across two supplied synthetic records.', refs=[ref(1), ref(2)]),
                     'edge:' + graph['id'] + ':e2': dict(confidence='Low', reason='A matching handle and event link support a candidate, but do not establish account control.', refs=[ref(4), ref(5)])},
        redaction=dict(enabled=False, terms=[]))
    items = inventory(case)
    graph_id = 'graph:' + graph['id']
    notes = ['notes', 'dossier:Report Details']
    findings = [item['id'] for item in items if item['kind'] == 'finding']
    screenshots = [item['id'] for item in items if item['kind'] == 'screenshot']
    remaining = [item['id'] for item in items if item['id'] not in notes + [graph_id] + findings + screenshots]
    order = notes + [graph_id] + findings + screenshots + remaining
    case['report_builder'] = dict(order=order, selected=notes + [graph_id] + findings + screenshots + ['dossier:Investigative Methodology'],
        summary=dict(purpose='Review the fictional public footprint of Cedar Trail Makers and establish which people, social accounts, and contact details are connected by the supplied training records. No real person or organization was investigated.',
                     findings='Six synthetic records describe two fictional event collaborators, two principal social accounts, one organization, and its website. Four records are marked Confirmed within the training scenario. The Maya Calder account association is supported by an exact email and website match. Theo Bennett account ownership remains unverified, although its link to the event page is visible. A separate similar-name profile was ruled out.',
                     questions='Who controls @theo_builds_demo? An independent identifier or direct corroboration is still needed. The evidence supports a workshop collaboration between Maya and Theo, but does not establish a personal relationship. All assessments apply only to this invented scenario.'))
    return case

"""Optional deployment-local usage measurements, isolated from case content."""
import json
import os
import re

from flask import Response, abort, request, url_for

SCREENS = {
    'index': 'console', 'cases_page': 'cases', 'case_detail': 'case',
    'demo_page': 'demo', 'help_page': 'help', 'osint_links_page': 'catalog',
    'edit_dossier': 'dossier', 'case_graphs.workspace': 'graphs',
    'report_builder.editor': 'report-builder', 'report_builder.preview': 'report-preview',
    'investigation.workspace': 'investigation', 'case_tools.search': 'case-search',
    'case_tools.entities': 'entities', 'case_tools.entity': 'entity',
    'case_tools.review': 'sharing-review', 'workspace.history': 'history',
    'workspace.history_detail': 'history-detail', 'workspace.tools_page': 'tools',
    'workspace.unified': 'unified', 'addons.page': 'addons',
}


def register(app):
    @app.get('/usage-metrics/<screen>')
    def usage_metrics(screen):
        measurement = os.environ.get('GOOGLE_ANALYTICS_ID', '')
        if screen not in SCREENS.values() or not re.fullmatch(r'G-[A-Z0-9]+', measurement):
            abort(404)
        config = dict(apiKey="AIzaSyAf6B4XAhzl5mOZNkV6rONG1AvqheWF1x4",
                      authDomain="osint-menace.firebaseapp.com", projectId="osint-menace",
                      storageBucket="osint-menace.firebasestorage.app", messagingSenderId="234494407000",
                      appId="1:234494407000:web:64ba4cf4629a280842752d", measurementId=measurement)
        payload = json.dumps(dict(firebase=config, screen=screen)).replace('<', '\\u003c')
        response = Response(
            '<!doctype html><html><head><title>OSINT Menace usage</title>'
            '<meta name="referrer" content="no-referrer"></head><body>'
            '<script id="analytics-config" type="application/json">' + payload + '</script>'
            '<script type="module" src="' + url_for('static', filename='firebase-usage.js') + '"></script>'
            '</body></html>', mimetype='text/html')
        response.headers['Cache-Control'] = 'no-store'
        response.headers['Referrer-Policy'] = 'no-referrer'
        return response

    @app.after_request
    def add_usage_frame(response):
        measurement = os.environ.get('GOOGLE_ANALYTICS_ID', '')
        screen = SCREENS.get(request.endpoint)
        if (not re.fullmatch(r'G-[A-Z0-9]+', measurement) or not screen
                or response.status_code != 200 or response.mimetype != 'text/html'
                or response.direct_passthrough):
            return response
        html = response.get_data(as_text=True)
        if '</body>' not in html:
            return response
        frame = url_for('usage_metrics', screen=screen)
        markup = ('<iframe hidden id="usage-analytics-frame" title="Usage analytics" '
                  'referrerpolicy="no-referrer" src="' + frame + '"></iframe>'
                  '<script src="' + url_for('static', filename='usage-actions.js') + '" defer></script>')
        response.set_data(html.replace('</body>', markup + '</body>', 1))
        return response

/* Only fixed action categories cross the analytics boundary; no element text or values. */
(() => {
  const frame = document.getElementById('usage-analytics-frame');
  if (!frame) return;
  let ready = false;
  const pending = [];
  const send = action => {
    const message = {type: 'menace_usage_action', action};
    if (ready) frame.contentWindow.postMessage(message, window.location.origin);
    else if (pending.length < 30) pending.push(message);
  };
  window.addEventListener('message', event => {
    if (event.source !== frame.contentWindow || event.origin !== window.location.origin ||
        event.data?.type !== 'menace_usage_ready') return;
    ready = true;
    pending.splice(0).forEach(message => frame.contentWindow.postMessage(message, window.location.origin));
  });
  const buttons = {preview:'report_save_requested', 'add-object':'graph_object_add_requested', 'add-annotation':'graph_annotation_add_requested',
    connect:'graph_connect_requested', 'group-selected':'graph_group_requested', layout:'graph_layout_requested',
    'save-graph':'graph_save_requested', undo:'graph_undo_requested', redo:'graph_redo_requested',
    'export-json':'graph_export_json_requested', 'export-png':'graph_export_image_requested',
    'download-graph-pdf':'report_export_pdf_requested', 'download-graph-word':'report_export_word_requested',
    'save-view':'graph_view_save_requested', 'apply-view':'graph_view_apply_requested',
    'create-snapshot':'graph_milestone_create_requested', 'restore-snapshot':'graph_milestone_restore_requested'};
  const changes = {'filter-type':'graph_filter_changed', 'filter-status':'graph_filter_changed',
    'timeline-from':'graph_filter_changed', 'timeline-to':'graph_filter_changed',
    'timeline-undated':'graph_filter_changed', 'graph-choice':'graph_selected',
    'include-graph-report':'graph_report_inclusion_changed'};
  const exports = {'report.pdf':'report_export_pdf_requested','report.docx':'report_export_word_requested',
    'report.html':'report_export_html_requested','report.md':'report_export_markdown_requested',
    'export.json':'case_export_json_requested'};
  document.addEventListener('click', event => {
    const control = event.target.closest('button, a');
    if (!control || control.disabled) return;
    if (Object.hasOwn(buttons, control.id)) return send(buttons[control.id]);
    if (control.tagName === 'A') {
      const target = new URL(control.href, window.location.origin);
      if (target.origin !== window.location.origin) return;
      const filename = target.pathname.split('/').pop();
      if (Object.hasOwn(exports, filename)) send(exports[filename]);
    }
  }, true);
  document.addEventListener('change', event => {
    if (Object.hasOwn(changes, event.target.id)) send(changes[event.target.id]);
  }, true);
  document.addEventListener('submit', event => {
    const form = event.target;
    const target = new URL(form.action || window.location.href, window.location.origin);
    if (target.origin !== window.location.origin) return;
    const path = target.pathname;
    const forms = {'addon-form':'addon_search_requested', 'unified-form':'unified_search_requested', builder:'report_save_requested'};
    if (Object.hasOwn(forms, form.id)) return send(forms[form.id]);
    if (form.matches('.search-form')) return send('search_requested');
    const routes = [ [/^\/cases$/, 'case_create_requested'], [/^\/cases\/[^/]+\/search$/, 'case_search_requested'],
      [/^\/cases\/[^/]+\/graphs$/, 'graph_create_requested'],
      [/^\/cases\/[^/]+\/report-builder$/, 'report_save_requested'],
      [/^\/cases\/[^/]+\/investigation\//, 'investigation_update_requested'],
      [/^\/cases\/[^/]+\/dossier$/, 'dossier_save_requested'],
      [/^\/cases\/[^/]+\/evidence\//, 'evidence_upload_requested'],
      [/^\/addons\/launch$/, 'addon_search_requested'], [/^\/unified\/launch$/, 'unified_search_requested'] ];
    const route = routes.find(([pattern]) => pattern.test(path));
    if (route) send(route[1]);
  }, true);
})();

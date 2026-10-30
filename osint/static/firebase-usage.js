import {initializeApp} from 'https://www.gstatic.com/firebasejs/13.1.0/firebase-app.js';
import {initializeAnalytics, getAnalytics, isSupported, logEvent, setConsent} from 'https://www.gstatic.com/firebasejs/13.1.0/firebase-analytics.js';

// The tag runs only in a document with a generic URL/title and no investigation UI.
(async () => {
  const {firebase, screen} = JSON.parse(document.getElementById('analytics-config').textContent);
  const safePage = {page_location: `https://osint-menace.invalid/screens/${screen}`,
    page_title: `OSINT Menace: ${screen}`, page_referrer: ''};
  try {
    if (!await isSupported()) return;
    window.dataLayer = window.dataLayer || [];
    window.gtag = function () { window.dataLayer.push(arguments); };
    window.gtag('consent', 'default', {analytics_storage: 'granted', ad_storage: 'denied',
      ad_user_data: 'denied', ad_personalization: 'denied'});
    window.gtag('set', safePage);
    const app = initializeApp(firebase);
    initializeAnalytics(app, {config: {...safePage, send_page_view: false,
      allow_google_signals: false, allow_ad_personalization_signals: false}});
    const analytics = getAnalytics(app);
    setConsent({analytics_storage: 'granted', ad_storage: 'denied',
      ad_user_data: 'denied', ad_personalization: 'denied'});
    logEvent(analytics, 'page_view', {...safePage, screen_name: screen});
    const actions = new Set(['search_requested', 'case_create_requested', 'case_search_requested',
      'graph_create_requested', 'graph_object_add_requested', 'graph_annotation_add_requested',
      'graph_connect_requested', 'graph_group_requested', 'graph_layout_requested',
      'graph_save_requested', 'graph_undo_requested', 'graph_redo_requested',
      'graph_export_json_requested', 'graph_export_image_requested', 'report_export_pdf_requested',
      'report_export_word_requested', 'report_export_html_requested', 'report_export_markdown_requested',
      'case_export_json_requested', 'graph_view_save_requested', 'graph_view_apply_requested',
      'graph_milestone_create_requested', 'graph_milestone_restore_requested',
      'graph_filter_changed', 'graph_selected', 'graph_report_inclusion_changed',
      'report_save_requested', 'investigation_update_requested', 'addon_search_requested',
      'unified_search_requested', 'dossier_save_requested', 'evidence_upload_requested']);
    window.addEventListener('message', event => {
      if (event.source !== window.parent || event.origin !== window.location.origin) return;
      const data = event.data;
      if (data?.type !== 'menace_usage_action' || !actions.has(data.action)) return;
      logEvent(analytics, 'feature_action', {...safePage, screen_name: screen, action_id: data.action});
    });
    window.parent.postMessage({type: 'menace_usage_ready'}, window.location.origin);
  } catch (_) {
    // Offline or blocked analytics must never interfere with investigations.
  }
})();

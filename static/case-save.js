// Save case changes in place, preserving scroll position and unrelated review forms.
(() => {
  const formSelector = [
    '.add-case-form', '.link-case-form', '#save-result', '.review-form',
    '.case-notes-form', '.evidence-form', '.tool-check-form', '.merge-form',
    '.evidence-check-form',
  ].join(', ');
  const status = document.getElementById('case-save-status') || document.createElement('div');
  const pending = new WeakSet();
  let hideTimer;

  status.className = 'case-save-toast';
  status.setAttribute('role', 'status');
  status.setAttribute('aria-live', 'polite');
  status.hidden = true;
  if (!status.isConnected) document.body.appendChild(status);

  function showStatus(message, isError = false) {
    status.textContent = message;
    status.dataset.error = String(isError);
    status.hidden = false;
    clearTimeout(hideTimer);
    hideTimer = setTimeout(() => { status.hidden = true; }, 4500);
  }

  function appendEvidence(form, evidence) {
    const gallery = form.closest('.result-card')?.querySelector('.evidence-gallery');
    if (!gallery) return;
    const figure = document.createElement('figure');
    const image = document.createElement('img');
    const caption = document.createElement('figcaption');
    image.src = evidence.url;
    image.alt = evidence.caption || 'Screenshot evidence';
    caption.textContent = `${evidence.caption} · ${evidence.created_at} · SHA-256: ${evidence.sha256}`;
    caption.className = 'evidence-provenance';
    figure.append(image, caption);
    gallery.append(figure);
    form.reset();
  }

  async function refreshCasePanels(form, payload) {
    const response = await fetch(location.pathname);
    if (!response.ok) throw new Error('Case display unavailable');
    const doc = new DOMParser().parseFromString(await response.text(), 'text/html');
    for (const id of ['case-activity', 'duplicate-review']) {
      const current = document.getElementById(id);
      const incoming = doc.getElementById(id);
      if (!current || !incoming) continue;
      const opened = [...current.querySelectorAll('details')].map(details => details.open);
      incoming.querySelectorAll('details').forEach((details, index) => {
        details.open = opened[index] || false;
      });
      current.replaceWith(incoming);
    }
    if (!form.matches('.merge-form')) return;
    const currentFindings = new Map(
      [...document.querySelectorAll('[data-finding-ref]')].map(node => [node.dataset.findingRef, node]),
    );
    for (const incoming of doc.querySelectorAll('[data-finding-ref]')) {
      if (payload.changed_refs?.includes(incoming.dataset.findingRef)) {
        currentFindings.get(incoming.dataset.findingRef)?.replaceWith(incoming);
      }
    }
  }

  document.addEventListener('submit', async event => {
    const form = event.target;
    if (!form.matches(formSelector)) return;
    event.preventDefault();
    if (pending.has(form)) return;
    pending.add(form);

    const button = form.querySelector('button[type="submit"]');
    const originalText = button?.textContent;
    if (button) {
      button.style.minWidth = `${button.getBoundingClientRect().width}px`;
      button.disabled = true;
      button.textContent = form.matches('.evidence-check-form') ? 'Checking…' : 'Saving…';
    }
    try {
      const response = await fetch(form.action, {
        method: 'POST',
        body: new FormData(form),
        headers: {'X-Requested-With': 'fetch'},
      });
      const payload = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(payload.error || 'Save failed. Please try again.');
      let message = payload.message || 'Added to case.';
      if (button) button.textContent = form.matches('.evidence-check-form') ? 'Verified' : 'Saved';
      if (payload.evidence) appendEvidence(form, payload.evidence);
      if (form.matches('.review-form, .case-notes-form, .evidence-form, .merge-form')) {
        try {
          await refreshCasePanels(form, payload);
        } catch {
          // The mutation succeeded; a failed follow-up read must not invite duplicate submissions.
          message += ' Refresh the page to update the case display.';
        }
      }
      if (form.matches('.tool-check-form')) {
        const card = form.closest('.results');
        card.querySelector('[data-startup-check]').textContent = payload.startup_check;
        card.querySelector('[data-checked-at]').textContent = payload.checked_at;
      }
      showStatus(message);
    } catch (error) {
      showStatus(error.message || 'Could not save. Please try again.', true);
    } finally {
      setTimeout(() => {
        if (button) {
          button.disabled = false;
          button.textContent = originalText;
        }
        pending.delete(form);
      }, 1200);
    }
  });
})();

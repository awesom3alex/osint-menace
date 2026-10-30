/* Checks only release metadata; never sends investigation content. */
(async () => {
  const panel = document.getElementById('release-update');
  if (!panel) return;
  try {
    const response = await fetch('/api/updates', {cache: 'no-store', signal: AbortSignal.timeout(7000)});
    if (!response.ok) return;
    const data = await response.json();
    if (!data.available || !/^\d+\.\d+\.\d+$/.test(data.latest?.version)) return;
    const key = 'menace-dismiss-update';
    try { if (localStorage.getItem(key) === data.latest.version) return; } catch (_) {}
    const link = new URL(data.latest.url);
    if (link.origin !== 'https://github.com' || !link.pathname.startsWith('/awesom3alex/osint-menace/releases/tag/')) return;
    document.getElementById('release-update-title').textContent = `OSINT Menace v${data.latest.version} is available`;
    document.getElementById('release-update-link').href = link.href;
    panel.hidden = false;
    document.getElementById('release-update-dismiss').addEventListener('click', () => {
      panel.hidden = true;
      try { localStorage.setItem(key, data.latest.version); } catch (_) {}
    });
  } catch (_) { /* Offline and rate-limited checks must not interrupt research. */ }
})();

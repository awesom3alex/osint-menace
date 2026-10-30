(() => {
  const form = document.querySelector('#builder');
  const list = document.querySelector('#report-items');
  const status = document.querySelector('#builder-status');
  let busy = false;
  let dirty = false;
  const changed = () => {dirty = true; status.textContent = 'Unsaved changes.';};
  const rows = () => [...list.querySelectorAll('li[data-id]')];
  const boundaries = () => rows().forEach((row, index, all) => {
    row.querySelector('[data-move="-1"]').disabled = index === 0;
    row.querySelector('[data-move="1"]').disabled = index === all.length - 1;
  });
  boundaries();
  form.addEventListener('input', changed);
  list.addEventListener('click', event => {
    const button = event.target.closest('[data-move]');
    if (!button || busy) return;
    const row = button.closest('li');
    if (button.dataset.move === '-1' && row.previousElementSibling) list.insertBefore(row, row.previousElementSibling);
    else if (button.dataset.move === '1' && row.nextElementSibling) list.insertBefore(row.nextElementSibling, row);
    changed(); boundaries(); button.focus();
  });
  for (const [id, checked] of [['select-all', true], ['select-none', false]]) {
    document.getElementById(id).addEventListener('click', () => {
      rows().forEach(row => {row.querySelector('input').checked = checked;}); changed();
    });
  }
  async function save(preview) {
    if (busy) return;
    busy = true;
    const summary = Object.fromEntries(['purpose', 'findings', 'questions'].map(key => [key, form.elements[key].value]));
    const payload = {updated_at: form.dataset.version, summary, order: rows().map(row => row.dataset.id), selected: rows().filter(row => row.querySelector('input').checked).map(row => row.dataset.id)};
    const controls = [...form.querySelectorAll('input, textarea, button')];
    controls.forEach(control => {control.disabled = true;});
    status.textContent = 'Saving report…';
    try {
      const response = await fetch(form.dataset.save, {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(payload)});
      const data = await response.json();
      if (!response.ok) throw new Error(data.error || 'Unable to save the report.');
      form.dataset.version = data.updated_at; dirty = false; status.textContent = 'Report saved.';
      if (preview) window.location.assign(form.dataset.preview);
    } catch (error) {status.textContent = error.message;}
    finally {busy = false; controls.forEach(control => {control.disabled = false;}); boundaries();}
  }
  form.addEventListener('submit', event => {event.preventDefault(); save(false);});
  document.querySelector('#preview').addEventListener('click', () => save(true));
  window.addEventListener('beforeunload', event => {if (dirty) {event.preventDefault(); event.returnValue = '';}});
})();

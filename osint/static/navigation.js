/* Native disclosure menus retain keyboard and no-JavaScript navigation. */
(() => {
  const menus = [...document.querySelectorAll('[data-nav-menu]')];
  menus.forEach(menu => {
    menu.addEventListener('toggle', () => {
      if (menu.open) menus.forEach(other => { if (other !== menu) other.open = false; });
    });
    menu.addEventListener('click', event => {
      if (event.target.closest('a') || (event.target.closest('button') && !event.target.closest('form'))) menu.open = false;
    });
  });
  document.addEventListener('pointerdown', event => {
    menus.forEach(menu => { if (!menu.contains(event.target)) menu.open = false; });
  });
  document.addEventListener('keydown', event => {
    if (event.key !== 'Escape') return;
    const open = menus.find(menu => menu.open);
    if (open) { open.open = false; open.querySelector('summary').focus(); }
  });
})();

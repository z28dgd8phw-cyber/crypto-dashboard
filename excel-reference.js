'use strict';
document.querySelectorAll('.excel-example').forEach(container => {
  const tabs = [...container.querySelectorAll('[role="tab"]')];
  const activate = tab => {
    tabs.forEach(other => {
      const selected = other === tab;
      other.setAttribute('aria-selected', String(selected));
      other.tabIndex = selected ? 0 : -1;
      container.querySelector('#' + other.getAttribute('aria-controls')).hidden = !selected;
    });
  };
  tabs.forEach((tab, index) => {
    tab.addEventListener('click', () => activate(tab));
    tab.addEventListener('keydown', event => {
      const next = event.key === 'ArrowRight' ? (index + 1) % tabs.length : event.key === 'ArrowLeft' ? (index + tabs.length - 1) % tabs.length : event.key === 'Home' ? 0 : event.key === 'End' ? tabs.length - 1 : null;
      if (next !== null) { event.preventDefault(); activate(tabs[next]); tabs[next].focus(); }
    });
  });
});

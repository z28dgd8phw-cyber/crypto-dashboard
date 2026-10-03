'use strict';
const filters = document.querySelectorAll('.journal-filters button');
const records = document.querySelectorAll('.journal-table tbody tr');
filters.forEach(button => button.addEventListener('click', () => {
  filters.forEach(other => other.setAttribute('aria-pressed', String(other === button)));
  let count = 0;
  records.forEach(row => {
    row.hidden = button.dataset.coin !== 'Alle' && row.dataset.coin !== button.dataset.coin;
    if (!row.hidden) count += 1;
  });
  document.getElementById('journal-status').textContent = `${count} ${count === 1 ? 'Eintrag' : 'Einträge'} · ${button.dataset.coin}`;
}));

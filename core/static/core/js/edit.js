/* Loaded only for the logged-in owner while edit mode is on. Every save is checked again on the server. */
(() => {
const $ = (s, r = document) => r.querySelector(s), $$ = (s, r = document) => [...r.querySelectorAll(s)];
const csrf = $('meta[name=csrf]')?.content || '';
const toast = m => window.siteToast && window.siteToast(m);
const pendingSaves = new Set();

async function api(path, data) {
  const task = (async () => {
    try {
      const r = await fetch('/api/' + path + '/', {
        method: 'POST', credentials: 'same-origin',
        headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrf },
        body: JSON.stringify(data || {}),
      });
      const j = await r.json().catch(() => ({}));
      if (!r.ok || !j.ok) { toast(j.error || 'Could not save. Please try again.'); return null; }
      return j;
    } catch (e) { toast('You appear to be offline. Not saved.'); return null; }
  })();
  pendingSaves.add(task);
  try { return await task; } finally { pendingSaves.delete(task); }
}

// ---- editable text: saves when you click away
$$('[data-key]').forEach(el => {
  el.contentEditable = 'true'; el.spellcheck = true;
  const block = !/^(P|DIV)$/.test(el.tagName);
  let before = el.textContent;
  el.addEventListener('focus', () => { before = el.textContent; });
  el.addEventListener('keydown', e => { if (e.key === 'Enter' && block) { e.preventDefault(); el.blur(); } });
  el.addEventListener('paste', e => { e.preventDefault(); document.execCommand('insertText', false, (e.clipboardData || window.clipboardData).getData('text/plain')); });
  el.addEventListener('blur', async () => {
    const v = el.textContent.trim();
    if (v === before.trim()) return;
    const task = (async () => {
      const j = await api('text', { key: el.dataset.key, value: v });
      if (j) { before = v; toast('Saved'); return true; }
      el.textContent = before;
      return false;
    })();
    pendingSaves.add(task);
    try { await task; } finally { pendingSaves.delete(task); }
  });
});
$$('form[action$="/owner/edit/"]').forEach(form => form.addEventListener('submit', async e => {
  if (form.dataset.flushReady) return;
  e.preventDefault();
  const submitter = e.submitter;
  if (submitter) {
    submitter.disabled = true;
    submitter.dataset.originalLabel = submitter.textContent;
    submitter.textContent = 'Saving…';
  }
  const results = await Promise.all([...pendingSaves]);
  if (results.includes(false)) {
    if (submitter) {
      submitter.disabled = false;
      submitter.textContent = submitter.dataset.originalLabel;
    }
    return;
  }
  if (submitter) {
    submitter.disabled = false;
    submitter.textContent = submitter.dataset.originalLabel;
  }
  form.dataset.flushReady = '1';
  if (submitter) form.requestSubmit(submitter);
  else form.requestSubmit();
}));
// Links remain usable in edit mode; Alt-click edits their label instead.
$$('[data-key]').forEach(el => {
  if (el.closest('a')) el.title = 'Click to follow this link. Alt-click to edit its text.';
});
document.addEventListener('click', e => {
  const el = e.target.closest('[data-key]');
  if (!el || !el.closest('a') || !e.altKey) return;
  e.preventDefault();
  el.focus();
  const range = document.createRange();
  range.selectNodeContents(el);
  const selection = window.getSelection();
  selection.removeAllRanges();
  selection.addRange(range);
});
document.addEventListener('click', e => { if (e.target.closest('[data-social-empty]')) e.preventDefault(); });

// ---- show / hide switches on every element
$$('[data-vis]').forEach(el => {
  const b = document.createElement('button');
  b.type = 'button'; b.className = 'eye'; b.setAttribute('aria-label', 'Show or hide');
  b.title = 'Show or hide';
  b.innerHTML = '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M2 12s4-7 10-7 10 7 10 7-4 7-10 7S2 12 2 12z"/><circle cx="12" cy="12" r="3"/></svg>';
  b.addEventListener('click', async ev => {
    ev.preventDefault(); ev.stopPropagation();
    const nowVisible = el.classList.contains('off');
    const j = await api('vis', { key: el.dataset.vis, visible: nowVisible });
    if (j) { el.classList.toggle('off', !j.visible); toast(j.visible ? 'Shown' : 'Hidden from visitors'); }
  });
  el.appendChild(b);
});
let controlsTimer;
document.addEventListener('pointerdown', e => {
  if (e.pointerType !== 'touch') return;
  if (e.target.closest('.eye,.picbtn,input,button')) return;
  if (e.target.closest('a,select,textarea,label')) return;
  const el = e.target.closest('[data-vis],[data-sec]');
  if (!el) return;
  e.preventDefault();
  $$('.controls-open').forEach(x => x.classList.remove('controls-open'));
  el.classList.add('controls-open');
  el.querySelectorAll('[data-img]').forEach(x => x.classList.add('controls-open'));
  clearTimeout(controlsTimer);
  controlsTimer = setTimeout(() => {
    el.classList.remove('controls-open');
    el.querySelectorAll('.controls-open').forEach(x => x.classList.remove('controls-open'));
  }, 5000);
});

// ---- sections: move up / down / on-off
$$('[data-sec]').forEach(el => {
  const id = el.dataset.sec, bar = document.createElement('div');
  bar.className = 'sbar glass';
  bar.innerHTML = `<b>${id}</b><button type="button" data-a="up" aria-label="Move up">↑</button><button type="button" data-a="down" aria-label="Move down">↓</button><button type="button" data-a="toggle" aria-label="Show or hide section">👁</button>`;
  bar.addEventListener('click', async e => {
    const b = e.target.closest('button'); if (!b) return;
    if (await api('section', { id, action: b.dataset.a })) location.reload();
  });
  el.prepend(bar);
});

// ---- release playlist order
const reorderList = $('[data-reorder-list="catalog"]');
if (reorderList) {
  const rows = () => [...reorderList.children].filter(row => $('[data-order-id]', row));
  const ids = () => rows().map(row => Number($('[data-order-id]', row).dataset.orderId));
  let draggedRow = null, startOrder = "";

  const saveOrder = async () => {
    const result = await api('item-order', { kind: 'catalog', ids: ids() });
    if (!result) { location.reload(); return; }
    toast('Release order saved');
    $('.rc', rows()[0])?.click();
  };

  const moveRow = (row, direction) => {
    const orderedRows = rows(), index = orderedRows.indexOf(row);
    const target = orderedRows[index + direction];
    if (!target) return false;
    reorderList.insertBefore(row, direction < 0 ? target : target.nextSibling);
    return true;
  };

  reorderList.addEventListener('click', async e => {
    const button = e.target.closest('[data-order-move]');
    if (!button) return;
    e.preventDefault();
    e.stopPropagation();
    if (moveRow(button.closest('.rail-item'), Number(button.dataset.orderMove))) await saveOrder();
  });
  reorderList.addEventListener('keydown', async e => {
    if (!e.target.matches('[data-order-id]') || !['ArrowUp', 'ArrowDown'].includes(e.key)) return;
    e.preventDefault();
    if (moveRow(e.target.closest('.rail-item'), e.key === 'ArrowUp' ? -1 : 1)) await saveOrder();
  });
  reorderList.addEventListener('dragstart', e => {
    const item = e.target.closest('[data-order-id]');
    if (!item) return;
    draggedRow = item.closest('.rail-item');
    startOrder = JSON.stringify(ids());
    draggedRow.classList.add('reordering');
    e.dataTransfer.effectAllowed = 'move';
    e.dataTransfer.setData('text/plain', item.dataset.orderId);
  });
  reorderList.addEventListener('dragover', e => {
    if (!draggedRow) return;
    const item = e.target.closest('[data-order-id]');
    const target = item?.closest('.rail-item');
    if (!target || target === draggedRow) return;
    e.preventDefault();
    const before = e.clientX < target.getBoundingClientRect().left + target.offsetWidth / 2;
    reorderList.insertBefore(draggedRow, before ? target : target.nextSibling);
  });
  reorderList.addEventListener('dragend', async () => {
    draggedRow?.classList.remove('reordering');
    draggedRow = null;
    if (startOrder && JSON.stringify(ids()) !== startOrder) await saveOrder();
    startOrder = "";
  });
}

// ---- replaceable images
$$('[data-img]').forEach(el => {
  const slot = el.dataset.img, l = document.createElement('label');
  l.className = 'picbtn'; l.textContent = 'Change image';
  const inp = document.createElement('input'); inp.type = 'file'; inp.accept = 'image/*'; inp.hidden = true;
  inp.addEventListener('change', async () => {
    const f = inp.files[0]; if (!f) return;
    const fd = new FormData(); fd.append('slot', slot); fd.append('file', f);
    toast('Uploading…');
    try {
      const r = await fetch('/api/image/', { method: 'POST', credentials: 'same-origin', headers: { 'X-CSRFToken': csrf }, body: fd });
      const j = await r.json().catch(() => ({}));
      if (r.ok && j.ok) location.reload(); else toast(j.error || 'Upload failed.');
    } catch (e) { toast('Upload failed. Check your connection.'); }
  });
  l.appendChild(inp); el.appendChild(l);
});

// ---- item cards: show / hide
document.addEventListener('click', async e => {
  const b = e.target.closest('[data-item-toggle]'); if (!b) return;
  e.preventDefault();
  const j = await api('item', { id: +b.dataset.itemToggle });
  if (j) { b.closest('.cw').querySelector('.card').classList.toggle('off', !j.published); toast(j.published ? 'Visible' : 'Hidden from visitors'); }
});

// ---- site panel: type, theme, sections
const panel = $('#sitepanel'), btn = $('#sitebtn');
if (btn && panel) btn.addEventListener('click', () => {
  panel.hidden = !panel.hidden; btn.setAttribute('aria-expanded', String(!panel.hidden));
});
panel?.addEventListener('click', async e => {
  const t = e.target.closest('[data-preset],[data-theme-set],[data-sec-toggle]'); if (!t) return;
  let ok;
  if (t.dataset.preset) {
    if (!confirm('Switch the site type? The look, labels and sections change. Your items, orders and images stay.')) return;
    ok = await api('preset', { type: t.dataset.preset });
  } else if (t.dataset.themeSet) ok = await api('theme', { theme: t.dataset.themeSet });
  else ok = await api('section', { id: t.dataset.secToggle, action: 'toggle' });
  if (ok) location.reload();
});
})();

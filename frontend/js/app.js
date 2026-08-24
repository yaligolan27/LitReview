/* App shell: hash router, topbar (crumb / global search / operator),
 * flow stepper, toast — plus small helpers shared by the screen modules. */

import { api, getOperator, setOperator } from './api.js';
import * as dashboard from './screens/dashboard.js';
import * as brief from './screens/brief.js';
import * as toc from './screens/toc.js';
import * as sources from './screens/sources.js';
import * as pipeline from './screens/pipeline.js';
import * as draft from './screens/draft.js';
import * as exportScreen from './screens/export.js';

/* ================= shared helpers (imported by screens) ================= */

export function esc(value) {
  return String(value ?? '').replace(/[&<>"']/g, (c) => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
  }[c]));
}

export function debounce(fn, ms) {
  let timer = null;
  const wrapped = (...args) => {
    clearTimeout(timer);
    timer = setTimeout(() => fn(...args), ms);
  };
  wrapped.cancel = () => clearTimeout(timer);
  return wrapped;
}

/* ISO timestamp → "14.5.26" like the mockup cards. */
export function fmtDate(iso) {
  if (!iso) return '';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return '';
  return `${d.getDate()}.${d.getMonth() + 1}.${String(d.getFullYear()).slice(2)}`;
}

export function fmtBytes(n) {
  if (!n && n !== 0) return '';
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(0)} KB`;
  return `${(n / (1024 * 1024)).toFixed(1)} MB`;
}

/* confidence helpers — HIGH/MODERATE/LIMITED/EMERGING */
export const CONF_ORDER = ['HIGH', 'MODERATE', 'LIMITED', 'EMERGING'];
const CONF_META = {
  HIGH: { cls: 'high', color: '#2e7d32' },
  MODERATE: { cls: 'mod', color: '#1565c0' },
  LIMITED: { cls: 'lim', color: '#e65100' },
  EMERGING: { cls: 'emg', color: '#c62828' },
};
export function confCls(v) { return (CONF_META[String(v || '').toUpperCase()] || {}).cls || ''; }
export function confColor(v) { return (CONF_META[String(v || '').toUpperCase()] || {}).color || '#9aa0b4'; }

/* Backend overrides may arrive as a plain value or {value, by, at, reason}. */
export function ovValue(ov) {
  if (!ov) return '';
  return typeof ov === 'object' ? String(ov.value || '') : String(ov);
}

/* survey status → dashboard badge + best screen to open */
export const STATUS_META = {
  brief:           { label: '✎ הגדרה',          cls: 'stage',      screen: 'brief' },
  toc_pending:     { label: '☰ תוכן עניינים',   cls: 'stage',      screen: 'toc' },
  collecting:      { label: '🔍 איסוף מקורות',  cls: 'stage run',  screen: 'sources' },
  sources_pending: { label: '📚 אישור מקורות',  cls: 'stage',      screen: 'sources' },
  writing:         { label: '✍ בכתיבה',         cls: 'stage run',  screen: 'pipeline' },
  draft_pending:   { label: '✐ אישור טיוטה',    cls: 'stage',      screen: 'draft' },
  finalizing:      { label: '⚙ הפקה',           cls: 'stage run',  screen: 'pipeline' },
  done:            { label: '✓ הושלם',          cls: 'stage done', screen: 'export' },
  failed:          { label: '✗ נכשל',           cls: 'stage fail', screen: 'pipeline' },
  archived:        { label: '🗂 בארכיון',       cls: 'stage wait', screen: 'export' },
};
export function statusScreen(status) {
  return (STATUS_META[status] || {}).screen || 'brief';
}

/* ================= toast ================= */

let toastTimer = null;
export function toast(msg, icon = '✓') {
  const el = document.getElementById('toast');
  document.getElementById('toastIcon').textContent = icon;
  document.getElementById('toastMsg').textContent = msg;
  el.classList.add('show');
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => el.classList.remove('show'), 2600);
}
window.toast = toast;

/* ================= router ================= */

const SCREENS = {
  dashboard, brief, toc, sources, pipeline, draft, export: exportScreen,
};

const CRUMBS = {
  dashboard: ['דשבורד', '— כל הסקרים'],
  brief: ['הגדרת סקר', '— סוכן 1'],
  toc: ['תוכן עניינים', '— סוכן 2 · נקודת אישור'],
  sources: ['מקורות', '— סוכנים 3–4 · נקודת אישור'],
  pipeline: ['ריצת המערכת', '— סוכנים 5–11'],
  draft: ['עריכת טיוטה', '— סוכנים 5–6 · נקודת אישור'],
  export: ['ייצוא', '— סוכנים 7–11'],
};

const FLOW = [
  { id: 'brief', n: 'הגדרה' },
  { id: 'toc', n: 'תוכן עניינים', gate: true },
  { id: 'sources', n: 'מקורות', gate: true },
  { id: 'pipeline', n: 'ריצה' },
  { id: 'draft', n: 'טיוטה', gate: true },
  { id: 'export', n: 'ייצוא' },
];

/* How far along the flow each survey status is (index of first not-done step). */
const STATUS_STEP = {
  brief: 0, toc_pending: 1, collecting: 2, sources_pending: 2, writing: 3,
  draft_pending: 4, finalizing: 5, done: 6, failed: 3, archived: 6,
};

let currentSid = '';
let cleanup = null;
let routeToken = 0;

export function navigate(hash) {
  if (location.hash === hash) route();
  else location.hash = hash;
}

function parseHash() {
  const parts = (location.hash || '').replace(/^#\/?/, '').split('/').filter(Boolean);
  if (parts[0] === 's' && parts[1]) {
    const screen = (parts[2] && parts[2] !== 'dashboard' && SCREENS[parts[2]]) ? parts[2] : 'brief';
    return { sid: decodeURIComponent(parts[1]), screen };
  }
  return { sid: '', screen: 'dashboard' };
}

function renderFlow(host, screen, card) {
  if (screen === 'dashboard') { host.innerHTML = ''; return; }
  const progressIdx = card ? (STATUS_STEP[card.status] ?? 0) : -1;
  const curIdx = FLOW.findIndex((f) => f.id === screen);
  let html = '<div class="flow">';
  FLOW.forEach((f, i) => {
    const done = progressIdx >= 0 && i < progressIdx;
    const active = i === curIdx;
    const cls = active ? 'active' : (done ? 'done' : '');
    html += `<div class="step ${cls}" data-step="${f.id}">
      <div class="dot">${done && !active ? '✓' : i + 1}</div>
      <div class="lbl">${esc(f.n)}${f.gate ? ' <span class="gate">אישור</span>' : ''}</div>
    </div>`;
    if (i < FLOW.length - 1) html += '<div class="arrow"></div>';
  });
  host.innerHTML = html + '</div>';
  host.querySelectorAll('.step').forEach((step) => {
    step.addEventListener('click', () => navigate(`#/s/${currentSid}/${step.dataset.step}`));
  });
}

async function route() {
  const token = ++routeToken;
  const { sid, screen } = parseHash();

  if (typeof cleanup === 'function') { try { cleanup(); } catch { /* noop */ } }
  cleanup = null;
  currentSid = sid;

  document.querySelectorAll('.rail .nav-ico').forEach((b) => {
    b.classList.toggle('active', b.dataset.nav === screen);
  });
  document.getElementById('globalSearch').classList.toggle('hidden', screen !== 'dashboard');

  /* survey card feeds both the crumb subtitle and the flow stepper */
  let card = null;
  if (sid) {
    try { card = await api.get(`/surveys/${sid}`); } catch { /* render without it */ }
    if (token !== routeToken) return;
  }

  const crumb = CRUMBS[screen] || [screen, ''];
  const sub = (sid && card && card.topic) ? `— ${card.topic}` : crumb[1];
  document.getElementById('crumb').innerHTML = `${esc(crumb[0])} <small>${esc(sub)}</small>`;

  renderFlow(document.getElementById('flow'), screen, card);

  const host = document.getElementById('screen');
  host.innerHTML = '';
  const view = document.createElement('div');
  view.className = 'screen-view';
  host.appendChild(view);

  const mod = SCREENS[screen] || SCREENS.dashboard;
  try {
    const ret = await mod.render(view, { sid, navigate, toast, card });
    if (token !== routeToken) {
      if (typeof ret === 'function') { try { ret(); } catch { /* noop */ } }
      return;
    }
    if (typeof ret === 'function') cleanup = ret;
  } catch (err) {
    console.error(err);
    if (token === routeToken) {
      view.innerHTML = `<div class="card empty">
        <div class="e-ico">⚠️</div>
        <h3>שגיאה בטעינת המסך</h3>
        <p>${esc((err && err.detail) || 'שגיאה לא צפויה')}</p>
        <div class="e-actions"><button class="btn" id="retryBtn">נסה שוב</button></div>
      </div>`;
      view.querySelector('#retryBtn').addEventListener('click', () => route());
    }
  }
  window.scrollTo({ top: 0 });
}

/* ================= topbar: rail, search, operator ================= */

function initRail() {
  document.querySelectorAll('.rail .nav-ico').forEach((btn) => {
    btn.addEventListener('click', () => {
      const target = btn.dataset.nav;
      if (target === 'dashboard') { navigate('#/dashboard'); return; }
      if (!currentSid) { toast('בחר סקר מהדשבורד תחילה', 'ℹ'); return; }
      navigate(`#/s/${currentSid}/${target}`);
    });
  });
}

function initGlobalSearch() {
  const input = document.getElementById('globalSearchInput');
  input.addEventListener('input', () => {
    window.dispatchEvent(new CustomEvent('litreview:search', { detail: input.value }));
  });
}

const NEW_OP = '__new__';

function normalizeOperators(res) {
  const raw = Array.isArray(res) ? res : (res && (res.operators || res.names)) || [];
  return raw.map((o) => (typeof o === 'string' ? o : (o && o.name) || '')).filter(Boolean);
}

function renderOperatorOptions(names, selected) {
  const sel = document.getElementById('opSelect');
  let html = '';
  if (!selected) html += '<option value="">בחר מפעיל…</option>';
  html += names.map((n) => `<option value="${esc(n)}">${esc(n)}</option>`).join('');
  html += `<option value="${NEW_OP}">+ מפעיל חדש</option>`;
  sel.innerHTML = html;
  sel.value = selected || '';
  document.getElementById('opAv').textContent = selected ? selected.trim().charAt(0) : '?';
}

async function initOperator() {
  const sel = document.getElementById('opSelect');
  let names = [];
  try { names = normalizeOperators(await api.get('/operators')); } catch { /* offline */ }
  const current = getOperator();
  if (current && !names.includes(current)) names.unshift(current);
  renderOperatorOptions(names, current);

  sel.addEventListener('change', async () => {
    if (sel.value === NEW_OP) {
      const name = (prompt('שם המפעיל החדש:') || '').trim();
      if (name) {
        try { await api.post('/operators', { name }); } catch (err) { toast(err.detail || 'שמירת המפעיל נכשלה', '⚠'); }
        if (!names.includes(name)) names.push(name);
        setOperator(name);
        toast(`המפעיל ${name} נוסף ונבחר`);
      }
      renderOperatorOptions(names, getOperator());
      return;
    }
    setOperator(sel.value);
    renderOperatorOptions(names, sel.value);
  });
}

/* ================= boot ================= */

window.addEventListener('hashchange', route);
initRail();
initGlobalSearch();
initOperator();
if (!location.hash) location.hash = '#/dashboard';
route();

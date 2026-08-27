/* Screen 4 — sources review + approval gate: table of found papers,
 * include/exclude staging (PATCH overlay), manual add, "search more"
 * background job with SSE progress, approve → start writing run. */

import { api } from '../api.js';
import { subscribe } from '../sse.js';
import { esc, debounce, confCls } from '../app.js';

const LANG_SHORT = {
  english: 'EN', hebrew: 'HE', 'עברית': 'HE', german: 'DE', russian: 'RU',
  spanish: 'ES', french: 'FR', chinese: 'ZH', japanese: 'JA', portuguese: 'PT',
};
function langPill(lang) {
  const key = String(lang || '').trim().toLowerCase();
  if (!key) return '—';
  return LANG_SHORT[key] || String(lang).slice(0, 2).toUpperCase();
}

export async function render(container, { sid, navigate, toast }) {
  let papers = [];
  let notices = {};
  let approved = false;
  let running = false;
  const decisions = new Map(); // paper_id → included (user staging)

  async function fetchSources(keepDecisions) {
    const res = await api.get(`/surveys/${sid}/sources`);
    papers = res.papers || [];
    notices = res.notices || {};
    approved = !!res.approved;
    const old = keepDecisions ? new Map(decisions) : null;
    decisions.clear();
    for (const p of papers) {
      const prev = old && old.has(p.paper_id) ? old.get(p.paper_id) : undefined;
      decisions.set(p.paper_id, prev !== undefined ? prev : p.included !== false);
    }
  }

  try { await fetchSources(false); } catch (err) {
    if (err.status && err.status !== 404) toast(err.detail, '⚠');
  }
  try { running = !!(await api.get(`/surveys/${sid}/run`)).running; } catch { /* no run yet */ }

  const filters = { q: '', year: '', conf: '', verified: false };
  const thisYear = new Date().getFullYear();

  container.innerHTML = `
    <div class="page-head">
      <div><h1>מקורות</h1><p>סוכנים 3–4 · סקירה, סינון ואישור מאמרים כולל ביקורת אמינות (Reliability Auditor). <b>נקודת אישור.</b></p></div>
    </div>
    <div id="noticeHost"></div>

    <div class="src-filters">
      <div class="search" style="width:240px"><span>🔍</span><input id="fQ" placeholder="חיפוש כותרת/מחבר…"></div>
      <select id="fYear">
        <option value="">שנה: הכל</option>
        <option value="recent">${thisYear - 2}–${thisYear}</option>
        <option value="mid">${thisYear - 6}–${thisYear - 3}</option>
        <option value="old">לפני ${thisYear - 6}</option>
      </select>
      <select id="fConf">
        <option value="">רמת אמון: הכל</option>
        <option value="HIGH">HIGH</option>
        <option value="MODERATE">MODERATE</option>
        <option value="LIMITED">LIMITED</option>
        <option value="EMERGING">EMERGING</option>
      </select>
      <label class="mini-check"><input type="checkbox" class="rowcb" id="fVerified"> מאומתים בלבד</label>
      <div style="flex:1"></div>
      <span class="run-note hidden" id="runNote"><span class="spin navy"></span> <span id="runNoteTxt">מחפש מקורות…</span></span>
      <button class="btn sm" id="addBtn">+ הוסף מקור</button>
      <button class="btn sm" id="moreBtn">🔁 חפש עוד</button>
    </div>

    <div id="tableHost"></div>

    <div class="actions-bar">
      <div class="sync-note">נבחרו <b id="selCount" style="color:var(--navy-700)">0</b> מתוך <span id="selTotal">0</span> מקורות</div>
      <button class="btn cta lg" id="approveBtn">אשר <span id="selCount2">0</span> מקורות והתחל כתיבה ←</button>
    </div>
  `;

  const tableHost = container.querySelector('#tableHost');
  const noticeHost = container.querySelector('#noticeHost');
  const runNote = container.querySelector('#runNote');
  const runNoteTxt = container.querySelector('#runNoteTxt');
  const moreBtn = container.querySelector('#moreBtn');

  function setRunning(on, msg) {
    running = on;
    runNote.classList.toggle('hidden', !on);
    if (msg) runNoteTxt.textContent = msg;
    moreBtn.disabled = on;
  }

  function renderNotice() {
    const doiFailed = notices.doi_failed || 0;
    const retracted = notices.retracted || 0;
    let html = '';
    if (doiFailed || retracted) {
      const parts = [];
      if (doiFailed) parts.push(`<b>${doiFailed} מאמרים</b> נכשלו באימות DOI מול Crossref`);
      if (retracted) parts.push(`<b>${retracted} מאמרים</b> סומנו כ-Retracted`);
      html = `<div class="notice">⚠️ <span>${parts.join(' · ')} — מסומנים באדום. הסר אותם או אמת ידנית לפני האישור.</span></div>`;
    }
    if (approved) {
      html += `<div class="notice ok">✓ <span>רשימת המקורות אושרה. אפשר עדיין לעדכן בחירות ולאשר מחדש.</span></div>`;
    }
    noticeHost.innerHTML = html;
  }

  function matches(p) {
    const q = filters.q.trim().toLowerCase();
    if (q) {
      const hay = `${p.title} ${(p.authors || []).join(' ')}`.toLowerCase();
      if (!hay.includes(q)) return false;
    }
    if (filters.year) {
      const y = p.year || 0;
      if (filters.year === 'recent' && y < thisYear - 2) return false;
      if (filters.year === 'mid' && (y < thisYear - 6 || y > thisYear - 3)) return false;
      if (filters.year === 'old' && y >= thisYear - 6) return false;
    }
    if (filters.conf && String(p.confidence || '').toUpperCase() !== filters.conf) return false;
    if (filters.verified && (p.doi_verified === false || p.is_retracted)) return false;
    return true;
  }

  function authorsText(a) {
    if (Array.isArray(a)) {
      return a.length > 2 ? `${a.slice(0, 2).join(', ')} et al.` : a.join(', ');
    }
    return a || '';
  }

  function rowHtml(p) {
    const unver = p.doi_verified === false || p.is_retracted;
    const conf = String(p.confidence || '').toUpperCase();
    const doiCell = p.doi
      ? `<a class="doi-link" href="https://doi.org/${esc(p.doi)}" target="_blank" rel="noopener">${esc(p.doi.length > 22 ? p.doi.slice(0, 22) + '…' : p.doi)}</a>${p.doi_verified === false ? ' <span class="warn-doi">⚠ לא אומת</span>' : ''}`
      : '<span class="warn-doi">⚠ DOI לא נמצא</span>';
    return `
      <tr class="${unver ? 'unver' : ''}" data-id="${esc(p.paper_id)}">
        <td><input type="checkbox" class="rowcb rowsel" ${decisions.get(p.paper_id) ? 'checked' : ''}></td>
        <td class="ttl">${p.is_retracted ? '<span class="retracted-pill">RETRACTED</span>' : ''}${esc(p.title)}</td>
        <td class="auth">${esc(authorsText(p.authors))}</td>
        <td>${esc(p.year ?? '—')}</td>
        <td><span class="lang-pill">${esc(langPill(p.language))}</span></td>
        <td>${Number(p.citation_count || 0).toLocaleString()}</td>
        <td><span class="badge ${confCls(conf)}">${esc(conf || '—')}</span>${p.tier ? ` <span class="lang-pill" title="Tier">${esc(p.tier)}</span>` : ''}</td>
        <td>${doiCell}</td>
        <td style="color:var(--muted);font-size:12px" title="${esc(p.found_via || '')}">${esc(p.source || '')}${p.found_via === 'user' ? ' 👤' : ''}</td>
      </tr>`;
  }

  const patchDecisions = debounce(async () => {
    const include = [];
    const exclude = [];
    for (const [id, inc] of decisions) (inc ? include : exclude).push(id);
    try {
      await api.patch(`/surveys/${sid}/sources`, { include, exclude });
    } catch (err) { toast(err.detail || 'שמירת הבחירה נכשלה', '⚠'); }
  }, 600);

  function updateCounts() {
    const n = [...decisions.values()].filter(Boolean).length;
    container.querySelector('#selCount').textContent = n;
    container.querySelector('#selCount2').textContent = n;
    container.querySelector('#selTotal').textContent = papers.length;
    container.querySelector('#approveBtn').disabled = !papers.length || n === 0;
  }

  function renderTable() {
    renderNotice();
    updateCounts();

    if (!papers.length) {
      tableHost.innerHTML = running
        ? `<div class="card empty">
             <div class="e-ico">🔍</div>
             <h3>חיפוש המקורות רץ כעת…</h3>
             <p>הטבלה תתעדכן אוטומטית כשצייד המקורות ומבקר האמינות יסיימו.</p>
           </div>`
        : `<div class="card empty">
             <div class="e-ico">📚</div>
             <h3>אין עדיין מקורות</h3>
             <p>ודא שתוכן העניינים אושר, ואז הפעל חיפוש מקורות — או חזור לתוכן העניינים לאישור.</p>
             <div class="e-actions">
               <button class="btn ghost" id="backToc">← לתוכן העניינים</button>
               <button class="btn cta" id="emptySearch">🔁 חפש מקורות</button>
             </div>
           </div>`;
      const backToc = tableHost.querySelector('#backToc');
      if (backToc) backToc.addEventListener('click', () => navigate(`#/s/${sid}/toc`));
      const emptySearch = tableHost.querySelector('#emptySearch');
      if (emptySearch) emptySearch.addEventListener('click', searchMore);
      return;
    }

    const list = papers.filter(matches);
    tableHost.innerHTML = `
      <div class="tbl-wrap">
        <table class="src">
          <thead><tr>
            <th><input type="checkbox" class="rowcb" id="selAll"></th>
            <th>כותרת</th><th>מחברים</th><th>שנה</th><th>שפה</th><th>ציטוטים</th><th>אמון</th><th>DOI</th><th>מקור</th>
          </tr></thead>
          <tbody>${list.map(rowHtml).join('') ||
            `<tr><td colspan="9" style="text-align:center;color:var(--muted);padding:24px">אין תוצאות למסננים שנבחרו</td></tr>`}
          </tbody>
        </table>
      </div>`;

    tableHost.querySelectorAll('.rowsel').forEach((cb) => {
      cb.addEventListener('change', () => {
        const id = cb.closest('tr').dataset.id;
        decisions.set(id, cb.checked);
        updateCounts();
        patchDecisions();
      });
    });
    const selAll = tableHost.querySelector('#selAll');
    selAll.checked = list.length > 0 && list.every((p) => decisions.get(p.paper_id));
    selAll.addEventListener('change', () => {
      list.forEach((p) => decisions.set(p.paper_id, selAll.checked));
      renderTable();
      patchDecisions();
    });
  }

  /* ---------- filters ---------- */
  container.querySelector('#fQ').addEventListener('input', (e) => { filters.q = e.target.value; renderTable(); });
  container.querySelector('#fYear').addEventListener('change', (e) => { filters.year = e.target.value; renderTable(); });
  container.querySelector('#fConf').addEventListener('change', (e) => { filters.conf = e.target.value; renderTable(); });
  container.querySelector('#fVerified').addEventListener('change', (e) => { filters.verified = e.target.checked; renderTable(); });

  /* ---------- manual add ---------- */
  container.querySelector('#addBtn').addEventListener('click', async () => {
    const raw = (prompt('הדבק DOI או כותרת מאמר להוספה ידנית:') || '').trim();
    if (!raw) return;
    const doiMatch = raw.match(/10\.\d{4,9}\/\S+/);
    const body = doiMatch ? { doi: doiMatch[0].replace(/[.,;]$/, '') } : { title: raw };
    try {
      const row = await api.post(`/surveys/${sid}/sources/manual`, body);
      papers.unshift(row);
      decisions.set(row.paper_id, row.included !== false);
      renderTable();
      toast('המקור נוסף לרשימה');
    } catch (err) {
      toast(err.status === 422 ? (err.detail || 'לא הצלחנו לזהות את המקור') : err.detail, '⚠');
    }
  });

  /* ---------- search more (background job + SSE) ---------- */
  async function searchMore() {
    if (running) return;
    try {
      await api.post(`/surveys/${sid}/sources/search`);
      setRunning(true, 'מחפש מקורות…');
      renderTable();
      toast('חיפוש מקורות התחיל');
    } catch (err) { toast(err.detail || 'לא ניתן להתחיל חיפוש', '⚠'); }
  }
  moreBtn.addEventListener('click', searchMore);

  /* ---------- approve → start run ---------- */
  container.querySelector('#approveBtn').addEventListener('click', async () => {
    const btn = container.querySelector('#approveBtn');
    btn.disabled = true;
    btn.innerHTML = '<span class="spin"></span> מאשר…';
    try {
      patchDecisions.cancel();
      const include = [];
      const exclude = [];
      for (const [id, inc] of decisions) (inc ? include : exclude).push(id);
      await api.patch(`/surveys/${sid}/sources`, { include, exclude });
      await api.post(`/surveys/${sid}/sources/approve`);
    } catch (err) {
      toast(err.detail || 'אישור המקורות נכשל', '⚠');
      btn.disabled = false;
      btn.innerHTML = 'אשר <span id="selCount2">0</span> מקורות והתחל כתיבה ←';
      renderTable();
      return;
    }
    try {
      await api.post(`/surveys/${sid}/run/start`);
      toast('המקורות אושרו — הכתיבה התחילה');
    } catch (err) {
      toast(err.detail || 'הריצה לא התחילה — נסה מהמסך הבא', '⚠');
    }
    navigate(`#/s/${sid}/pipeline`);
  });

  /* ---------- SSE: live progress of the search job ---------- */
  const close = subscribe(sid, {
    progress: (d) => {
      if (running) runNoteTxt.textContent = d.detail ? String(d.detail) : 'מחפש מקורות…';
    },
    stage_started: (d) => {
      if (d.stage === 'hunt' || d.stage === 'audit') setRunning(true, d.stage === 'audit' ? 'מבקר אמינות…' : 'מחפש מקורות…');
    },
    stage_done: async (d) => {
      if (d.stage !== 'hunt' && d.stage !== 'audit') return;
      try { await fetchSources(true); renderTable(); } catch { /* keep old table */ }
    },
    stage_failed: (d) => {
      setRunning(false);
      toast(`שלב ${d.stage || ''} נכשל: ${d.message || ''}`, '⚠');
      renderTable();
    },
    run_done: async () => {
      setRunning(false);
      try { await fetchSources(true); renderTable(); } catch { /* noop */ }
    },
    run_error: (d) => { setRunning(false); toast(d.message || 'שגיאה בריצה', '⚠'); },
    gate_reached: async (d) => {
      if (d.gate === 'sources') {
        setRunning(false);
        try { await fetchSources(true); renderTable(); } catch { /* noop */ }
        toast('חיפוש המקורות הסתיים — סקור ואשר');
      }
    },
  });

  setRunning(running);
  renderTable();
  return () => { close(); patchDecisions.cancel(); };
}

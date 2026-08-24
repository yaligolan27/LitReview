/* Screen 6 — draft review + approval gate: chapter nav, markdown editor,
 * confidence overrides, claim statuses, pins, rewrite job, approve. */

import { api } from '../api.js';
import { subscribe } from '../sse.js';
import { esc, confCls, confColor, ovValue, CONF_ORDER } from '../app.js';

const CLAIM_STATUSES = [
  { v: 'supported', l: 'נתמכת' },
  { v: 'uncertain', l: 'לא ודאית' },
  { v: 'unsupported', l: 'לא נתמכת' },
];

function normIssue(item) {
  if (item && typeof item === 'object') {
    const level = String(item.level || item.severity || '').toLowerCase();
    const text = item.message || item.text || item.issue || JSON.stringify(item);
    return { err: /err|critical|major|unsupported|red/.test(level), text };
  }
  return { err: false, text: String(item) };
}

function countOf(value) {
  return Array.isArray(value) ? value.length : (Number(value) || 0);
}

export async function render(container, { sid, navigate, toast }) {
  let overview = null;
  try { overview = await api.get(`/surveys/${sid}/draft`); } catch (err) {
    if (err.status && err.status !== 404) toast(err.detail, '⚠');
  }

  if (!overview || !(overview.chapters || []).length) {
    container.innerHTML = `
      <div class="page-head">
        <div><h1>עריכת טיוטה</h1><p>סוכנים 5–6 · עריכה אנושית והערות המבקר. <b>נקודת אישור אחרונה לפני הפקה.</b></p></div>
      </div>
      <div class="card empty">
        <div class="e-ico">✐</div>
        <h3>אין עדיין פרקים בטיוטה</h3>
        <p>הטיוטה נכתבת בשלב הריצה. עבור למסך הריצה כדי להפעיל או לעקוב אחרי הכתיבה.</p>
        <div class="e-actions">
          <button class="btn ghost" id="toSources">← למקורות</button>
          <button class="btn cta" id="toPipeline">⚙ למסך הריצה</button>
        </div>
      </div>`;
    container.querySelector('#toPipeline').addEventListener('click', () => navigate(`#/s/${sid}/pipeline`));
    container.querySelector('#toSources').addEventListener('click', () => navigate(`#/s/${sid}/sources`));
    return;
  }

  let chapters = overview.chapters;
  let curIndex = chapters[0].index;
  let detail = null;          // GET draft/chapters/{i}
  let lintResults = [];       // last PATCH lint results
  let sideTab = 'issues';
  let rewriteRunning = false;
  let alive = true;

  container.innerHTML = `
    <div class="page-head">
      <div><h1>עריכת טיוטה</h1><p>סוכנים 5–6 · עריכה אנושית והערות המבקר. <b>נקודת אישור אחרונה לפני הפקה.</b></p></div>
    </div>
    <div class="draft-grid">
      <aside class="card chap-nav" id="chapNav"></aside>
      <div class="card editor" id="editorHost"><div class="empty"><span class="spin navy"></span></div></div>
      <aside class="card panel" style="padding:16px" id="sideHost"></aside>
    </div>
  `;

  const navHost = container.querySelector('#chapNav');
  const editorHost = container.querySelector('#editorHost');
  const sideHost = container.querySelector('#sideHost');

  const listChapter = (i) => chapters.find((c) => c.index === i) || {};
  const effConf = (ch) => (ovValue(ch.confidence_override) || ch.confidence || '').toUpperCase();

  /* ---------- chapter nav (right column) ---------- */
  function renderNav() {
    navHost.innerHTML = `<div class="section-title" style="padding:4px 8px">פרקים</div>` +
      chapters.map((ch) => {
        const issues = countOf(ch.issues);
        return `
        <div class="cn ${ch.index === curIndex ? 'on' : ''}" data-i="${ch.index}">
          <span class="cn-t" title="${esc(ch.title)}">${esc(ch.index)}. ${esc(ch.title)}</span>
          ${issues ? `<span class="ib" title="הערות מבקר">${issues}</span>` : ''}
          <span class="dotc" style="background:${confColor(effConf(ch))}" title="${esc(effConf(ch) || '—')}"></span>
        </div>`;
      }).join('');
    navHost.querySelectorAll('.cn').forEach((el) => {
      el.addEventListener('click', () => loadChapter(+el.dataset.i));
    });
  }

  /* ---------- side panel (left column) ---------- */
  function renderSide() {
    const ch = listChapter(curIndex);
    const issues = (detail && detail.issues) || (Array.isArray(ch.issues) ? ch.issues : []);
    const claims = (detail && detail.claims) || [];
    const counts = { supported: 0, uncertain: 0, unsupported: 0 };
    claims.forEach((c) => {
      const s = (ovValue(c.status_override) || c.status || '').toLowerCase();
      if (s in counts) counts[s] += 1;
    });
    const summary = ch.claims_summary || {};
    const supported = claims.length ? counts.supported : (summary.supported || 0);
    const uncertain = claims.length ? counts.uncertain : (summary.uncertain || 0);
    const unsupported = claims.length ? counts.unsupported : (summary.unsupported || 0);
    const content = (detail && detail.content) || '';
    const words = content.trim() ? content.trim().split(/\s+/).length : 0;

    const issuesHtml = [
      ...lintResults.map((l) => {
        const { err, text } = normIssue(l);
        return `<div class="issue ${err ? 'err' : 'warn'}"><span class="ic">${err ? '🔴' : '🟠'}</span><div><b>בדיקת שמירה</b><br>${esc(text)}</div></div>`;
      }),
      ...issues.map((it) => {
        const { err, text } = normIssue(it);
        return `<div class="issue ${err ? 'err' : 'warn'}"><span class="ic">${err ? '🔴' : '🟠'}</span><div>${esc(text)}</div></div>`;
      }),
    ].join('') || '<div class="empty" style="padding:20px"><div class="e-ico">🕊</div><p style="margin:0">אין הערות מבקר לפרק הזה.</p></div>';

    sideHost.innerHTML = `
      <div class="side-tabs">
        <div class="st ${sideTab === 'issues' ? 'on' : ''}" data-tab="issues">הערות מבקר</div>
        <div class="st ${sideTab === 'stats' ? 'on' : ''}" data-tab="stats">סטטיסטיקה</div>
      </div>
      <div id="tabIssues" class="${sideTab === 'issues' ? '' : 'hidden'}">${issuesHtml}</div>
      <div id="tabStats" class="${sideTab === 'stats' ? '' : 'hidden'}">
        <div class="stat-mini">
          <div class="sm"><div class="n" style="color:var(--c-high-fg)">${supported}</div><div class="l">טענות נתמכות</div></div>
          <div class="sm"><div class="n" style="color:var(--c-lim-fg)">${uncertain}</div><div class="l">לא ודאיות</div></div>
          <div class="sm"><div class="n" style="color:var(--c-emg-fg)">${unsupported}</div><div class="l">לא נתמכות</div></div>
          <div class="sm"><div class="n">${words.toLocaleString()}</div><div class="l">מילים</div></div>
        </div>
      </div>`;
    sideHost.querySelectorAll('.st').forEach((el) => {
      el.addEventListener('click', () => { sideTab = el.dataset.tab; renderSide(); });
    });
  }

  /* ---------- editor (center column) ---------- */
  function autoGrow(ta) {
    ta.style.height = 'auto';
    ta.style.height = Math.max(280, ta.scrollHeight + 4) + 'px';
  }

  function renderEditor() {
    const ch = listChapter(curIndex);
    const override = ovValue(ch.confidence_override).toUpperCase();
    const eff = effConf(ch);

    const confChips = CONF_ORDER.map((v) =>
      `<span class="cp ${confCls(v)} ${eff === v ? 'on' : ''}" data-conf="${v}">${v}</span>`).join('');

    const claimsHtml = (detail.claims || []).map((c) => {
      const effStatus = (ovValue(c.status_override) || c.status || 'uncertain').toLowerCase();
      const text = String(c.text || '');
      const cites = Array.isArray(c.citations)
        ? c.citations.map((n) => `[${esc(n)}]`).join('') : esc(c.citations || '');
      return `
        <div class="claim-row ${esc(effStatus)}" data-id="${esc(c.id)}">
          <div class="ct" title="${esc(text)}">${esc(text.length > 160 ? text.slice(0, 160) + '…' : text)}
            ${cites ? `<span class="cites">${cites}</span>` : ''}
            ${ovValue(c.status_override) ? '<span class="ov-note">(נדרס ידנית)</span>' : ''}
          </div>
          <select class="claim-status">
            ${CLAIM_STATUSES.map((s) =>
              `<option value="${s.v}" ${s.v === effStatus ? 'selected' : ''}>${s.l}</option>`).join('')}
          </select>
        </div>`;
    }).join('') || '<div style="color:var(--muted);font-size:13px">לא זוהו טענות בפרק הזה.</div>';

    const pins = detail.pins || [];
    const pinsHtml = pins.map((p) => `
      <div class="pin-row ${p.status === 'open' ? '' : 'resolved'}" data-id="${esc(p.id)}">
        <span>${p.status === 'open' ? '📌' : '✓'}</span>
        <span class="pt">${esc(p.text)}</span>
        ${p.status === 'open' ? '<button class="rm pin-del" title="מחק הוראה">🗑</button>' : ''}
      </div>`).join('');

    editorHost.innerHTML = `
      <h2>${esc(detail.index)}. ${esc(detail.title)}</h2>
      <div class="conf-bar">
        <span style="font-size:13px;font-weight:700;color:var(--muted)">רמת אמינות הפרק:</span>
        <div class="conf-pick">${confChips}</div>
        ${override ? '<span class="ov-note">(נדרס ידנית — לחיצה על הרמה הפעילה מנקה)</span>' : ''}
        <span style="flex:1"></span>
        ${ch.stale_grounding ? '<span class="flag-chip" title="הטקסט נערך אחרי אימות הטענות">↻ עיגון לא מעודכן</span>' : ''}
        ${ch.user_edited ? '<span class="flag-chip" style="background:#e8f0fe;color:#1a3a8f;border-color:#90caf9">✎ נערך ידנית</span>' : ''}
      </div>

      <textarea class="editor-ta" id="contentTa" spellcheck="false"></textarea>
      <div class="actions-bar" style="margin-top:12px;padding-top:12px">
        <div class="sync-note" id="editNote">Markdown + סימוני ‎[n]‎ לציטוטים</div>
        <button class="btn primary" id="saveContent" disabled>שמור שינויים</button>
      </div>

      <div class="sub-title">🔎 טענות (claims) — סטטוס אימות מול המקורות</div>
      <div class="claims-list">${claimsHtml}</div>

      <div class="sub-title">📌 הוראות לפרק <span class="hint" style="font-weight:500">הכלי מטמיע אותן בכתיבה החוזרת</span></div>
      <div id="pinsList">${pinsHtml}</div>
      <div class="instr-box">
        <textarea class="input" id="pinText" placeholder="לדוגמה: הוסף כאן טבלת השוואה בין שלוש הארכיטקטורות / הוסף callout על מגבלות…"></textarea>
        <button class="btn sm" style="margin-top:8px" id="pinAdd">📌 הוסף הוראה</button>
      </div>

      <div class="actions-bar">
        <button class="btn" id="rewriteBtn">↻ שלח לכתיבה חוזרת</button>
        <button class="btn cta" id="approveBtn">אשר טיוטה והפק פלטים ←</button>
      </div>`;

    const ta = editorHost.querySelector('#contentTa');
    ta.value = detail.content || '';
    autoGrow(ta);
    const saveBtn = editorHost.querySelector('#saveContent');
    ta.addEventListener('input', () => { autoGrow(ta); saveBtn.disabled = false; });

    /* content save → lint feedback */
    saveBtn.addEventListener('click', async () => {
      saveBtn.disabled = true;
      saveBtn.innerHTML = '<span class="spin"></span> שומר…';
      try {
        const res = await api.patch(`/surveys/${sid}/draft/chapters/${curIndex}`, { content: ta.value });
        detail.content = ta.value;
        lintResults = [...(res && res.lint ? res.lint : []),
          ...((res && res.warnings) || []).map((w) => ({ level: 'warn', message: w }))];
        const ch = listChapter(curIndex);
        ch.user_edited = true;
        ch.stale_grounding = true;
        toast(lintResults.length ? `נשמר · ${lintResults.length} הערות בדיקה` : 'הפרק נשמר');
        sideTab = lintResults.length ? 'issues' : sideTab;
        renderEditor();
        renderSide();
      } catch (err) {
        toast(err.detail || 'שמירת הפרק נכשלה', '⚠');
        saveBtn.disabled = false;
        saveBtn.textContent = 'שמור שינויים';
      }
    });

    /* chapter confidence override */
    editorHost.querySelectorAll('.conf-pick .cp').forEach((chip) => {
      chip.addEventListener('click', async () => {
        const value = chip.dataset.conf;
        const clearing = override && value === eff;
        try {
          await api.put(`/surveys/${sid}/draft/chapters/${curIndex}/confidence`,
            { value: clearing ? '' : value });
          const c = listChapter(curIndex);
          c.confidence_override = clearing ? null : { value };
          toast(clearing ? 'הדריסה נוקתה — חזרה לרמה שחושבה' : `רמת האמינות עודכנה ל-${value}`);
          renderEditor();
          renderNav();
        } catch (err) { toast(err.detail || 'עדכון האמינות נכשל', '⚠'); }
      });
    });

    /* claim status overrides */
    editorHost.querySelectorAll('.claim-row').forEach((row) => {
      const sel = row.querySelector('.claim-status');
      sel.addEventListener('change', async () => {
        const id = row.dataset.id;
        try {
          await api.put(`/surveys/${sid}/draft/claims/${id}`, { status: sel.value });
          const claim = (detail.claims || []).find((c) => String(c.id) === id);
          if (claim) claim.status_override = { value: sel.value };
          row.className = `claim-row ${sel.value}`;
          toast('סטטוס הטענה עודכן');
          renderSide();
        } catch (err) { toast(err.detail || 'עדכון הטענה נכשל', '⚠'); }
      });
    });

    /* pins */
    editorHost.querySelector('#pinAdd').addEventListener('click', async () => {
      const input = editorHost.querySelector('#pinText');
      const text = input.value.trim();
      if (!text) { toast('כתוב הוראה תחילה', 'ℹ'); return; }
      try {
        const res = await api.post(`/surveys/${sid}/draft/chapters/${curIndex}/pins`, { text });
        (detail.pins = detail.pins || []).push({ id: res && res.id, text, status: 'open' });
        input.value = '';
        toast('ההוראה נוספה לפרק');
        renderEditor();
      } catch (err) { toast(err.detail || 'הוספת ההוראה נכשלה', '⚠'); }
    });
    editorHost.querySelectorAll('.pin-del').forEach((btn) => {
      btn.addEventListener('click', async () => {
        const row = btn.closest('.pin-row');
        const id = row.dataset.id;
        try {
          await api.del(`/surveys/${sid}/draft/chapters/${curIndex}/pins/${id}`);
          detail.pins = (detail.pins || []).filter((p) => String(p.id) !== id);
          toast('ההוראה נמחקה');
          renderEditor();
        } catch (err) { toast(err.detail || 'מחיקת ההוראה נכשלה', '⚠'); }
      });
    });

    /* rewrite current chapter (background job, tracked over SSE) */
    const rewriteBtn = editorHost.querySelector('#rewriteBtn');
    rewriteBtn.disabled = rewriteRunning;
    if (rewriteRunning) rewriteBtn.innerHTML = '<span class="spin navy"></span> כתיבה חוזרת רצה…';
    rewriteBtn.addEventListener('click', async () => {
      try {
        await api.post(`/surveys/${sid}/draft/rewrite`, { chapters: [curIndex] });
        rewriteRunning = true;
        toast('נשלח לכתיבה חוזרת עם ההוראות וההערות');
        renderEditor();
      } catch (err) { toast(err.detail || 'הכתיבה החוזרת לא התחילה', '⚠'); }
    });

    /* approve draft → produce outputs */
    editorHost.querySelector('#approveBtn').addEventListener('click', approveDraft);
  }

  async function approveDraft() {
    const btn = editorHost.querySelector('#approveBtn');
    btn.disabled = true;
    btn.innerHTML = '<span class="spin"></span> מאשר…';
    try {
      try {
        await api.post(`/surveys/${sid}/draft/approve`, {});
      } catch (err) {
        const openPins = err.status === 409 && err.data && err.data.open_pins;
        if (!openPins) throw err;
        const ok = confirm(`יש ${openPins.length} הוראות (📌) פתוחות שטרם טופלו.\nלאשר את הטיוטה בכל זאת?`);
        if (!ok) throw { detail: 'האישור בוטל — טפל בהוראות הפתוחות או אשר בכוח', silent: true };
        await api.post(`/surveys/${sid}/draft/approve`, { force: true });
      }
      try {
        await api.post(`/surveys/${sid}/run/start`);
        toast('הטיוטה אושרה — הפקת הפלטים התחילה');
      } catch (err) {
        toast(err.detail || 'הטיוטה אושרה, אך ההפקה לא התחילה', '⚠');
      }
      navigate(`#/s/${sid}/export`);
    } catch (err) {
      if (!err.silent) toast(err.detail || 'אישור הטיוטה נכשל', '⚠');
      btn.disabled = false;
      btn.textContent = 'אשר טיוטה והפק פלטים ←';
    }
  }

  /* ---------- data loading ---------- */
  async function loadChapter(i) {
    curIndex = i;
    lintResults = [];
    renderNav();
    editorHost.innerHTML = '<div class="empty"><span class="spin navy"></span></div>';
    try {
      detail = await api.get(`/surveys/${sid}/draft/chapters/${i}`);
      if (!alive) return;
      renderEditor();
      renderSide();
    } catch (err) {
      if (!alive) return;
      editorHost.innerHTML = `<div class="empty"><div class="e-ico">⚠️</div><h3>הפרק לא נטען</h3><p>${esc(err.detail)}</p></div>`;
      renderSide();
    }
  }

  async function reloadAll() {
    try {
      const fresh = await api.get(`/surveys/${sid}/draft`);
      if (!alive) return;
      chapters = fresh.chapters || chapters;
      renderNav();
      await loadChapter(curIndex);
    } catch { /* keep current view */ }
  }

  /* ---------- SSE: rewrite job progress ---------- */
  const close = subscribe(sid, {
    progress: (d) => {
      if (!rewriteRunning) return;
      const note = editorHost.querySelector('#editNote');
      if (note) note.textContent = `↻ ${d.stage || ''}: ${d.detail || 'רץ…'}`;
    },
    stage_failed: (d) => {
      if (!rewriteRunning) return;
      rewriteRunning = false;
      toast(`הכתיבה החוזרת נכשלה: ${d.message || d.stage || ''}`, '⚠');
      renderEditor();
    },
    run_done: () => {
      if (!rewriteRunning) return;
      rewriteRunning = false;
      toast('הכתיבה החוזרת הסתיימה — הפרק נטען מחדש');
      reloadAll();
    },
    run_error: (d) => {
      if (!rewriteRunning) return;
      rewriteRunning = false;
      toast(d.message || 'שגיאה בכתיבה החוזרת', '⚠');
      renderEditor();
    },
  });

  renderNav();
  await loadChapter(curIndex);
  return () => { alive = false; close(); };
}

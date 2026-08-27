/* Screen 5 — live pipeline run: agent stepper from GET run, overall
 * progress, and an SSE-fed log console. Gates navigate onward. */

import { api } from '../api.js';
import { subscribe } from '../sse.js';
import { esc } from '../app.js';

const STAGE_TITLES = {
  plan: 'מתכנן המחקר',
  toc: 'תוכן עניינים',
  hunt: 'צייד המקורות',
  audit: 'מבקר האמינות',
  fulltext: 'טקסט מלא',
  deep_research: 'מחקר עומק',
  write: 'כתיבה',
  ground: 'עיגון טענות',
  review: 'ביקורת',
  fix_loop: 'לולאת תיקון',
  executive: 'תקציר מנהלים',
  edit_language: 'עריכת לשון',
  citations: 'ציטוטים',
  visualize: 'גרפים',
  ideation: 'רעיונות',
  glossary: 'מילון מונחים',
  evaluate: 'הערכה',
  html: 'הרכבת המסמך',
  extras: 'פלטים',
};

const STATUS_CLS = {
  done: 'done', running: 'run', failed: 'fail', stale: 'stale',
  skipped: 'skip', pending: 'wait',
};

function fmtDuration(started, ended) {
  if (!started || !ended) return '';
  const secs = Math.max(0, Math.round((new Date(ended) - new Date(started)) / 1000));
  if (Number.isNaN(secs)) return '';
  if (secs < 60) return `${secs}ש׳`;
  return `${Math.floor(secs / 60)}:${String(secs % 60).padStart(2, '0')}`;
}

export async function render(container, { sid, navigate, toast }) {
  let run = { stages: [], gates: {}, running: false, overall_pct: 0 };
  let card = null;
  try { run = await api.get(`/surveys/${sid}/run`); } catch (err) {
    if (err.status && err.status !== 404) toast(err.detail, '⚠');
  }
  try { card = await api.get(`/surveys/${sid}`); } catch { /* optional */ }

  container.innerHTML = `
    <div class="page-head">
      <div><h1>ריצת המערכת</h1><p>סוכנים 5–11 · מעקב חי אחרי הכתיבה, הביקורת וההפקה.</p></div>
      <div style="display:flex;gap:10px">
        <button class="btn" id="startBtn">▶ המשך ריצה</button>
        <button class="btn" id="draftBtn">📄 טיוטה חלקית</button>
      </div>
    </div>

    <div class="card panel" style="margin-bottom:22px">
      <div class="run-head">
        <div class="chap">התקדמות כללית · <span id="chapCount"></span></div>
        <div style="font-weight:800;color:var(--navy-700)" id="pctLabel">0%</div>
      </div>
      <div class="progress"><span id="overallBar" style="width:0%"></span></div>
    </div>

    <div id="bridgePanel"></div>

    <div class="run-grid">
      <div class="card stepper" id="stepper"></div>
      <div>
        <div class="section-title">📟 לוג חי (stdout מהסוכנים)</div>
        <div class="log" id="logBox"></div>
      </div>
    </div>
  `;

  const stepper = container.querySelector('#stepper');
  const logBox = container.querySelector('#logBox');
  const startBtn = container.querySelector('#startBtn');
  const startedAt = Date.now();

  /* ---------- log console ---------- */
  function logLine(cls, msg) {
    const secs = Math.floor((Date.now() - startedAt) / 1000);
    const mm = String(Math.floor(secs / 60)).padStart(2, '0');
    const ss = String(secs % 60).padStart(2, '0');
    const line = document.createElement('div');
    line.innerHTML = `<span class="t">[${mm}:${ss}]</span> <span class="${esc(cls)}">${esc(msg)}</span>`;
    logBox.appendChild(line);
    logBox.scrollTop = logBox.scrollHeight;
  }
  logLine('info', 'connected — waiting for pipeline events…');

  /* ---------- native-bridge panel ----------
   * Personal mode (a Claude subscription, no API key): the pipeline waits
   * for a Claude Code session to serve the file bridge. Surface the bridge
   * dir and a copy-paste serving command right where the user is watching. */
  function renderBridgePanel() {
    const panel = container.querySelector('#bridgePanel');
    if ((run.backend || '') !== 'native') { panel.innerHTML = ''; return; }
    const dir = run.bridge_dir || '';
    const cmd = dir
      ? `claude "קרא את SKILL.md בשורש הריפו ושרת את גשר הקבצים בתיקייה ${dir} — עני על כל בקשה לפי הכללים, עד שהריצה מסתיימת"`
      : '';
    panel.innerHTML = `
      <div class="card panel" style="margin-bottom:22px;border-inline-start:4px solid var(--blue-600)">
        <div style="font-weight:800;color:var(--navy-700);margin-bottom:6px">🔌 מצב native — הצינור מופעל על ידי סשן Claude Code</div>
        <div style="font-size:13.5px;color:var(--muted);line-height:1.7">
          הריצה לא צורכת API: היא כותבת בקשות לתיקיית הגשר וממתינה שסשן
          Claude Code (על המנוי שלך) יענה עליהן. פתחי טרמינל בתיקיית הפרויקט
          והדביקי את הפקודה:
        </div>
        ${dir ? `
        <div style="display:flex;gap:8px;align-items:center;margin-top:10px">
          <code id="bridgeCmd" style="flex:1;direction:ltr;text-align:left;background:var(--soft);border:1px solid var(--line);border-radius:8px;padding:8px 10px;font-size:12px;overflow-x:auto;white-space:nowrap">${esc(cmd)}</code>
          <button class="btn" id="copyBridge" title="העתקה">📋</button>
        </div>
        <div style="font-size:12.5px;color:var(--muted);margin-top:6px">תיקיית הגשר: <code style="direction:ltr;unicode-bidi:embed">${esc(dir)}</code></div>
        ` : `
        <div style="font-size:13px;color:var(--muted);margin-top:8px">תיקיית הגשר תופיע כאן ברגע שהריצה תתחיל.</div>
        `}
      </div>`;
    const copyBtn = panel.querySelector('#copyBridge');
    if (copyBtn) {
      copyBtn.addEventListener('click', async () => {
        try {
          await navigator.clipboard.writeText(cmd);
          toast('הפקודה הועתקה');
        } catch {
          toast('העתקה נחסמה — סמני את הטקסט ידנית', '⚠');
        }
      });
    }
  }

  /* ---------- stepper + progress ---------- */
  function renderRun() {
    renderBridgePanel();
    const stages = run.stages || [];
    if (!stages.length) {
      stepper.innerHTML = `<div class="empty" style="padding:28px 18px">
        <div class="e-ico">⚙</div>
        <h3 style="font-size:1rem">הריצה עוד לא התחילה</h3>
        <p style="font-size:13px">אשר את המקורות, או לחץ "המשך ריצה" להפעלת הקטע הבא.</p>
      </div>`;
    } else {
      stepper.innerHTML = stages.map((s, i) => {
        const cls = STATUS_CLS[s.status] || 'wait';
        let icon = i + 1;
        if (s.status === 'done') icon = '✓';
        else if (s.status === 'running') icon = '<span class="spin"></span>';
        else if (s.status === 'failed') icon = '✗';
        else if (s.status === 'stale') icon = '↻';
        else if (s.status === 'skipped') icon = '—';
        const time = s.status === 'running' ? 'רץ…' : (fmtDuration(s.started, s.ended) || '—');
        return `
          <div class="agent ${cls}" data-stage="${esc(s.id)}">
            <div class="ai">${icon}</div>
            <div class="meta-a">
              <div class="an">${esc(STAGE_TITLES[s.id] || s.title || s.id)}</div>
              <div class="ad">${esc(s.title && STAGE_TITLES[s.id] ? s.title : s.id)}</div>
              ${s.error ? `<div class="aerr">${esc(s.error)}</div>` : ''}
            </div>
            <div class="at">${time}</div>
          </div>`;
      }).join('');
    }

    const pct = Math.max(0, Math.min(100, run.overall_pct || 0));
    container.querySelector('#overallBar').style.width = pct + '%';
    container.querySelector('#pctLabel').textContent = pct + '%';
    container.querySelector('#chapCount').textContent = card && card.chapters_total
      ? `פרק ${card.chapters_done}/${card.chapters_total}` : 'סטטוס הריצה';
    startBtn.disabled = !!run.running;
    startBtn.innerHTML = run.running ? '<span class="spin navy"></span> רץ…' : '▶ המשך ריצה';
  }

  let refreshing = false;
  async function refresh() {
    if (refreshing) return;
    refreshing = true;
    try {
      run = await api.get(`/surveys/${sid}/run`);
      try { card = await api.get(`/surveys/${sid}`); } catch { /* keep old */ }
      renderRun();
    } catch { /* transient */ }
    refreshing = false;
  }

  /* ---------- buttons ---------- */
  startBtn.addEventListener('click', async () => {
    startBtn.disabled = true;
    try {
      await api.post(`/surveys/${sid}/run/start`);
      logLine('info', 'run segment started');
      toast('הריצה הופעלה');
      await refresh();
    } catch (err) {
      toast(err.detail || 'לא ניתן להפעיל ריצה כעת', '⚠');
      startBtn.disabled = false;
    }
  });
  container.querySelector('#draftBtn').addEventListener('click', () => navigate(`#/s/${sid}/draft`));

  /* ---------- SSE ---------- */
  const LOG_CLS = { error: 'err', err: 'err', warning: 'warn', warn: 'warn', ok: 'ok', success: 'ok' };
  // The SSE stream replays history on connect (Last-Event-ID). Historical
  // gate_reached events must not yank the user away from this screen —
  // only a gate reached by a LIVE run navigates onward.
  const mountedAt = Date.now();
  const isLiveEvent = () => Date.now() - mountedAt > 2000;
  const close = subscribe(sid, {
    stage_started: (d) => {
      logLine('info', `→ stage started: ${d.stage || '?'} (${STAGE_TITLES[d.stage] || ''})`);
      refresh();
    },
    progress: (d) => logLine('info', `${d.stage || 'run'}: ${d.detail || ''}`),
    log: (d) => logLine(LOG_CLS[String(d.level || '').toLowerCase()] || 'info',
      `${d.stage ? d.stage + ': ' : ''}${d.message || ''}`),
    stage_done: (d) => {
      logLine('ok', `stage done: ${d.stage || '?'}${d.duration ? ` (${d.duration}s)` : ''}`);
      refresh();
    },
    stage_skipped: (d) => { logLine('warn', `stage skipped: ${d.stage || '?'}`); refresh(); },
    stage_failed: (d) => {
      logLine('err', `stage failed: ${d.stage || '?'} — ${d.message || ''}`);
      toast(`שלב ${STAGE_TITLES[d.stage] || d.stage || ''} נכשל`, '⚠');
      refresh();
    },
    gate_reached: (d) => {
      logLine('ok', `gate reached: ${d.gate || '?'}`);
      if (!isLiveEvent()) { refresh(); return; }
      if (d.gate === 'draft') {
        toast('הטיוטה מוכנה לאישור — מעבר לעריכה');
        navigate(`#/s/${sid}/draft`);
      } else if (d.gate === 'sources') {
        toast('המקורות מוכנים לאישור');
        navigate(`#/s/${sid}/sources`);
      } else if (d.gate === 'toc') {
        toast('תוכן העניינים מוכן לאישור');
        navigate(`#/s/${sid}/toc`);
      } else {
        refresh();
      }
    },
    run_done: () => {
      logLine('ok', 'pipeline segment complete');
      toast('הריצה הושלמה');
      refresh();
    },
    run_error: (d) => {
      logLine('err', `run error: ${d.message || ''}`);
      toast(d.message || 'שגיאה בריצה', '⚠');
      refresh();
    },
  });

  renderRun();
  return () => close();
}

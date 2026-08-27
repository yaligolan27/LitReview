/* Screen 7 — exports: per-format generate/download cards + HTML preview. */

import { api } from '../api.js';
import { esc, fmtBytes, fmtDate } from '../app.js';

const FORMATS = [
  { id: 'html', name: 'HTML', desc: 'תקן הזהב · אינטראקטיבי', ico: '⬡', bg: '#e65100' },
  { id: 'pdf', name: 'PDF', desc: 'להדפסה ולהפצה', ico: 'PDF', bg: '#c62828' },
  { id: 'docx', name: 'DOCX', desc: 'Word · RTL לעריכה', ico: 'W', bg: '#1565c0' },
  { id: 'slides', name: 'מצגת', desc: 'תקציר מנהלים', ico: '▦', bg: '#e8710a' },
  { id: 'podcast', name: 'NotebookLM', desc: 'טקסט + הוראות העלאה', ico: '🎧', bg: '#7b1fa2' },
];

const STATUS_CHIP = {
  ready: { label: 'מוכן ✓', cls: 'ready' },
  stale: { label: 'ישן — הפק מחדש ↻', cls: 'stale click' },
  idle: { label: 'הפק ←', cls: 'idle click' },
  unavailable: { label: 'לא זמין', cls: 'unavail' },
};

export async function render(container, { sid, navigate, toast, card }) {
  let statuses = new Map(); // format → {status, bytes, generated_at}

  async function fetchExports() {
    const res = await api.get(`/surveys/${sid}/exports`);
    statuses = new Map((res.formats || []).map((f) => [f.format, f]));
  }
  try { await fetchExports(); } catch (err) {
    if (err.status && err.status !== 404) toast(err.detail, '⚠');
  }

  container.innerHTML = `
    <div class="page-head">
      <div><h1>תצוגה מקדימה וייצוא</h1><p>סוכנים 7–11 · הסקר הסופי בסגנון תקן הזהב, מוכן להורדה.</p></div>
    </div>
    <div class="exp-grid">
      <div class="preview" id="previewHost"></div>
      <aside>
        <div class="section-title">📦 פורמטי ייצוא</div>
        <div id="cardsHost"></div>
        <button class="btn cta lg" style="width:100%;margin-top:14px" id="dlAll">⤓ הורד הכל</button>
        <button class="btn" style="width:100%;margin-top:10px" id="backDash">← חזרה לדשבורד</button>
      </aside>
    </div>
  `;

  const cardsHost = container.querySelector('#cardsHost');
  const previewHost = container.querySelector('#previewHost');
  const generating = new Set();

  const downloadUrl = (fmt) => `/api/surveys/${sid}/exports/${fmt}/download`;

  function triggerDownload(fmt) {
    const a = document.createElement('a');
    a.href = downloadUrl(fmt);
    a.download = '';
    document.body.appendChild(a);
    a.click();
    a.remove();
  }

  function renderPreview() {
    const html = statuses.get('html');
    if (html && (html.status === 'ready' || html.status === 'stale')) {
      previewHost.innerHTML =
        `<iframe src="/api/surveys/${sid}/exports/html/download?inline=1" title="תצוגה מקדימה"></iframe>`;
    } else {
      const topic = (card && card.topic) || 'סקר ספרות';
      const sub = card
        ? `סקירה שיטתית · ${card.sources_count || 0} מקורות · ${card.chapters_total || 0} פרקים`
        : '';
      previewHost.innerHTML = `
        <div class="pv-cover">
          <div class="k">סקר ספרות · ${new Date().getFullYear()}</div>
          <h1>${esc(topic)}</h1>
          <div class="sub">${esc(sub)}</div>
        </div>
        <div class="pv-body">
          התצוגה המקדימה תופיע כאן אחרי הפקת פורמט ה-HTML.<br>
          לחץ "הפק ←" בכרטיס HTML מימין.
        </div>`;
    }
  }

  function renderCards() {
    cardsHost.innerHTML = FORMATS.map((f) => {
      const st = statuses.get(f.id) || { status: 'idle' };
      const isGen = generating.has(f.id);
      const chip = isGen
        ? { label: 'מפיק…', cls: 'gen' }
        : (STATUS_CHIP[st.status] || STATUS_CHIP.idle);
      const canDl = !isGen && (st.status === 'ready' || st.status === 'stale');
      const meta = st.generated_at
        ? `<span class="fmeta">${esc(fmtBytes(st.bytes))} · ${esc(fmtDate(st.generated_at))}</span>` : '';
      return `
        <div class="exp-card" data-fmt="${f.id}">
          <div class="ei" style="background:${f.bg}">${f.ico}</div>
          <div class="en"><b>${esc(f.name)}</b><span>${esc(f.desc)}</span>${meta}</div>
          ${canDl ? '<button class="dl" title="הורדה">⤓</button>' : ''}
          <span class="exp-status ${chip.cls}">${esc(chip.label)}</span>
        </div>`;
    }).join('');

    cardsHost.querySelectorAll('.exp-card').forEach((el) => {
      const fmt = el.dataset.fmt;
      const chip = el.querySelector('.exp-status');
      if (chip.classList.contains('click')) {
        chip.addEventListener('click', () => generate(fmt));
      }
      const dl = el.querySelector('.dl');
      if (dl) dl.addEventListener('click', () => triggerDownload(fmt));
    });

    const anyReady = FORMATS.some((f) => {
      const st = statuses.get(f.id);
      return st && (st.status === 'ready' || st.status === 'stale');
    });
    container.querySelector('#dlAll').disabled = !anyReady;
  }

  async function generate(fmt) {
    if (generating.has(fmt)) return;
    generating.add(fmt);
    renderCards();
    try {
      const res = await api.post(`/surveys/${sid}/exports`, { formats: [fmt] });
      if (res && res.formats) {
        statuses = new Map(res.formats.map((f) => [f.format, f]));
      } else {
        await fetchExports();
      }
      generating.delete(fmt);
      const st = statuses.get(fmt);
      if (st && st.status === 'ready') toast('הפלט הופק בהצלחה');
      else if (st && st.status === 'unavailable') toast('הפורמט אינו זמין בסביבה הזו', '⚠');
      else toast('סטטוס הפורמט עודכן');
    } catch (err) {
      generating.delete(fmt);
      toast(err.detail || 'ההפקה נכשלה', '⚠');
    }
    renderCards();
    renderPreview();
  }

  container.querySelector('#dlAll').addEventListener('click', () => {
    const ready = FORMATS.filter((f) => {
      const st = statuses.get(f.id);
      return st && (st.status === 'ready' || st.status === 'stale');
    });
    if (!ready.length) { toast('אין פלטים מוכנים להורדה', 'ℹ'); return; }
    ready.forEach((f, i) => setTimeout(() => triggerDownload(f.id), i * 400));
    toast(`מוריד ${ready.length} פלטים…`, '⤓');
  });
  container.querySelector('#backDash').addEventListener('click', () => navigate('#/dashboard'));

  renderCards();
  renderPreview();
}

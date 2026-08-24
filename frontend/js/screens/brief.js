/* Screen 2 — research brief form with debounced autosave (PUT is a full
 * replace, so the whole loaded object is kept and only edited keys change). */

import { api } from '../api.js';
import { esc, debounce } from '../app.js';

const LANGS = [
  { v: 'English', l: 'English' },
  { v: 'Hebrew', l: 'עברית' },
  { v: 'Russian', l: 'Русский' },
  { v: 'German', l: 'Deutsch' },
  { v: 'Spanish', l: 'Español' },
  { v: 'Chinese', l: '中文' },
  { v: 'Japanese', l: '日本語' },
  { v: 'Portuguese', l: 'Português' },
];

const DEFAULT_BRIEF = {
  topic: '', search_topic: '', goals: [], audience: '',
  year_from: 2015, year_to: new Date().getFullYear(),
  languages: ['English', 'Hebrew'], user_papers: [], user_experts: [],
  author: '', scope_preset: 'full', scope_target_pages: null,
  output_slides: false, output_podcast: false,
};

function splitList(text) {
  return String(text || '').split(/[\n·]+/).map((s) => s.trim()).filter(Boolean);
}

export async function render(container, { sid, navigate, toast }) {
  let b = { ...DEFAULT_BRIEF };
  try {
    const loaded = await api.get(`/surveys/${sid}/brief`);
    if (loaded && typeof loaded === 'object') b = { ...DEFAULT_BRIEF, ...loaded };
  } catch (err) {
    if (err.status && err.status !== 404) toast(err.detail, '⚠');
  }

  /* selected languages: match saved values against the canonical list,
   * keep unknown values as extra chips */
  const known = new Map(LANGS.map((x) => [x.v.toLowerCase(), x.v]));
  const knownLabels = new Map(LANGS.map((x) => [x.l.toLowerCase(), x.v]));
  const selected = new Set();
  const extra = [];
  for (const lang of (b.languages || [])) {
    const key = String(lang).trim().toLowerCase();
    const canon = known.get(key) || knownLabels.get(key);
    if (canon) selected.add(canon);
    else { extra.push(String(lang)); selected.add(String(lang)); }
  }

  container.innerHTML = `
    <div class="page-head">
      <div><h1>הגדרת סקר</h1><p>סוכן 1 · איסוף ה־ResearchBrief. שינויים נשמרים אוטומטית.</p></div>
    </div>

    <div class="cols">
      <div class="card panel">
        <div class="row2">
          <div class="field">
            <label>נושא הסקר (עברית) <span class="hint">לתצוגה ולכתיבה</span></label>
            <input class="input" id="fTopic" value="${esc(b.topic)}">
          </div>
          <div class="field">
            <label>נושא לחיפוש (אנגלית) <span class="hint">למאגרים</span></label>
            <input class="input" id="fSearchTopic" dir="ltr" value="${esc(b.search_topic)}">
          </div>
        </div>

        <div class="field">
          <label>מטרות הסקר</label>
          <div id="goals"></div>
          <button class="btn sm" id="addGoal">+ הוסף מטרה</button>
        </div>

        <div class="row2">
          <div class="field">
            <label>קהל יעד</label>
            <input class="input" id="fAudience" value="${esc(b.audience)}">
          </div>
          <div class="field">
            <label>טווח שנים</label>
            <div class="row2">
              <input class="input" id="fYearFrom" type="number" placeholder="מ-" value="${esc(b.year_from ?? '')}">
              <input class="input" id="fYearTo" type="number" placeholder="עד" value="${esc(b.year_to ?? '')}">
            </div>
          </div>
        </div>

        <div class="field">
          <label>שפות חיפוש <span class="hint">לחיצה על שפה מפעילה/מכבה אותה</span></label>
          <div class="chip-wrap" id="langs"></div>
        </div>

        <div class="green-box">
          <div class="gh">➕ מקורות נוספים <span style="font-weight:600;font-size:12px">(לא חובה)</span></div>
          <div class="gsub">הכלי כבר מאתר מקורות בעצמו. כאן אפשר <b>להוסיף</b> מאמרים/מומחים שחשוב לכלול — זו תוספת, לא תחליף.</div>
          <div class="field" style="margin-bottom:12px">
            <label>מאמרים ידועים (DOI / כותרת) <span class="hint">שורה או · לכל פריט</span></label>
            <textarea class="input" id="fPapers" placeholder='10.1145/3586183 · "ReAct: Synergizing Reasoning and Acting"…'></textarea>
          </div>
          <div class="field" style="margin-bottom:0">
            <label>מומחים / קבוצות מחקר</label>
            <textarea class="input" id="fExperts" placeholder="שמות חוקרים או מעבדות שכדאי לעקוב אחרי הפרסומים שלהם…"></textarea>
          </div>
        </div>

        <div class="field">
          <label>היקף הסקר</label>
          <div class="scope-opts">
            <div class="scope-opt" data-scope="summary"><div class="sn">~10</div><div class="sd">תמצית עמודים</div></div>
            <div class="scope-opt" data-scope="full"><div class="sn">30–40</div><div class="sd">סקר מלא</div></div>
            <div class="scope-opt" data-scope="custom"><div class="sn">✎</div><div class="sd">מותאם אישית</div></div>
          </div>
          <div class="scope-custom hidden" id="scopeCustom">
            <span>יעד עמודים:</span>
            <input class="input" id="fTargetPages" type="number" min="1" value="${esc(b.scope_target_pages ?? 20)}">
          </div>
        </div>

        <div class="field">
          <label>פלטים נוספים <span class="hint">אופציונלי</span></label>
          <label class="check"><input type="checkbox" id="fSlides" ${b.output_slides ? 'checked' : ''}><span><span class="ct">🎞 מצגת</span> <span class="cs">— תקציר מנהלים כשקופיות</span></span></label>
          <label class="check"><input type="checkbox" id="fPodcast" ${b.output_podcast ? 'checked' : ''}><span><span class="ct">🎧 פודקאסט</span> <span class="cs">— הוראות + טקסט ל-NotebookLM</span></span></label>
        </div>

        <div class="field" style="margin-bottom:0">
          <label>מחבר <span class="hint">יופיע על כריכת הסקר</span></label>
          <input class="input" id="fAuthor" value="${esc(b.author)}">
        </div>

        <div class="actions-bar">
          <div class="sync-note" id="syncNote">🔄 שינויים נשמרים אוטומטית</div>
          <div style="display:flex;gap:10px">
            <button class="btn" id="saveBtn">שמור טיוטה</button>
            <button class="btn cta" id="buildBtn">בנה תוכן עניינים ←</button>
          </div>
        </div>
      </div>

      <aside class="card panel">
        <div class="section-title">🧭 מה קורה בשלב הזה</div>
        <div class="side-list">
          <div class="si"><div class="st">1 · הגדרה</div><div class="sd">הטופס הזה מזין את סוכן תכנון המחקר.</div></div>
          <div class="si"><div class="st">2 · תוכן עניינים</div><div class="sd">ייבנה אוטומטית מהנושא והמטרות — ותוכל לערוך ולאשר.</div></div>
          <div class="si"><div class="st">3 · מקורות</div><div class="sd">חיפוש רב-לשוני במאגרים + ביקורת אמינות (DOI, retraction).</div></div>
          <div class="si"><div class="st">4 · כתיבה והפקה</div><div class="sd">כתיבה מעוגנת-ציטוטים, ביקורת, עריכת לשון וייצוא.</div></div>
        </div>
      </aside>
    </div>
  `;

  /* ---------- goals ---------- */
  const goalsHost = container.querySelector('#goals');
  function addGoalRow(value = '') {
    const row = document.createElement('div');
    row.className = 'goal-row';
    row.innerHTML = `<input class="input" placeholder="מטרה חדשה…"><button class="rm" title="הסר">✕</button>`;
    row.querySelector('input').value = value;
    row.querySelector('.rm').addEventListener('click', () => { row.remove(); scheduleSave(); });
    goalsHost.appendChild(row);
    return row;
  }
  (b.goals || []).forEach((g) => addGoalRow(g));
  container.querySelector('#addGoal').addEventListener('click', () => {
    addGoalRow().querySelector('input').focus();
  });

  /* ---------- language chips ---------- */
  const langsHost = container.querySelector('#langs');
  function chipEl(value, label) {
    const chip = document.createElement('span');
    chip.className = 'chip ' + (selected.has(value) ? 'on' : 'off');
    chip.textContent = label;
    chip.addEventListener('click', () => {
      if (selected.has(value)) selected.delete(value); else selected.add(value);
      chip.className = 'chip ' + (selected.has(value) ? 'on' : 'off');
      scheduleSave();
    });
    return chip;
  }
  function renderLangs() {
    langsHost.innerHTML = '';
    LANGS.forEach(({ v, l }) => langsHost.appendChild(chipEl(v, l)));
    extra.forEach((v) => langsHost.appendChild(chipEl(v, v)));
    const add = document.createElement('span');
    add.className = 'chip add';
    add.textContent = '+ שפה';
    add.addEventListener('click', () => {
      const name = (prompt('שם השפה להוספה (למשל: Français):') || '').trim();
      if (!name) return;
      if (!extra.includes(name) && !LANGS.some((x) => x.v === name)) extra.push(name);
      selected.add(name);
      renderLangs();
      scheduleSave();
    });
    langsHost.appendChild(add);
  }
  renderLangs();

  /* ---------- scope ---------- */
  const scopeOpts = container.querySelectorAll('.scope-opt');
  const scopeCustom = container.querySelector('#scopeCustom');
  function setScope(preset) {
    b.scope_preset = preset;
    scopeOpts.forEach((o) => o.classList.toggle('on', o.dataset.scope === preset));
    scopeCustom.classList.toggle('hidden', preset !== 'custom');
  }
  scopeOpts.forEach((o) => o.addEventListener('click', () => { setScope(o.dataset.scope); scheduleSave(); }));
  setScope(b.scope_preset || 'full');

  /* prefill list textareas */
  container.querySelector('#fPapers').value = (b.user_papers || []).join('\n');
  container.querySelector('#fExperts').value = (b.user_experts || []).join('\n');

  /* ---------- collect + save ---------- */
  const $ = (id) => container.querySelector(id);
  function collect() {
    b.topic = $('#fTopic').value.trim();
    b.search_topic = $('#fSearchTopic').value.trim();
    b.goals = [...goalsHost.querySelectorAll('input')].map((i) => i.value.trim()).filter(Boolean);
    b.audience = $('#fAudience').value.trim();
    b.year_from = parseInt($('#fYearFrom').value, 10) || DEFAULT_BRIEF.year_from;
    b.year_to = parseInt($('#fYearTo').value, 10) || DEFAULT_BRIEF.year_to;
    b.languages = [...LANGS.map((x) => x.v), ...extra].filter((v) => selected.has(v));
    b.user_papers = splitList($('#fPapers').value);
    b.user_experts = splitList($('#fExperts').value);
    b.output_slides = $('#fSlides').checked;
    b.output_podcast = $('#fPodcast').checked;
    b.author = $('#fAuthor').value.trim();
    b.scope_target_pages = b.scope_preset === 'custom'
      ? (parseInt($('#fTargetPages').value, 10) || null) : null;
    return b;
  }

  const syncNote = container.querySelector('#syncNote');
  let alive = true;
  async function save() {
    collect();
    syncNote.textContent = '🔄 שומר…';
    try {
      await api.put(`/surveys/${sid}/brief`, b);
      if (!alive) return;
      const t = new Date();
      syncNote.textContent = `🔄 נשמר אוטומטית · ${String(t.getHours()).padStart(2, '0')}:${String(t.getMinutes()).padStart(2, '0')}`;
    } catch (err) {
      if (!alive) return;
      syncNote.textContent = '⚠ השמירה נכשלה';
      toast(err.detail, '⚠');
      throw err;
    }
  }
  const scheduleSave = debounce(() => save().catch(() => {}), 800);
  container.querySelector('.card.panel').addEventListener('input', scheduleSave);

  container.querySelector('#saveBtn').addEventListener('click', async () => {
    scheduleSave.cancel();
    try { await save(); toast('הטיוטה נשמרה'); } catch { /* toasted in save() */ }
  });

  container.querySelector('#buildBtn').addEventListener('click', async () => {
    const btn = container.querySelector('#buildBtn');
    scheduleSave.cancel();
    collect();
    if (!b.topic && !b.search_topic) { toast('הגדר נושא לסקר תחילה', '⚠'); return; }
    btn.disabled = true;
    btn.innerHTML = '<span class="spin"></span> בונה תוכן עניינים…';
    try {
      await save();
      await api.post(`/surveys/${sid}/toc/build`);
      toast('תוכן העניינים נבנה');
      navigate(`#/s/${sid}/toc`);
    } catch (err) {
      toast(err.detail || 'בניית תוכן העניינים נכשלה', '⚠');
      btn.disabled = false;
      btn.textContent = 'בנה תוכן עניינים ←';
    }
  });

  return () => { alive = false; scheduleSave.cancel(); };
}

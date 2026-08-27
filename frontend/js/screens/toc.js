/* Screen 3 — TOC editing + approval gate: editable chapters/sections/
 * keywords, drag reorder, gap-fill suggestions, approve → source search. */

import { api } from '../api.js';
import { esc } from '../app.js';

export async function render(container, ctx) {
  const { sid, navigate, toast } = ctx;

  let data = null;
  try {
    data = await api.get(`/surveys/${sid}/toc`);
  } catch (err) {
    if (err.status && err.status !== 404) toast(err.detail, '⚠');
  }

  /* ---------- empty state: no TOC built yet ---------- */
  if (!data || !(data.chapters || []).length) {
    container.innerHTML = `
      <div class="page-head">
        <div><h1>תוכן עניינים</h1><p>סוכן 2 · עריכה ואישור. <b>נקודת אישור אנושי.</b></p></div>
      </div>
      <div class="card empty">
        <div class="e-ico">☰</div>
        <h3>אין עדיין תוכן עניינים</h3>
        <p>בנה תוכן עניינים אוטומטית מתוך הגדרת הסקר (Brief), או חזור להגדרה כדי להשלים אותה.</p>
        <div class="e-actions">
          <button class="btn ghost" id="backBrief">← חזרה להגדרה</button>
          <button class="btn cta" id="buildBtn">🏗 בנה תוכן עניינים</button>
        </div>
      </div>`;
    container.querySelector('#backBrief').addEventListener('click', () => navigate(`#/s/${sid}/brief`));
    container.querySelector('#buildBtn').addEventListener('click', async () => {
      const btn = container.querySelector('#buildBtn');
      btn.disabled = true;
      btn.innerHTML = '<span class="spin"></span> בונה תוכן עניינים…';
      try {
        await api.post(`/surveys/${sid}/toc/build`);
        toast('תוכן העניינים נבנה');
        render(container, ctx); // re-enter with fresh data
      } catch (err) {
        toast(err.detail || 'בניית תוכן העניינים נכשלה', '⚠');
        btn.disabled = false;
        btn.textContent = '🏗 בנה תוכן עניינים';
      }
    });
    return;
  }

  /* ---------- editable model ---------- */
  let nextKey = 0;
  const byKey = new Map();
  let chapters = (data.chapters || []).map((c) => {
    const ch = { ...c, _k: nextKey++ };
    ch.chapter = ch.chapter || '';
    ch.sections = [...(ch.sections || [])];
    ch.keywords_en = [...(ch.keywords_en || [])];
    byKey.set(ch._k, ch);
    return ch;
  });
  const rule = (data.meter && data.meter.rule) || '≥8';

  container.innerHTML = `
    <div class="page-head">
      <div><h1>תוכן עניינים</h1><p>סוכן 2 · עריכה ואישור. גרור פרקים לסידור, הוסף/מחק/ערוך. <b>נקודת אישור אנושי.</b></p></div>
    </div>

    <div class="toc-meta">
      <div class="toc-meter ok" id="chMeter"></div>
      <div style="flex:1"></div>
      <button class="btn sm" id="suggestBtn">💡 הצעות אוטומטיות</button>
      <button class="btn sm" id="addChapterBtn">+ הוסף פרק</button>
      <button class="btn sm" id="saveBtn">💾 שמור</button>
    </div>

    <div id="chapters"></div>
    <div id="suggestHost"></div>

    <div class="actions-bar">
      <button class="btn ghost" id="backBtn">← חזרה להגדרה</button>
      <button class="btn cta lg" id="approveBtn">אשר והמשך לאיסוף מקורות ←</button>
    </div>
  `;

  const host = container.querySelector('#chapters');
  const meterEl = container.querySelector('#chMeter');

  function updateMeter() {
    const n = chapters.length;
    const ok = n >= 8;
    meterEl.className = 'toc-meter ' + (ok ? 'ok' : 'warn');
    meterEl.textContent = ok
      ? `✓ ${n} פרקים — עומד בדרישת התקן (${rule})`
      : `⚠ ${n} פרקים — מומלץ ${rule} (לא חוסם)`;
    host.querySelectorAll('.cidx').forEach((c, i) => { c.textContent = i + 1; });
  }

  function syncFromDom() {
    chapters = [...host.querySelectorAll('.chapter')].map((el) => byKey.get(+el.dataset.key));
    updateMeter();
  }

  function chapterEl(ch, index) {
    const el = document.createElement('div');
    el.className = 'chapter';
    el.draggable = true;
    el.dataset.key = ch._k;
    el.innerHTML = `
      <div class="ch-head">
        <span class="grip" title="גרור לסידור">⠿</span>
        <span class="cidx">${index + 1}</span>
        <input class="ctitle" placeholder="שם הפרק…">
        <div class="ch-actions">
          <button class="icon-btn add-sec" title="הוסף תת-סעיף">＋</button>
          <button class="icon-btn del-ch" title="מחק פרק">🗑</button>
        </div>
      </div>
      <div class="kw-line">
        <label>מילות מפתח לחיפוש (EN)</label>
        <input class="kw" placeholder="agent architectures, orchestration, …">
      </div>
      <div class="ch-secs"></div>`;

    const title = el.querySelector('.ctitle');
    title.value = ch.chapter;
    title.addEventListener('input', () => { ch.chapter = title.value; });

    const kw = el.querySelector('.kw');
    kw.value = ch.keywords_en.join(', ');
    kw.addEventListener('input', () => {
      ch.keywords_en = kw.value.split(',').map((s) => s.trim()).filter(Boolean);
    });

    const secs = el.querySelector('.ch-secs');
    const addBtn = document.createElement('button');
    addBtn.className = 'sec-add';
    addBtn.textContent = '+ תת-סעיף';

    function secRow(value, sIdx) {
      const row = document.createElement('div');
      row.className = 'sec-item';
      row.innerHTML = `<span class="sb">›</span><input class="input" placeholder="תת-סעיף חדש…"><button class="rm-sec" title="הסר">✕</button>`;
      const input = row.querySelector('input');
      input.value = value;
      input.dataset.idx = sIdx;
      input.addEventListener('input', () => {
        ch.sections = [...secs.querySelectorAll('input')].map((i) => i.value.trim()).filter(Boolean);
      });
      row.querySelector('.rm-sec').addEventListener('click', () => {
        row.remove();
        ch.sections = [...secs.querySelectorAll('input')].map((i) => i.value.trim()).filter(Boolean);
      });
      return row;
    }
    ch.sections.forEach((s, i) => secs.appendChild(secRow(s, i)));
    secs.appendChild(addBtn);
    addBtn.addEventListener('click', () => {
      const row = secRow('', secs.querySelectorAll('.sec-item').length);
      secs.insertBefore(row, addBtn);
      row.querySelector('input').focus();
    });
    el.querySelector('.add-sec').addEventListener('click', () => addBtn.click());

    el.querySelector('.del-ch').addEventListener('click', () => {
      if (ch.chapter && !confirm(`למחוק את הפרק "${ch.chapter}"?`)) return;
      byKey.delete(ch._k);
      el.remove();
      syncFromDom();
    });

    /* drag reorder (HTML5, like the mockup) */
    el.addEventListener('dragstart', () => { dragEl = el; el.classList.add('dragging'); });
    el.addEventListener('dragend', () => { el.classList.remove('dragging'); dragEl = null; syncFromDom(); });
    el.addEventListener('dragover', (e) => {
      e.preventDefault();
      if (!dragEl || dragEl === el) return;
      const rect = el.getBoundingClientRect();
      const before = e.clientY < rect.top + rect.height / 2;
      host.insertBefore(dragEl, before ? el : el.nextSibling);
    });
    return el;
  }

  let dragEl = null;
  function renderChapters() {
    host.innerHTML = '';
    chapters.forEach((ch, i) => host.appendChild(chapterEl(ch, i)));
    updateMeter();
  }

  function addChapter(title = 'פרק חדש', sections = []) {
    const ch = { chapter: title, sections: [...sections], keywords_en: [], _k: nextKey++ };
    byKey.set(ch._k, ch);
    chapters.push(ch);
    const el = chapterEl(ch, chapters.length - 1);
    host.appendChild(el);
    updateMeter();
    const input = el.querySelector('.ctitle');
    input.focus();
    input.select();
    return ch;
  }

  function payload() {
    syncFromDom();
    return {
      chapters: chapters.map(({ _k, ...rest }) => ({
        ...rest,
        chapter: (rest.chapter || '').trim() || 'פרק ללא שם',
      })),
    };
  }

  async function saveToc() {
    await api.put(`/surveys/${sid}/toc`, payload());
  }

  /* ---------- suggestions ---------- */
  const suggestHost = container.querySelector('#suggestHost');
  container.querySelector('#suggestBtn').addEventListener('click', async () => {
    const btn = container.querySelector('#suggestBtn');
    btn.disabled = true;
    btn.innerHTML = '<span class="spin navy"></span> מחפש פערים…';
    try {
      const res = await api.post(`/surveys/${sid}/toc/suggestions`);
      const suggestions = (res && res.suggestions) || [];
      if (!suggestions.length) {
        toast('לא נמצאו פערים — תוכן העניינים נראה שלם');
        suggestHost.innerHTML = '';
      } else {
        suggestHost.innerHTML = `
          <div class="suggest">
            <h4>💡 הצעות אוטומטיות למילוי פערים</h4>
            ${suggestions.map((s, i) => `
              <div class="sug" data-i="${i}">
                <span>${s.kind === 'section' ? 'תת-סעיף מוצע' : 'פרק מוצע'}: <b>${esc(s.title)}</b>
                  ${s.kind === 'section' && s.parent ? ` תחת "${esc(s.parent)}"` : ''}
                  ${s.reason ? ` <span class="why">— ${esc(s.reason)}</span>` : ''}</span>
                <button>+ הוסף</button>
              </div>`).join('')}
          </div>`;
        suggestHost.querySelectorAll('.sug').forEach((row) => {
          row.querySelector('button').addEventListener('click', () => {
            const s = suggestions[+row.dataset.i];
            if (s.kind === 'section') {
              syncFromDom();
              const parent = chapters.find((c) => c.chapter === s.parent)
                || chapters.find((c) => s.parent && c.chapter.includes(s.parent))
                || chapters[chapters.length - 1];
              if (parent) {
                parent.sections.push(s.title);
                renderChapters();
              } else {
                addChapter(s.title);
              }
            } else {
              addChapter(s.title);
            }
            row.remove();
            toast('ההצעה נוספה לתוכן העניינים');
          });
        });
      }
    } catch (err) { toast(err.detail || 'שליפת ההצעות נכשלה', '⚠'); }
    btn.disabled = false;
    btn.textContent = '💡 הצעות אוטומטיות';
  });

  /* ---------- actions ---------- */
  container.querySelector('#addChapterBtn').addEventListener('click', () => addChapter());
  container.querySelector('#backBtn').addEventListener('click', () => navigate(`#/s/${sid}/brief`));

  container.querySelector('#saveBtn').addEventListener('click', async () => {
    try { await saveToc(); toast('תוכן העניינים נשמר'); }
    catch (err) { toast(err.detail, '⚠'); }
  });

  container.querySelector('#approveBtn').addEventListener('click', async () => {
    const btn = container.querySelector('#approveBtn');
    btn.disabled = true;
    btn.innerHTML = '<span class="spin"></span> מאשר…';
    try {
      await saveToc();
      await api.post(`/surveys/${sid}/toc/approve`, {});
    } catch (err) {
      toast(err.detail || 'אישור תוכן העניינים נכשל', '⚠');
      btn.disabled = false;
      btn.textContent = 'אשר והמשך לאיסוף מקורות ←';
      return;
    }
    try {
      await api.post(`/surveys/${sid}/sources/search`);
      toast('תוכן העניינים אושר — חיפוש מקורות התחיל');
    } catch (err) {
      /* approved anyway — the sources screen exposes a retry */
      toast(err.detail || 'חיפוש המקורות לא התחיל', '⚠');
    }
    navigate(`#/s/${sid}/sources`);
  });

  renderChapters();
}

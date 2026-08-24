/* Screen 1 — dashboard: stats, survey cards, search/filter,
 * create/delete surveys, gold-standard swap. */

import { api, getOperator } from '../api.js';
import { esc, fmtDate, STATUS_META, statusScreen } from '../app.js';

export async function render(container, { navigate, toast }) {
  let data;
  try {
    data = await api.get('/surveys');
  } catch (err) {
    container.innerHTML = `<div class="card empty">
      <div class="e-ico">📡</div>
      <h3>לא ניתן לטעון את הדשבורד</h3>
      <p>${esc(err.detail)}</p>
      <div class="e-actions"><button class="btn primary" id="retry">נסה שוב</button></div>
    </div>`;
    container.querySelector('#retry').addEventListener('click', () => render(container, { navigate, toast }));
    return;
  }

  const surveys = data.surveys || [];
  const stats = data.stats || {};
  const filter = {
    q: (document.getElementById('globalSearchInput') || {}).value || '',
    status: '',
  };
  let goldPick = false; // "swap gold standard" selection mode

  container.innerHTML = `
    <div class="page-head">
      <div><h1>הסקרים שלי</h1><p>נקודת כניסה — צפייה, המשך וניהול גרסאות של סקרי ספרות.</p></div>
      <button class="btn cta lg" id="newSurveyBtn">+ סקר חדש</button>
    </div>

    <div class="stat-row">
      <div class="card stat"><div class="num">${esc(stats.total ?? surveys.length)}</div><div class="lbl">סה״כ סקרים</div></div>
      <div class="card stat run"><div class="num">${esc(stats.running ?? 0)}</div><div class="lbl">בתהליך</div></div>
      <div class="card stat done"><div class="num">${esc(stats.done ?? 0)}</div><div class="lbl">הושלמו</div></div>
      <div class="card stat"><div class="num">${esc(stats.papers_analyzed ?? 0)}</div><div class="lbl">מאמרים שנותחו</div></div>
    </div>

    <div class="toolbar">
      <div class="search" style="width:260px"><span>🔍</span><input id="dashSearch" placeholder="חיפוש לפי נושא…"></div>
      <select id="statusFilter">
        <option value="">סטטוס: הכל</option>
        ${Object.entries(STATUS_META)
          .filter(([s]) => s !== 'archived')
          .map(([s, m]) => `<option value="${s}">${esc(m.label)}</option>`).join('')}
      </select>
    </div>

    <div id="goldNote" class="notice hidden">👑 <span>בחר כרטיס סקר שיוגדר כתקן הזהב החדש, או <b id="goldCancel" style="cursor:pointer;text-decoration:underline">בטל</b>.</span></div>
    <div class="grid" id="grid"></div>
  `;

  const grid = container.querySelector('#grid');
  const dashSearch = container.querySelector('#dashSearch');
  const statusFilter = container.querySelector('#statusFilter');
  dashSearch.value = filter.q;

  function visible() {
    const q = filter.q.trim().toLowerCase();
    return surveys.filter((s) => {
      if (filter.status && s.status !== filter.status) return false;
      if (!q) return true;
      return `${s.topic} ${s.operator}`.toLowerCase().includes(q);
    });
  }

  function cardHtml(s) {
    const meta = STATUS_META[s.status] || { label: s.status, cls: 'stage wait' };
    const versions = [...(s.versions || [])].sort((a, b) => b.v - a.v);
    const vtags = versions.map((v) =>
      `<span class="vtag ${v.v === s.current_version ? 'cur' : ''}">v${esc(v.v)}</span>`).join('');
    const chapters = s.chapters_total
      ? `<span>פרק ${esc(s.chapters_done)}/${esc(s.chapters_total)}</span>` : '';
    return `
      <div class="card s-card ${s.gold ? 'gold' : ''}" data-id="${esc(s.id)}">
        <div class="top">
          <h3>${s.gold ? '<span class="crown">👑</span> ' : ''}${esc(s.topic)}</h3>
          <span class="badge ${meta.cls}">${esc(meta.label)}</span>
        </div>
        ${s.gold ? '<span class="badge gold-b">תקן הזהב הנוכחי</span>' : ''}
        <div class="progress"><span style="width:${Math.max(0, Math.min(100, s.progress_pct || 0))}%"></span></div>
        <div class="meta">
          <span><b>${esc(s.sources_count ?? 0)}</b> מקורות</span>
          ${chapters}
          <span>${esc(s.operator || '—')} · ${esc(fmtDate(s.updated_at))}</span>
        </div>
        <div class="vers">גרסאות: ${vtags || '<span class="vtag cur">v1</span>'}</div>
        ${s.gold
          ? '<button class="btn sm gold-swap" style="width:100%;margin-top:10px">⇄ החלף תקן זהב</button>'
          : ''}
        <button class="del" title="מחק">🗑</button>
      </div>`;
  }

  function renderGrid() {
    const list = visible();
    grid.classList.toggle('goldpick', goldPick);
    container.querySelector('#goldNote').classList.toggle('hidden', !goldPick);

    let html = `
      <div class="card s-card new" id="newCard">
        <div class="plus">+</div>
        <b>סקר חדש</b>
        <span style="font-size:13px;color:var(--muted);margin-top:4px">התחל מהגדרת נושא</span>
      </div>`;
    html += list.map(cardHtml).join('');
    grid.innerHTML = html;

    if (!surveys.length) {
      grid.insertAdjacentHTML('beforeend', `
        <div class="card empty" style="grid-column:1/-1">
          <div class="e-ico">📚</div>
          <h3>אין עדיין סקרים</h3>
          <p>צור סקר חדש כדי להתחיל — הגדרת נושא, בניית תוכן עניינים ואיסוף מקורות.</p>
        </div>`);
    } else if (!list.length) {
      grid.insertAdjacentHTML('beforeend', `
        <div class="card empty" style="grid-column:1/-1">
          <div class="e-ico">🔍</div>
          <h3>לא נמצאו סקרים תואמים</h3>
          <p>נסה חיפוש אחר או אפס את מסנן הסטטוס.</p>
        </div>`);
    }

    grid.querySelector('#newCard').addEventListener('click', createSurvey);

    grid.querySelectorAll('.s-card[data-id]').forEach((el) => {
      const id = el.dataset.id;
      const survey = surveys.find((s) => s.id === id);

      el.addEventListener('click', async () => {
        if (goldPick) {
          if (survey.gold) return;
          try {
            await api.put('/gold-standard', { survey_id: id });
            toast('תקן הזהב עודכן', '👑');
            reload();
          } catch (err) { toast(err.detail, '⚠'); }
          return;
        }
        navigate(`#/s/${id}/${statusScreen(survey.status)}`);
      });

      const del = el.querySelector('.del');
      del.addEventListener('click', async (e) => {
        e.stopPropagation();
        if (!confirm(`להעביר את הסקר "${survey.topic}" לארכיון?`)) return;
        try {
          await api.del(`/surveys/${id}`);
          toast('הסקר הוסר מהדשבורד');
          reload();
        } catch (err) { toast(err.detail, '⚠'); }
      });

      const swap = el.querySelector('.gold-swap');
      if (swap) {
        swap.addEventListener('click', (e) => {
          e.stopPropagation();
          goldPick = !goldPick;
          if (goldPick) toast('בחר סקר אחר להגדרה כתקן הזהב', '👑');
          renderGrid();
        });
      }
    });
  }

  async function reload() {
    try {
      const fresh = await api.get('/surveys');
      surveys.length = 0;
      surveys.push(...(fresh.surveys || []));
      goldPick = false;
      renderGrid();
    } catch (err) { toast(err.detail, '⚠'); }
  }

  async function createSurvey() {
    try {
      const card = await api.post('/surveys', { operator: getOperator() });
      toast('סקר חדש נוצר — הגדר את הנושא');
      navigate(`#/s/${card.id}/brief`);
    } catch (err) { toast(err.detail, '⚠'); }
  }

  container.querySelector('#newSurveyBtn').addEventListener('click', createSurvey);
  container.querySelector('#goldNote').querySelector('#goldCancel')
    .addEventListener('click', () => { goldPick = false; renderGrid(); });

  dashSearch.addEventListener('input', () => { filter.q = dashSearch.value; renderGrid(); });
  statusFilter.addEventListener('change', () => { filter.status = statusFilter.value; renderGrid(); });

  /* topbar global search filters the dashboard too */
  const onGlobalSearch = (e) => {
    filter.q = e.detail || '';
    dashSearch.value = filter.q;
    renderGrid();
  };
  window.addEventListener('litreview:search', onGlobalSearch);

  renderGrid();
  return () => window.removeEventListener('litreview:search', onGlobalSearch);
}

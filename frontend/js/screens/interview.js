/* Screen 1.5 — Deep Interview (M8): a survey-style chat before the pipeline
 * runs. Each interviewer turn arrives as structured questions with prepared
 * clickable options (+ optional free-text detail per question); the user can
 * also just type freely. Turns go through the LLM gateway (native mode: the
 * user's own Claude Code session serves them via the bridge). Finishing
 * distills a research charter that is merged into the brief. */

import { api } from '../api.js';
import { subscribe } from '../sse.js';
import { esc } from '../app.js';

export async function render(container, { sid, navigate, toast }) {
  container.innerHTML = `
    <div class="page-head">
      <div><h1>🎙 ראיון עומק</h1>
        <p>המראיין מציג שאלות עם אפשרויות מוכנות — פשוט ללחוץ, ואפשר תמיד לפרט
        חופשי. אין הגבלת זמן; בסיום מופקת "אמנת מחקר" שמנחה את כל שלבי הכתיבה.</p></div>
      <div style="display:flex;gap:10px">
        <button class="btn" id="skipBtn">דלג לתוכן עניינים</button>
        <button class="btn cta" id="finishBtn">✔ סיים ראיון והפק אמנה</button>
      </div>
    </div>

    <div id="bridgeHint"></div>

    <div class="card panel" style="padding:0;display:flex;flex-direction:column;height:min(66vh,700px)">
      <div class="chat" id="chat"></div>
      <div class="chat-input">
        <textarea id="msgBox" rows="2" placeholder="או כתבי חופשי — תשובה, הרחבה או כל דבר שחשוב שנדע…"></textarea>
        <button class="btn cta" id="sendBtn">שלח ↵</button>
      </div>
    </div>
    <div id="charterCard"></div>
  `;

  const chat = container.querySelector('#chat');
  const msgBox = container.querySelector('#msgBox');
  const sendBtn = container.querySelector('#sendBtn');
  const finishBtn = container.querySelector('#finishBtn');
  let waiting = false;
  let activeCard = null;      // the current interactive survey card, if any

  /* ---------- bridge hint (native mode) ---------- */
  try {
    const run = await api.get(`/surveys/${sid}/run`);
    if (run.backend === 'native') {
      const dir = run.bridge_dir || 'var/surveys/<id>/v1/bridge';
      container.querySelector('#bridgeHint').innerHTML = `
        <div class="card panel" style="margin-bottom:16px;border-inline-start:4px solid var(--blue-600);font-size:13px;color:var(--muted)">
          🔌 מצב native: גם הראיון עובר דרך הגשר — ודאי שסשן Claude Code משרת
          פתוח בטרמינל (הפקודה במסך "ריצה"). תיקיית הגשר:
          <code style="direction:ltr;unicode-bidi:embed">${esc(dir)}</code>
        </div>`;
    }
  } catch { /* hint is optional */ }

  /* ---------- rendering ---------- */
  function bubble(role, text) {
    const div = document.createElement('div');
    div.className = `bubble ${role === 'user' ? 'user' : 'assistant'}`;
    div.innerHTML = esc(text).replace(/\n/g, '<br>');
    chat.appendChild(div);
    chat.scrollTop = chat.scrollHeight;
    return div;
  }

  /* An answered/superseded survey card collapses to its plain-text form. */
  function freezeActiveCard() {
    if (!activeCard) return;
    const text = activeCard.dataset.plain || '';
    const plain = document.createElement('div');
    plain.className = 'bubble assistant';
    plain.innerHTML = esc(text).replace(/\n/g, '<br>');
    activeCard.replaceWith(plain);
    activeCard = null;
  }

  function surveyCard(message) {
    const turn = message.turn;
    const card = document.createElement('div');
    card.className = 'survey-card';
    card.dataset.plain = message.text || '';
    let html = '';
    if (turn.intro) html += `<div class="sv-intro">${esc(turn.intro)}</div>`;
    turn.questions.forEach((q, qi) => {
      const chips = (q.options || []).map((o, oi) =>
        `<button type="button" class="chip" data-q="${qi}" data-o="${oi}">${esc(o)}</button>`).join('');
      html += `
        <div class="q-block" data-multi="${q.multi ? 1 : 0}" data-qi="${qi}">
          <div class="q-text">${qi + 1}. ${esc(q.text)}${q.multi ? ' <span class="q-hint">(אפשר לבחור כמה)</span>' : ''}</div>
          <div class="chips">${chips}</div>
          ${q.allow_other ? `<input class="input other-input" data-q="${qi}" placeholder="אחר / פירוט חופשי (לא חובה)…">` : ''}
        </div>`;
    });
    if (turn.done_hint) {
      html += `<div class="sv-done">✔ נראה שהתמונה מלאה — אפשר ללחוץ "סיים ראיון והפק אמנה", או להמשיך להוסיף.</div>`;
    }
    if (turn.questions.length) {
      html += `<button class="btn cta sv-send" type="button">שלח תשובות ←</button>`;
    }
    card.innerHTML = html;

    card.querySelectorAll('.chip').forEach((chip) => {
      chip.addEventListener('click', () => {
        const block = chip.closest('.q-block');
        if (block.dataset.multi !== '1') {
          block.querySelectorAll('.chip.sel').forEach((c) => { if (c !== chip) c.classList.remove('sel'); });
        }
        chip.classList.toggle('sel');
      });
    });

    const sendAnswers = card.querySelector('.sv-send');
    if (sendAnswers) {
      sendAnswers.addEventListener('click', () => {
        const parts = [];
        turn.questions.forEach((q, qi) => {
          const block = card.querySelector(`.q-block[data-qi="${qi}"]`);
          const picked = [...block.querySelectorAll('.chip.sel')].map((c) => c.textContent.trim());
          const other = (block.querySelector('.other-input') || {}).value || '';
          if (!picked.length && !other.trim()) return;
          let line = `${q.text}\n← ${picked.join(', ') || '—'}`;
          if (other.trim()) line += `${picked.length ? ' · ' : ''}פירוט: ${other.trim()}`;
          parts.push(line);
        });
        if (!parts.length) { toast('בחרי לפחות תשובה אחת או כתבי פירוט', 'ℹ'); return; }
        sendText(parts.join('\n\n'));
      });
    }
    chat.appendChild(card);
    chat.scrollTop = chat.scrollHeight;
    return card;
  }

  function renderMessage(m, interactive) {
    if (m.role === 'assistant' && interactive && m.turn && m.turn.questions
        && m.turn.questions.length) {
      freezeActiveCard();
      activeCard = surveyCard(m);
    } else if (m.role === 'assistant' && m.turn && !m.turn.questions.length
               && interactive) {
      // A question-less turn (e.g. saturation hint) — plain bubble is right.
      bubble('assistant', m.text);
    } else {
      bubble(m.role, m.text);
    }
  }

  function setWaiting(on, label = 'המראיין חושב…') {
    waiting = on;
    sendBtn.disabled = on;
    finishBtn.disabled = on;
    let typing = chat.querySelector('.typing');
    if (on) {
      if (!typing) {
        typing = document.createElement('div');
        typing.className = 'bubble assistant typing';
        chat.appendChild(typing);
      }
      typing.textContent = label;
      chat.scrollTop = chat.scrollHeight;
    } else if (typing) {
      typing.remove();
    }
  }

  function renderCharter(charterText, fields) {
    container.querySelector('#charterCard').innerHTML = `
      <div class="card panel" style="margin-top:18px;border-inline-start:4px solid #2f855a">
        <div style="font-weight:800;color:#22543d;margin-bottom:6px">📜 אמנת המחקר הופקה ושולבה בהגדרת הסקר</div>
        ${fields && fields.length ? `<div style="font-size:13px;color:var(--muted);margin-bottom:8px">שדות שעודכנו: ${esc(fields.join(', '))}</div>` : ''}
        <div style="white-space:pre-wrap;font-size:13.5px;background:var(--soft);border:1px solid var(--line);border-radius:10px;padding:12px;max-height:260px;overflow:auto">${esc(charterText || '')}</div>
        <div style="display:flex;gap:10px;margin-top:12px">
          <button class="btn cta" id="toTocBtn">המשך לתוכן עניינים ←</button>
          <button class="btn" id="toBriefBtn">עיון בהגדרה המעודכנת</button>
        </div>
      </div>`;
    container.querySelector('#toTocBtn').addEventListener('click', () => navigate(`#/s/${sid}/toc`));
    container.querySelector('#toBriefBtn').addEventListener('click', () => navigate(`#/s/${sid}/brief`));
  }

  /* ---------- initial load ---------- */
  let doc = { messages: [], status: 'idle', busy: false };
  try { doc = await api.get(`/surveys/${sid}/interview`); } catch (err) {
    toast(err.detail || 'טעינת הראיון נכשלה', '⚠');
  }
  doc.messages.forEach((m, i) => {
    renderMessage(m, i === doc.messages.length - 1 && doc.status !== 'done');
  });
  let rendered = doc.messages.length;   // idempotency cursor (SSE replays history)

  /* Re-sync from server state — safe under SSE replays and duplicates. */
  async function refreshChat() {
    let d;
    try { d = await api.get(`/surveys/${sid}/interview`); } catch { return; }
    for (let i = rendered; i < d.messages.length; i++) {
      renderMessage(d.messages[i],
        i === d.messages.length - 1 && d.status !== 'done');
    }
    rendered = Math.max(rendered, d.messages.length);
    if (!d.busy) setWaiting(false);
    if (d.status === 'done' && d.charter) {
      freezeActiveCard();
      renderCharter(d.charter.charter, d.applied_fields);
    }
  }

  if (doc.status === 'done' && doc.charter) {
    renderCharter(doc.charter.charter, doc.applied_fields);
  } else if (!doc.messages.length) {
    setWaiting(true, 'המראיין מכין את שאלות הפתיחה…');
    try { await api.post(`/surveys/${sid}/interview/start`); } catch (err) {
      setWaiting(false);
      bubble('assistant', `לא ניתן לפתוח את הראיון: ${err.detail || 'שגיאה'}`);
    }
  } else if (doc.busy) {
    setWaiting(true);
  }

  /* ---------- send / finish ---------- */
  async function sendText(text) {
    if (!text || waiting) return;
    setWaiting(true);
    try {
      await api.post(`/surveys/${sid}/interview/message`, { text });
      freezeActiveCard();               // the questions were answered
      bubble('user', text);
      rendered += 1;                    // the server appends this same message
      msgBox.value = '';
      setWaiting(true);                 // re-show typing (bubble scrolled it)
    } catch (err) {
      setWaiting(false);
      toast(err.detail || 'שליחה נכשלה', '⚠');
    }
  }
  sendBtn.addEventListener('click', () => sendText(msgBox.value.trim()));
  msgBox.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendText(msgBox.value.trim()); }
  });

  finishBtn.addEventListener('click', async () => {
    if (waiting) return;
    setWaiting(true, 'מגבש את אמנת המחקר מכל הראיון…');
    try {
      await api.post(`/surveys/${sid}/interview/finish`);
    } catch (err) {
      setWaiting(false);
      toast(err.detail || 'הפקת האמנה נכשלה', '⚠');
    }
  });
  container.querySelector('#skipBtn').addEventListener('click', () => navigate(`#/s/${sid}/toc`));

  /* ---------- SSE (handlers only re-sync — rendering is state-driven) ----- */
  const close = subscribe(sid, {
    interview: () => refreshChat(),
    interview_done: () => { toast('אמנת המחקר הופקה ושולבה בהגדרה'); refreshChat(); },
    interview_error: (d) => {
      setWaiting(false);
      bubble('assistant', `⚠ תקלה: ${d.message || 'שגיאה'} — במצב native ודאי שסשן הגשר פתוח, ונסי שוב.`);
    },
  });

  return () => close();
}

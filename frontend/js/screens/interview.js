/* Screen 1.5 — Deep Interview (M8): an open-ended chat with the interviewer
 * before the pipeline runs. Turns go through the LLM gateway (in native mode
 * — the user's own Claude Code session serves them via the bridge). Finishing
 * distills a research charter that is merged into the brief and steers every
 * later stage. */

import { api } from '../api.js';
import { subscribe } from '../sse.js';
import { esc } from '../app.js';

export async function render(container, { sid, navigate, toast }) {
  container.innerHTML = `
    <div class="page-head">
      <div><h1>🎙 ראיון עומק</h1>
        <p>ככל שתספרי יותר — הסקר יהיה מדויק יותר. אין הגבלת זמן: המראיין
        ישאל, יעמיק ויסכם, ובסיום תופק "אמנת מחקר" שתנחה את כל שלבי הכתיבה.</p></div>
      <div style="display:flex;gap:10px">
        <button class="btn" id="skipBtn">דלג לתוכן עניינים</button>
        <button class="btn cta" id="finishBtn">✔ סיים ראיון והפק אמנה</button>
      </div>
    </div>

    <div id="bridgeHint"></div>

    <div class="card panel" style="padding:0;display:flex;flex-direction:column;height:min(62vh,640px)">
      <div class="chat" id="chat"></div>
      <div class="chat-input">
        <textarea id="msgBox" rows="2" placeholder="כתבי תשובה חופשית — אפשר באריכות…"></textarea>
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

  /* ---------- chat rendering ---------- */
  function bubble(role, text) {
    const div = document.createElement('div');
    div.className = `bubble ${role === 'user' ? 'user' : 'assistant'}`;
    div.innerHTML = esc(text).replace(/\n/g, '<br>');
    chat.appendChild(div);
    chat.scrollTop = chat.scrollHeight;
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
  doc.messages.forEach((m) => bubble(m.role, m.text));
  let rendered = doc.messages.length;   // idempotency cursor (SSE replays history)

  /* Re-sync from server state — safe under SSE replays and duplicates. */
  async function refreshChat() {
    let d;
    try { d = await api.get(`/surveys/${sid}/interview`); } catch { return; }
    for (let i = rendered; i < d.messages.length; i++) {
      bubble(d.messages[i].role, d.messages[i].text);
    }
    rendered = Math.max(rendered, d.messages.length);
    if (!d.busy) setWaiting(false);
    if (d.status === 'done' && d.charter) {
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
  async function send() {
    const text = msgBox.value.trim();
    if (!text || waiting) return;
    setWaiting(true);
    try {
      await api.post(`/surveys/${sid}/interview/message`, { text });
      bubble('user', text);
      rendered += 1;                    // the server appends this same message
      msgBox.value = '';
      setWaiting(true);                 // re-show typing (bubble scrolled it)
    } catch (err) {
      setWaiting(false);
      toast(err.detail || 'שליחה נכשלה', '⚠');
    }
  }
  sendBtn.addEventListener('click', send);
  msgBox.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send(); }
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

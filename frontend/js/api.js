/* REST helper — same-origin `/api`, JSON in/out.
 * Every request carries the operator name (X-Operator) from localStorage.
 * On failure it throws `{status, detail, data}`; status 0 = network error. */

const BASE = '/api';
const OP_KEY = 'litreview.operator';

export function getOperator() {
  try { return localStorage.getItem(OP_KEY) || ''; } catch { return ''; }
}

export function setOperator(name) {
  try { localStorage.setItem(OP_KEY, name || ''); } catch { /* storage blocked */ }
}

/* Header values must be ByteStrings — percent-encode non-ASCII names. */
function headerSafe(value) {
  return /[^\t\x20-\x7e]/.test(value) ? encodeURIComponent(value) : value;
}

async function request(method, path, body) {
  const headers = { Accept: 'application/json' };
  const op = getOperator();
  if (op) headers['X-Operator'] = headerSafe(op);
  const init = { method, headers };
  if (body !== undefined) {
    headers['Content-Type'] = 'application/json';
    init.body = JSON.stringify(body);
  }

  let res;
  try {
    res = await fetch(BASE + path, init);
  } catch {
    throw { status: 0, detail: 'שגיאת רשת — השרת אינו זמין', data: null };
  }

  let data = null;
  const text = await res.text();
  if (text) {
    try { data = JSON.parse(text); } catch { data = text; }
  }
  if (!res.ok) {
    const detail = (data && typeof data === 'object' && data.detail)
      ? String(data.detail) : `שגיאה ${res.status}`;
    throw { status: res.status, detail, data };
  }
  return data;
}

export const api = {
  get: (path) => request('GET', path),
  post: (path, body) => request('POST', path, body === undefined ? {} : body),
  put: (path, body) => request('PUT', path, body),
  patch: (path, body) => request('PATCH', path, body),
  del: (path) => request('DELETE', path),
};

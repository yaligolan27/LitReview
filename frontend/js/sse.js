/* SSE subscription for `/api/surveys/{sid}/events`.
 *
 *   const close = subscribe(sid, { log(data){…}, stage_done(data){…} });
 *   …
 *   close();   // on unmount
 *
 * Handlers are keyed by event type and receive the parsed JSON payload.
 * Reconnection (with Last-Event-ID replay) is native EventSource behavior. */

const EVENT_TYPES = [
  'stage_started', 'progress', 'log', 'stage_done', 'stage_skipped',
  'stage_failed', 'gate_reached', 'run_done', 'run_error',
  'interview', 'interview_done', 'interview_error',
];

export function subscribe(sid, handlers = {}) {
  const es = new EventSource(`/api/surveys/${encodeURIComponent(sid)}/events`);

  for (const type of EVENT_TYPES) {
    es.addEventListener(type, (ev) => {
      const fn = handlers[type];
      if (!fn) return;
      let data = {};
      if (ev.data) {
        try { data = JSON.parse(ev.data); } catch { data = { raw: ev.data }; }
      }
      try { fn(data, ev); } catch (err) { console.error('SSE handler failed:', type, err); }
    });
  }
  if (handlers.open) es.addEventListener('open', handlers.open);
  if (handlers.error) es.addEventListener('error', handlers.error);

  return () => es.close();
}

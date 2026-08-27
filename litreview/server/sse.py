"""Per-survey SSE event bus: ring buffer with sequence ids, subscriber
queues, and Last-Event-ID replay (plan §3)."""

from __future__ import annotations

import json
import queue
import threading
from typing import Any, Iterator

RING_SIZE = 2000
HEARTBEAT_SECONDS = 15.0


class _SurveyLog:
    def __init__(self) -> None:
        self.events: list[dict[str, Any]] = []
        self.seq = 0
        self.subscribers: list[queue.Queue] = []
        self.lock = threading.Lock()

    def append(self, type: str, data: dict[str, Any]) -> None:
        with self.lock:
            self.seq += 1
            event = {"id": self.seq, "type": type, "data": data}
            self.events.append(event)
            if len(self.events) > RING_SIZE:
                self.events = self.events[-RING_SIZE:]
            for q in list(self.subscribers):
                try:
                    q.put_nowait(event)
                except queue.Full:
                    pass


class BusEmitter:
    """ProgressEmitter implementation writing into the bus."""

    def __init__(self, log: _SurveyLog):
        self._log = log

    def emit(self, type: str, **data: Any) -> None:
        self._log.append(type, data)


class EventBus:
    def __init__(self) -> None:
        self._logs: dict[str, _SurveyLog] = {}
        self._lock = threading.Lock()

    def _log_for(self, sid: str) -> _SurveyLog:
        with self._lock:
            if sid not in self._logs:
                self._logs[sid] = _SurveyLog()
            return self._logs[sid]

    def emitter(self, sid: str) -> BusEmitter:
        return BusEmitter(self._log_for(sid))

    def stream(self, sid: str, last_event_id: int = 0) -> Iterator[str]:
        """Yields SSE-formatted lines: replay after last_event_id, then live."""
        log = self._log_for(sid)
        q: queue.Queue = queue.Queue(maxsize=1000)
        with log.lock:
            backlog = [e for e in log.events if e["id"] > last_event_id]
            log.subscribers.append(q)
        try:
            for event in backlog:
                yield _format(event)
            while True:
                try:
                    event = q.get(timeout=HEARTBEAT_SECONDS)
                except queue.Empty:
                    yield ": heartbeat\n\n"
                    continue
                yield _format(event)
        finally:
            with log.lock:
                if q in log.subscribers:
                    log.subscribers.remove(q)


def _format(event: dict[str, Any]) -> str:
    payload = json.dumps(event["data"], ensure_ascii=False)
    return f"id: {event['id']}\nevent: {event['type']}\ndata: {payload}\n\n"

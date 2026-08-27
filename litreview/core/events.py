"""Progress events — one emitter protocol for CLI stdout and server SSE."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Protocol


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class ProgressEmitter(Protocol):
    def emit(self, type: str, **data: Any) -> None: ...


class NullEmitter:
    def emit(self, type: str, **data: Any) -> None:
        pass


class StdoutEmitter:
    """Human-readable progress lines for CLI runs."""

    ICONS = {
        "stage_started": "▶",
        "stage_done": "✓",
        "stage_failed": "✗",
        "stage_skipped": "↷",
        "gate_reached": "⏸",
        "log": "·",
        "progress": "…",
        "run_done": "🏁",
        "error": "‼",
    }

    def emit(self, type: str, **data: Any) -> None:
        icon = self.ICONS.get(type, "·")
        stage = data.get("stage", "")
        message = data.get("message", "")
        extra = ""
        if type == "stage_done" and "duration" in data:
            extra = f" ({data['duration']:.1f}s)"
        elif type == "gate_reached":
            message = f"waiting for approval: {data.get('gate', '')}"
        elif type == "progress" and "detail" in data:
            message = str(data["detail"])
        print(f"{icon} {stage:<14} {message}{extra}".rstrip(), flush=True)


class FanoutEmitter:
    def __init__(self, *emitters: ProgressEmitter):
        self.emitters = [e for e in emitters if e is not None]

    def emit(self, type: str, **data: Any) -> None:
        for e in self.emitters:
            e.emit(type, **data)


class MemoryEmitter:
    """Collects events (tests; also backs the server's SSE ring buffer)."""

    def __init__(self) -> None:
        self.events: list[dict[str, Any]] = []

    def emit(self, type: str, **data: Any) -> None:
        self.events.append({"type": type, "at": _now(), **data})

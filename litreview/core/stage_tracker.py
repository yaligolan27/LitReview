"""Stage execution wrapper — spec §10 ("למה שום שלב לא נעלם").

Runs each stage with critical/non-critical semantics, validates output,
emits progress events, and appends to a real-time ``stage_log.json`` that
survives crashes (flushed after every change).
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Callable

from .events import NullEmitter, ProgressEmitter


class StageFailed(RuntimeError):
    def __init__(self, stage: str, message: str):
        super().__init__(f"critical stage '{stage}' failed: {message}")
        self.stage = stage


class StageValidationError(RuntimeError):
    pass


# --- validators (spec §10) -------------------------------------------------


def val_papers(result: Any) -> tuple[bool, str]:
    papers = getattr(result, "papers", result)
    n = len(papers or [])
    return (n > 0, f"{n} papers")


def val_papers_after_audit(result: Any) -> tuple[bool, str]:
    if result is None:
        return (False, "auditor returned None")
    papers = getattr(result, "papers", result)
    n = len(papers or [])
    return (n > 0, f"{n} papers after audit")


def val_sections(result: Any) -> tuple[bool, str]:
    sections = getattr(result, "sections", result) or []
    if not sections:
        return (False, "no sections written")
    too_short = [s.title for s in sections if len(getattr(s, "content", "")) < 150]
    if too_short:
        return (False, f"sections under 150 chars: {too_short}")
    with_cites = sum(1 for s in sections if "[" in getattr(s, "content", ""))
    if with_cites * 2 < len(sections):
        return (False, "most sections have no citations")
    return (True, f"{len(sections)} sections")


def val_executive(result: Any) -> tuple[bool, str]:
    text = result if isinstance(result, str) else getattr(result, "executive_summary", "")
    return (len(text or "") >= 100, f"{len(text or '')} chars")


def val_html(result: Any) -> tuple[bool, str]:
    path = Path(str(result))
    if not path.exists():
        return (False, f"missing file {path}")
    size = path.stat().st_size
    return (size >= 2000, f"{size} bytes")


# --- tracker ---------------------------------------------------------------


class StageTracker:
    def __init__(self, log_path: str | Path | None = None,
                 emitter: ProgressEmitter | None = None):
        self.log_path = Path(log_path) if log_path else None
        self.emitter = emitter or NullEmitter()
        self.records: list[dict[str, Any]] = []

    def _flush(self) -> None:
        if self.log_path is None:
            return
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        self.log_path.write_text(
            json.dumps(self.records, ensure_ascii=False, indent=1), encoding="utf-8"
        )

    def run(self, name: str, fn: Callable[..., Any], *args: Any,
            critical: bool = True,
            validate: Callable[[Any], tuple[bool, str]] | None = None,
            **kwargs: Any) -> Any:
        record: dict[str, Any] = {"stage": name, "status": "running",
                                  "started": time.time(), "critical": critical}
        self.records.append(record)
        self._flush()
        self.emitter.emit("stage_started", stage=name)
        t0 = time.monotonic()
        try:
            result = fn(*args, **kwargs)
            if validate is not None:
                ok, msg = validate(result)
                record["validation"] = msg
                if not ok:
                    raise StageValidationError(msg)
        except Exception as exc:  # noqa: BLE001 — fail-safe grading is the point
            record["status"] = "failed"
            record["error"] = f"{type(exc).__name__}: {exc}"
            record["duration"] = time.monotonic() - t0
            self._flush()
            if critical:
                self.emitter.emit("stage_failed", stage=name, message=str(exc))
                raise StageFailed(name, str(exc)) from exc
            self.emitter.emit("log", stage=name, level="warn",
                              message=f"non-critical stage failed: {exc}")
            return None
        record["status"] = "done"
        record["duration"] = time.monotonic() - t0
        self._flush()
        self.emitter.emit("stage_done", stage=name, duration=record["duration"],
                          message=record.get("validation", ""))
        return result

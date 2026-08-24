"""Background job runner — one active job per survey (plan §2).

Runs orchestrator segments in a thread with the ServerGatePolicy: the run
pauses at unapproved gates, checkpoints survive restarts, and every event
streams to the SSE bus. Also runs the draft rewrite round (writer→grounder→
reviewer for selected chapters with pinned instructions).
"""

from __future__ import annotations

import threading
from datetime import datetime, timezone
from typing import Any

from ..agents import claim_grounder, critical_reviewer, writer
from ..config import get_settings
from ..core import orchestrator
from ..core.checkpoints import RunRecord
from ..core.context import RunContext
from ..core.llm import LLM
from ..core.state import SurveyState
from .sse import EventBus
from .store import SurveyStore

# Stages invalidated when upstream human edits arrive (plan §2.2).
S2_ONWARD = [sid for seg, ids, _ in orchestrator.SEGMENTS
             for sid in ids if seg != "S1_PLAN"]
S3_ONWARD = [sid for seg, ids, _ in orchestrator.SEGMENTS
             for sid in ids if seg in ("S3_WRITE", "S4_FINALIZE")]
S4_STAGES = [sid for seg, ids, _ in orchestrator.SEGMENTS
             for sid in ids if seg == "S4_FINALIZE"]

STAGE_TITLES = {
    "plan": "מתכנן המחקר", "toc": "תוכן עניינים", "hunt": "צייד המקורות",
    "audit": "מבקר האמינות", "fulltext": "טקסט מלא", "deep_research": "מחקר עומק",
    "write": "כתיבת הפרקים", "ground": "עיגון טענות", "review": "ביקורת",
    "fix_loop": "לולאת תיקון", "executive": "תקציר מנהלים",
    "edit_language": "עריכת לשון", "citations": "סידור ציטוטים",
    "visualize": "גרפים", "ideation": "רעיונות", "glossary": "מילון מונחים",
    "evaluate": "הערכה",
    "html": "הרכבת המסמך", "extras": "פלטים נוספים",
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class JobRunner:
    def __init__(self, store: SurveyStore, bus: EventBus):
        self.store = store
        self.bus = bus
        self._threads: dict[str, threading.Thread] = {}
        self._lock = threading.Lock()

    def is_running(self, sid: str) -> bool:
        thread = self._threads.get(sid)
        return thread is not None and thread.is_alive()

    def _context(self, sid: str) -> RunContext:
        workdir = self.store.vdir(sid)
        settings = get_settings()
        return RunContext(
            settings=settings,
            llm=LLM(settings, bridge_dir=workdir / "bridge"),
            workdir=workdir,
            emitter=self.bus.emitter(sid),
        )

    def _phase_status(self, run: RunRecord) -> str:
        gates = run.gates
        if gates.get("toc", {}).get("status") != "approved":
            return "collecting"      # about to run S1→gate (rare via jobs)
        if gates.get("sources", {}).get("status") != "approved":
            return "collecting"
        if gates.get("draft", {}).get("status") != "approved":
            return "writing"
        return "finalizing"

    # --- main pipeline job -------------------------------------------------

    def start(self, sid: str) -> bool:
        with self._lock:
            if self.is_running(sid):
                return False
            state = self.store.load_state(sid)
            run = self.store.load_run(sid) or RunRecord(run_id=sid)
            if state is None:
                raise ValueError("survey has no state — build the TOC first")
            self.store.set_status(sid, self._phase_status(run))
            thread = threading.Thread(target=self._run_pipeline,
                                      args=(sid, state, run), daemon=True)
            self._threads[sid] = thread
            thread.start()
            return True

    def _run_pipeline(self, sid: str, state: SurveyState, run: RunRecord) -> None:
        ctx = self._context(sid)
        checkpointer = self.store.checkpointer(sid)
        brief = self.store.load_brief(sid) or {}
        stages = orchestrator.build_stages(brief)
        try:
            outcome = orchestrator.run(ctx, state, run, checkpointer,
                                       orchestrator.ServerGatePolicy(), stages)
        except Exception as exc:  # noqa: BLE001
            self.store.set_status(sid, "failed")
            ctx.emitter.emit("run_error", message=str(exc))
            return
        if outcome == "done":
            self.store.set_status(sid, "done")
            ctx.emitter.emit("run_done")
        elif outcome.startswith("paused:"):
            gate = outcome.split(":", 1)[1]
            self.store.set_status(sid, f"{gate}_pending")

    # --- rewrite job -------------------------------------------------------

    def rewrite(self, sid: str, chapter_indexes: list[int]) -> bool:
        with self._lock:
            if self.is_running(sid):
                return False
            thread = threading.Thread(target=self._run_rewrite,
                                      args=(sid, chapter_indexes), daemon=True)
            self._threads[sid] = thread
            thread.start()
            return True

    def _run_rewrite(self, sid: str, chapter_indexes: list[int]) -> None:
        ctx = self._context(sid)
        state = self.store.load_state(sid)
        run = self.store.load_run(sid) or RunRecord(run_id=sid)
        overlay = self.store.load_overlay(sid)
        if state is None:
            return
        try:
            targets = []
            for index in chapter_indexes:
                if not 1 <= index <= len(state.sections):
                    continue
                sec = state.sections[index - 1]
                targets.append(sec)
                feedback_lines = [critical_reviewer.build_feedback(sec)]
                pins = overlay.get("pins", {}).get(str(index), [])
                open_pins = [p for p in pins if p.get("status") == "open"]
                for i, pin in enumerate(open_pins, start=1):
                    feedback_lines.append(f"- הוראת מפעיל {i}: {pin['text']}")
                ctx.emitter.emit("stage_started", stage="write")
                ctx.emitter.emit("log", stage="write", level="info",
                                 message=f"rewriting chapter {index}: {sec.title}")
                writer.revise_section(ctx, state, sec, "\n".join(feedback_lines), index)
                for pin in open_pins:
                    pin["status"] = "resolved"
                    pin["resolved_at"] = _now()
            if targets:
                claim_grounder.run_claim_grounder(ctx, state, only_sections=targets)
                critical_reviewer.run_critical_reviewer(ctx, state)
                run.invalidate(S4_STAGES)
                run.gates["draft"] = {"status": "pending", "decided_by": "",
                                      "at": _now(), "notes": "rewrite round"}
            self.store.checkpointer(sid).save(state, run)
            self.store.save_overlay(sid, overlay)
            self.store.set_status(sid, "draft_pending")
            ctx.emitter.emit("run_done")
        except Exception as exc:  # noqa: BLE001
            ctx.emitter.emit("run_error", message=str(exc))

    # --- invalidation helpers ---------------------------------------------

    def invalidate_after_toc_edit(self, sid: str) -> None:
        run = self.store.load_run(sid)
        if run is None:
            return
        if run.gates.get("toc", {}).get("status") == "approved":
            run.invalidate(S2_ONWARD)
            for gate in ("sources", "draft"):
                if gate in run.gates:
                    run.gates[gate] = {"status": "pending", "decided_by": "",
                                       "at": _now(), "notes": "TOC edited"}
            self.store.save_run(sid, run)

    def invalidate_after_source_edit(self, sid: str) -> None:
        run = self.store.load_run(sid)
        if run is None:
            return
        if run.gates.get("sources", {}).get("status") == "approved":
            run.invalidate(S3_ONWARD)
            if "draft" in run.gates:
                run.gates["draft"] = {"status": "pending", "decided_by": "",
                                      "at": _now(), "notes": "sources edited"}
            self.store.save_run(sid, run)

    def invalidate_finalize(self, sid: str, note: str) -> None:
        run = self.store.load_run(sid)
        if run is None:
            return
        run.invalidate(S4_STAGES)
        self.store.save_run(sid, run)

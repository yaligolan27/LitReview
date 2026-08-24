"""The orchestration layer — stage registry, segments, gates (spec §6, §9.0).

Stages are grouped into four segments separated by human approval gates
(TOC / sources / draft — the three gates of the product mockup). One
``GatePolicy`` abstraction serves all three frontends:

* ``AutoApprovePolicy``  — mock runs / tests / CI: approve and continue.
* ``BridgeGatePolicy``   — CLI native mode: the TOC gate goes through the
  bridge (purpose=toc_review) exactly as in the spec — including the fix for
  the "added chapters are ignored" bug: a JSON reply *replaces* the TOC and
  new chapters get keywords_en backfilled, entering assignment and writing.
* ``ServerGatePolicy``   — the web app: pause the run and wait for the
  approval endpoint (M4).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable, Protocol

from ..agents import (
    claim_grounder,
    critical_reviewer,
    reliability_auditor,
    research_planner,
    source_hunter,
    toc_architect,
    writer,
)
from ..agents.evaluator import run_evaluator
from ..agents.executive_translator import run_executive_translator
from ..agents.exports import run_extras
from ..agents.hebrew_editor import run_hebrew_editor
from ..agents.html_generator import run_html_generator
from ..agents.ideation_engine import run_ideation_engine
from ..agents.visualizer import run_visualizer
from .checkpoints import Checkpointer, RunRecord
from .citation_manager import run_citation_manager
from .context import RunContext
from .fulltext import run_fulltext
from .llm import extract_json
from .stage_tracker import (
    StageFailed,
    StageTracker,
    val_executive,
    val_html,
    val_papers,
    val_papers_after_audit,
    val_sections,
)
from .state import SurveyState, TocEntry

GATE_TOC = "toc"
GATE_SOURCES = "sources"
GATE_DRAFT = "draft"


class GateReached(Exception):
    def __init__(self, gate: str):
        super().__init__(f"gate reached: {gate}")
        self.gate = gate


class GatePolicy(Protocol):
    def on_gate(self, ctx: RunContext, state: SurveyState,
                run: RunRecord, gate: str) -> None: ...


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _approve(run: RunRecord, gate: str, decided_by: str, notes: str = "") -> None:
    run.gates[gate] = {"status": "approved", "decided_by": decided_by,
                       "at": _utcnow(), "notes": notes}


class AutoApprovePolicy:
    def on_gate(self, ctx: RunContext, state: SurveyState,
                run: RunRecord, gate: str) -> None:
        _approve(run, gate, decided_by="auto")
        state.log("gate", f"gate '{gate}' auto-approved")


class ServerGatePolicy:
    def on_gate(self, ctx: RunContext, state: SurveyState,
                run: RunRecord, gate: str) -> None:
        if run.gates.get(gate, {}).get("status") == "approved":
            return
        run.gates[gate] = {"status": "pending", "decided_by": "", "at": _utcnow(), "notes": ""}
        ctx.emitter.emit("gate_reached", gate=gate)
        raise GateReached(gate)


class BridgeGatePolicy:
    """CLI native mode. TOC always goes through the bridge; the sources and
    draft gates default to auto-approve (matching the original tool) and can
    be routed through the bridge with SURVEY_GATE_SOURCES/DRAFT=bridge."""

    def on_gate(self, ctx: RunContext, state: SurveyState,
                run: RunRecord, gate: str) -> None:
        if run.gates.get(gate, {}).get("status") == "approved":
            return
        if gate == GATE_TOC:
            self._toc_review(ctx, state)
            _approve(run, gate, decided_by="bridge")
            return
        setting = ctx.settings.gate_sources if gate == GATE_SOURCES else ctx.settings.gate_draft
        if setting == "bridge":
            purpose = "sources_review" if gate == GATE_SOURCES else "draft_review"
            summary = _gate_summary(state, gate)
            ctx.llm.complete(summary, purpose=purpose,
                             system="חובה להציג את התוכן למשתמש בשיחה ולחכות לאישורו לפני מענה.")
        _approve(run, gate, decided_by="bridge" if setting == "bridge" else "auto")

    def _toc_review(self, ctx: RunContext, state: SurveyState) -> None:
        toc_json = json.dumps(
            [{"chapter": t.chapter, "sections": t.sections} for t in state.toc],
            ensure_ascii=False, indent=1)
        prompt = (
            "להלן תוכן העניינים המוצע לסקר. חובה להציג אותו למשתמש בשיחה ולחכות "
            "לתשובתו. אם המשתמש מאשר — השב 'approved'. אם המשתמש מבקש שינויים "
            "(כולל הוספת פרקים) — השב JSON מלא של תוכן העניינים המעודכן בפורמט "
            '[{"chapter": "...", "sections": ["..."]}].\n\n' + toc_json
        )
        reply = ctx.llm.complete(prompt, purpose="toc_review",
                                 system="אתה מתווך אישור אנושי. אל תאשר בעצמך.")
        normalized = reply.strip().lower()
        if normalized in ("approved", "אושר", "מאושר") or normalized.startswith("approved"):
            state.log("gate", "TOC approved via bridge")
            return
        try:
            data = extract_json(reply)
            assert isinstance(data, list) and data
            new_toc = [TocEntry(chapter=str(item.get("chapter", "")).strip(),
                                sections=[str(s) for s in item.get("sections", [])])
                       for item in data if str(item.get("chapter", "")).strip()]
            assert new_toc
        except (ValueError, AssertionError):
            state.log("gate", "TOC reply not parseable — keeping original (fail-safe)")
            return
        state.toc = new_toc
        # Bug fix (spec §16): chapters added at the gate get keywords and are
        # fully part of assignment + writing.
        toc_architect.run_toc_architect(ctx, state)
        state.log("gate", "TOC replaced by user edit via bridge", chapters=len(state.toc))


def _gate_summary(state: SurveyState, gate: str) -> str:
    if gate == GATE_SOURCES:
        lines = [f"נמצאו {len(state.papers)} מקורות. חובה להציג למשתמש ולחכות לאישור:"]
        for p in state.papers[:40]:
            lines.append(f"- {p.title} ({p.year}) · {p.confidence} · DOI: {p.doi or '—'}")
        return "\n".join(lines)
    lines = [f"נכתבו {len(state.sections)} פרקים. חובה להציג למשתמש ולחכות לאישור:"]
    for s in state.sections:
        lines.append(f"- {s.title}: {len(s.content)} תווים, {len(s.issues)} הערות ביקורת")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Stage registry
# ---------------------------------------------------------------------------


@dataclass
class StageSpec:
    id: str
    title: str
    fn: Callable[[RunContext, SurveyState], Any]
    critical: bool = True
    validate: Callable[[Any], tuple[bool, str]] | None = None


# (segment id, [stage ids], gate after segment or None)
SEGMENTS: list[tuple[str, list[str], str | None]] = [
    ("S1_PLAN", ["plan", "toc"], GATE_TOC),
    ("S2_COLLECT", ["hunt", "audit"], GATE_SOURCES),
    ("S3_WRITE", ["fulltext", "deep_research", "write", "ground", "review", "fix_loop"],
     GATE_DRAFT),
    ("S4_FINALIZE", ["executive", "edit_language", "citations", "visualize",
                     "ideation", "evaluate", "html", "extras"], None),
]

ALL_STAGE_IDS = [sid for _, ids, _ in SEGMENTS for sid in ids]


def _stub(stage_id: str, arrives: str):
    def run_stub(ctx: RunContext, state: SurveyState) -> SurveyState:
        state.log(stage_id, f"stage not implemented yet (arrives in {arrives}) — skipped")
        return state
    return run_stub


def _run_fix_loop(ctx: RunContext, state: SurveyState) -> SurveyState:
    rounds_used = 0
    for _ in range(ctx.settings.max_fix_rounds):
        problematic = [(i + 1, s) for i, s in enumerate(state.sections) if s.issues]
        if not problematic:
            break
        rounds_used += 1
        for chapter_no, sec in problematic:
            feedback = critical_reviewer.build_feedback(sec)
            writer.revise_section(ctx, state, sec, feedback, chapter_no)
        claim_grounder.run_claim_grounder(ctx, state,
                                          only_sections=[s for _, s in problematic])
        critical_reviewer.run_critical_reviewer(ctx, state)
    remaining = sum(len(s.issues) for s in state.sections)
    state.log("fix_loop", "fix loop finished",
              rounds=rounds_used, remaining_issues=remaining)
    return state


def build_stages(config: dict[str, Any]) -> dict[str, StageSpec]:
    return {spec.id: spec for spec in [
        StageSpec("plan", "Research Planner",
                  lambda ctx, s: research_planner.run_research_planner(ctx, s, config),
                  critical=True),
        StageSpec("toc", "TOC Architect", toc_architect.run_toc_architect, critical=True),
        StageSpec("hunt", "Source Hunter", source_hunter.run_source_hunter,
                  critical=True, validate=val_papers),
        StageSpec("audit", "Reliability Auditor",
                  reliability_auditor.run_reliability_auditor,
                  critical=True, validate=val_papers_after_audit),
        StageSpec("fulltext", "Full-Text Retrieval", run_fulltext, critical=False),
        StageSpec("deep_research", "Deep Research", _stub("deep_research", "M5"),
                  critical=False),
        StageSpec("write", "Writer", writer.run_writer, critical=True,
                  validate=val_sections),
        StageSpec("ground", "Claim Grounder", claim_grounder.run_claim_grounder,
                  critical=True),
        StageSpec("review", "Critical Reviewer",
                  critical_reviewer.run_critical_reviewer, critical=False),
        StageSpec("fix_loop", "Writer↔Reviewer Loop", _run_fix_loop, critical=False),
        StageSpec("executive", "Executive Summary", run_executive_translator,
                  critical=True, validate=val_executive),
        StageSpec("edit_language", "Language Editor", run_hebrew_editor,
                  critical=False),
        StageSpec("citations", "Citation Manager", run_citation_manager, critical=True),
        StageSpec("visualize", "Visualizer", run_visualizer, critical=False),
        StageSpec("ideation", "Ideation Engine", run_ideation_engine, critical=False),
        StageSpec("evaluate", "Evaluator", run_evaluator, critical=False),
        StageSpec("html", "HTML Generator", run_html_generator, critical=True,
                  validate=val_html),
        StageSpec("extras", "DOCX/Slides/Podcast", run_extras, critical=False),
    ]}


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------


def run(ctx: RunContext, state: SurveyState, run_record: RunRecord,
        checkpointer: Checkpointer, gate_policy: GatePolicy,
        stages: dict[str, StageSpec], until: str | None = None) -> str:
    """Run all segments. Returns "done", "paused:<gate>" or raises StageFailed."""
    tracker = StageTracker(log_path=ctx.workdir / "stage_log.json", emitter=ctx.emitter)
    artifacts: dict[str, Any] = {}

    for segment_id, stage_ids, gate in SEGMENTS:
        for stage_id in stage_ids:
            spec = stages[stage_id]
            if run_record.is_done(stage_id):
                ctx.emitter.emit("stage_skipped", stage=stage_id,
                                 message="already completed (resume)")
                continue
            run_record.mark(stage_id, "running")
            checkpointer.save(state, run_record)
            try:
                result = tracker.run(stage_id, spec.fn, ctx, state,
                                     critical=spec.critical, validate=spec.validate)
            except StageFailed:
                run_record.mark(stage_id, "failed")
                checkpointer.save(state, run_record)
                raise
            if result is None and not spec.critical:
                run_record.mark(stage_id, "failed")   # retried on next resume
            else:
                run_record.mark(stage_id, "done")
            if stage_id == "html" and result:
                artifacts["html"] = result
            checkpointer.save(state, run_record)

        if gate is not None:
            if until == gate:
                run_record.gates.setdefault(
                    gate, {"status": "pending", "decided_by": "", "at": _utcnow(),
                           "notes": "stopped by --until"})
                checkpointer.save(state, run_record)
                ctx.emitter.emit("gate_reached", gate=gate)
                return f"paused:{gate}"
            try:
                gate_policy.on_gate(ctx, state, run_record, gate)
            except GateReached:
                checkpointer.save(state, run_record)
                return f"paused:{gate}"
            checkpointer.save(state, run_record)

    ctx.emitter.emit("run_done", segment="all", artifacts=artifacts)
    return "done"

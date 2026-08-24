"""All /api routes (contract: docs/API.md)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Header, HTTPException, Request
from fastapi.responses import FileResponse, StreamingResponse

from .. import __version__
from ..agents import research_planner, toc_architect
from ..agents.claim_grounder import _build_report as rebuild_grounding_report
from ..agents.exports import build_docx, build_podcast_text, build_slides
from ..agents.html_generator import run_html_generator
from ..apis import crossref, registry
from ..config import get_settings
from ..core import markers, orchestrator
from ..core.checkpoints import RunRecord
from ..core.context import RunContext
from ..core.llm import LLM, extract_json
from ..core.state import CONFIDENCE_LEVELS, SurveyState, TocEntry
from .jobs import STAGE_TITLES, JobRunner
from .store import NotFound, SurveyStore

router = APIRouter()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _op(x_operator: str) -> str:
    """Operator names arrive URL-encoded (HTTP headers are latin-1 only)."""
    from urllib.parse import unquote
    return unquote(x_operator or "").strip()


def _store(request: Request) -> SurveyStore:
    return request.app.state.store


def _jobs(request: Request) -> JobRunner:
    return request.app.state.jobs


def _ctx(store: SurveyStore, sid: str) -> RunContext:
    settings = get_settings()
    workdir = store.vdir(sid)
    return RunContext(settings=settings, llm=LLM(settings, bridge_dir=workdir / "bridge"),
                      workdir=workdir)


def _get_state(store: SurveyStore, sid: str) -> SurveyState:
    state = store.load_state(sid)
    if state is None:
        raise HTTPException(409, "לסקר אין עדיין state — בנה תוכן עניינים תחילה")
    return state


def _manifest_or_404(store: SurveyStore, sid: str) -> dict:
    try:
        return store.get(sid)
    except NotFound:
        raise HTTPException(404, "סקר לא נמצא") from None


# ---------------------------------------------------------------------------
# Surveys & dashboard
# ---------------------------------------------------------------------------


@router.get("/surveys")
def list_surveys(request: Request):
    store = _store(request)
    cards = [store.card(m) for m in store.list()]
    stats = {
        "total": len(cards),
        "running": sum(1 for c in cards if c["status"] in
                       ("collecting", "writing", "finalizing")),
        "done": sum(1 for c in cards if c["status"] == "done"),
        "papers_analyzed": sum(c["sources_count"] for c in cards),
    }
    return {"surveys": cards, "stats": stats}


@router.post("/surveys")
def create_survey(request: Request, body: dict | None = None,
                  x_operator: str = Header(default="")):
    body = body or {}
    store = _store(request)
    manifest = store.create(topic=body.get("topic", ""),
                            operator=body.get("operator") or _op(x_operator))
    return store.card(manifest)


@router.get("/surveys/{sid}")
def get_survey(request: Request, sid: str):
    store = _store(request)
    return store.card(_manifest_or_404(store, sid))


@router.delete("/surveys/{sid}")
def delete_survey(request: Request, sid: str):
    store = _store(request)
    _manifest_or_404(store, sid)
    store.archive(sid)
    return {"ok": True}


@router.post("/surveys/{sid}/versions")
def create_version(request: Request, sid: str, body: dict | None = None):
    store = _store(request)
    _manifest_or_404(store, sid)
    manifest = store.new_version(sid, carry=(body or {}).get("carry", ["brief"]))
    return store.card(manifest)


@router.put("/gold-standard")
def set_gold(request: Request, body: dict):
    store = _store(request)
    sid = body.get("survey_id", "")
    _manifest_or_404(store, sid)
    store.set_gold(sid)
    return {"ok": True}


@router.get("/operators")
def list_operators(request: Request):
    return {"operators": _store(request).operators()}


@router.post("/operators")
def add_operator(request: Request, body: dict):
    name = str(body.get("name", "")).strip()
    if not name:
        raise HTTPException(422, "שם מפעיל ריק")
    return {"operators": _store(request).add_operator(name)}


@router.get("/meta")
def meta(request: Request):
    settings = get_settings()
    import os
    return {
        "backend": settings.llm_backend,
        "backends_available": {
            "mock": True,
            "native": True,
            "api": bool(os.environ.get("ANTHROPIC_API_KEY")),
        },
        "version": __version__,
    }


# ---------------------------------------------------------------------------
# Brief
# ---------------------------------------------------------------------------


@router.get("/surveys/{sid}/brief")
def get_brief(request: Request, sid: str):
    store = _store(request)
    _manifest_or_404(store, sid)
    return store.load_brief(sid) or {}


@router.put("/surveys/{sid}/brief")
def put_brief(request: Request, sid: str, body: dict):
    store = _store(request)
    _manifest_or_404(store, sid)
    store.save_brief(sid, body)
    return {"ok": True}


# ---------------------------------------------------------------------------
# TOC (gate 1)
# ---------------------------------------------------------------------------


def _toc_response(state: SurveyState) -> dict:
    count = len(state.toc)
    return {
        "chapters": [t.to_dict() for t in state.toc],
        "meter": {"count": count, "ok": count >= 8, "rule": "≥8"},
    }


@router.post("/surveys/{sid}/toc/build")
def build_toc(request: Request, sid: str):
    store = _store(request)
    _manifest_or_404(store, sid)
    brief = store.load_brief(sid)
    if not brief or not brief.get("topic"):
        raise HTTPException(409, "מלא את הגדרת הסקר (נושא) לפני בניית תוכן עניינים")
    ctx = _ctx(store, sid)
    state = SurveyState()
    try:
        research_planner.run_research_planner(ctx, state, brief)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from None
    toc_architect.run_toc_architect(ctx, state)
    run = RunRecord(run_id=sid, backend=ctx.settings.llm_backend,
                    bridge_dir=str(ctx.llm.bridge_dir))
    run.mark("plan", "running"); run.mark("plan", "done")
    run.mark("toc", "running"); run.mark("toc", "done")
    store.checkpointer(sid).save(state, run)
    store.set_status(sid, "toc_pending")
    return _toc_response(state)


@router.get("/surveys/{sid}/toc")
def get_toc(request: Request, sid: str):
    store = _store(request)
    _manifest_or_404(store, sid)
    state = store.load_state(sid)
    if state is None:
        return {"chapters": [], "meter": {"count": 0, "ok": False, "rule": "≥8"}}
    return _toc_response(state)


@router.put("/surveys/{sid}/toc")
def put_toc(request: Request, sid: str, body: dict):
    store = _store(request)
    state = _get_state(store, sid)
    chapters = body.get("chapters", [])
    state.toc = [TocEntry.from_dict(c) for c in chapters
                 if str(c.get("chapter", "")).strip()]
    toc_architect.backfill_keywords(state)   # deliberate empty TOC stays empty
    store.save_state(sid, state)
    _jobs(request).invalidate_after_toc_edit(sid)
    return _toc_response(state)


@router.post("/surveys/{sid}/toc/suggestions")
def toc_suggestions(request: Request, sid: str):
    store = _store(request)
    state = _get_state(store, sid)
    ctx = _ctx(store, sid)
    toc_lines = "\n".join(f"- {t.chapter}: {', '.join(t.sections)}" for t in state.toc)
    prompt = (
        f"נושא הסקר: {state.brief.topic} ({state.brief.search_topic})\n"
        f"תוכן העניינים הנוכחי:\n{toc_lines}\n\n"
        "הצע עד 3 פרקים או תתי-סעיפים חסרים שמרכזיים לנושא. החזר JSON: "
        '{"suggestions": [{"kind": "chapter"|"section", "title": "...", '
        '"parent": "שם פרק קיים או ריק", "reason": "..."}]}'
    )
    try:
        data = extract_json(ctx.llm.complete(prompt, purpose="toc_gaps"))
        suggestions = data.get("suggestions", []) if isinstance(data, dict) else []
    except Exception:  # noqa: BLE001
        suggestions = []
    return {"suggestions": suggestions[:5]}


@router.post("/surveys/{sid}/toc/approve")
def approve_toc(request: Request, sid: str, body: dict | None = None,
                x_operator: str = Header(default="")):
    store = _store(request)
    state = _get_state(store, sid)
    if not state.toc:
        raise HTTPException(409, "אי אפשר לאשר תוכן עניינים ריק")
    run = store.load_run(sid) or RunRecord(run_id=sid)
    run.gates["toc"] = {"status": "approved", "decided_by": _op(x_operator) or "operator",
                        "at": _now(), "notes": (body or {}).get("notes", "")}
    state.log("gate", f"TOC approved by {x_operator or 'operator'}",
              chapters=len(state.toc))
    store.checkpointer(sid).save(state, run)
    return {"ok": True}


# ---------------------------------------------------------------------------
# Sources (gate 2)
# ---------------------------------------------------------------------------


@router.post("/surveys/{sid}/sources/search")
def search_sources(request: Request, sid: str):
    store, jobs = _store(request), _jobs(request)
    state = _get_state(store, sid)
    run = store.load_run(sid) or RunRecord()
    if run.gates.get("toc", {}).get("status") != "approved":
        raise HTTPException(409, "אשר את תוכן העניינים לפני איסוף מקורות")
    if jobs.is_running(sid):
        raise HTTPException(409, "ריצה כבר פעילה עבור סקר זה")
    # A re-search re-runs hunt+audit even if previously done.
    run.invalidate(["hunt", "audit"])
    for entry in run.stages:
        if entry["id"] in ("hunt", "audit") and entry["status"] == "stale":
            entry["status"] = "pending"
    store.save_run(sid, run)
    jobs.start(sid)
    return {"job": "started"}


def _paper_row(paper, included: bool) -> dict:
    return {
        "paper_id": paper.id,
        "title": paper.title,
        "authors": ", ".join(paper.authors[:4]) + ("..." if len(paper.authors) > 4 else ""),
        "year": paper.year,
        "language": (paper.language or "en").upper()[:2],
        "citation_count": paper.citation_count,
        "confidence": paper.confidence or "EMERGING",
        "tier": paper.tier,
        "doi": paper.doi,
        "doi_verified": paper.doi_verified,
        "is_retracted": paper.is_retracted,
        "source": paper.source,
        "found_via": paper.found_via,
        "included": included,
    }


@router.get("/surveys/{sid}/sources")
def get_sources(request: Request, sid: str):
    store = _store(request)
    state = _get_state(store, sid)
    overlay = store.load_overlay(sid)
    decisions = overlay.get("source_decisions", {})
    run = store.load_run(sid)
    rows = []
    for paper in state.papers:
        default_included = not (paper.is_retracted or paper.doi_verified is False)
        included = decisions.get(paper.id, default_included)
        rows.append(_paper_row(paper, included))
    return {
        "papers": rows,
        "notices": {
            "doi_failed": sum(1 for p in state.papers if p.doi_verified is False),
            "retracted": sum(1 for p in state.papers if p.is_retracted),
        },
        "approved": bool(run and run.gates.get("sources", {}).get("status") == "approved"),
    }


@router.patch("/surveys/{sid}/sources")
def patch_sources(request: Request, sid: str, body: dict,
                  x_operator: str = Header(default="")):
    store = _store(request)
    _get_state(store, sid)
    overlay = store.load_overlay(sid)
    decisions = overlay.setdefault("source_decisions", {})
    for pid in body.get("include", []):
        decisions[str(pid)] = True
    for pid in body.get("exclude", []):
        decisions[str(pid)] = False
    overlay.setdefault("edit_log", []).append(
        {"what": "source_decisions", "by": _op(x_operator), "at": _now(),
         "include": len(body.get("include", [])), "exclude": len(body.get("exclude", []))})
    store.save_overlay(sid, overlay)
    return {"ok": True}


@router.post("/surveys/{sid}/sources/manual")
def add_manual_source(request: Request, sid: str, body: dict,
                      x_operator: str = Header(default="")):
    store = _store(request)
    state = _get_state(store, sid)
    ctx = _ctx(store, sid)
    doi = str(body.get("doi", "")).strip()
    title = str(body.get("title", "")).strip()
    paper = None
    if ctx.offline:
        raise HTTPException(422, "הוספת מקור ידני אינה זמינה במצב mock (אין רשת)")
    if doi:
        paper = crossref.fetch_by_doi(doi.split("doi.org/")[-1])
    elif title:
        candidates = crossref.search(title, limit=3)
        paper = candidates[0] if candidates else None
    if paper is None:
        raise HTTPException(422, "לא הצלחתי לאתר את המקור לפי הנתונים שסופקו")
    paper.found_via = "user"
    paper.tier = registry.tier_for("crossref")
    result = crossref.verify_doi(paper.doi) if paper.doi else {"checked": True, "valid": False}
    if result["checked"]:
        paper.doi_verified = result["valid"]
    from ..core.confidence_scorer import score_paper
    paper.confidence = score_paper(paper)
    state.papers.append(paper)
    state.log("sources", f"manual source added by {_op(x_operator)}", title=paper.title)
    store.save_state(sid, state)
    return _paper_row(paper, included=True)


@router.post("/surveys/{sid}/sources/approve")
def approve_sources(request: Request, sid: str, x_operator: str = Header(default="")):
    store = _store(request)
    state = _get_state(store, sid)
    overlay = store.load_overlay(sid)
    decisions = overlay.get("source_decisions", {})
    kept, excluded = [], []
    for paper in state.papers:
        default_included = not (paper.is_retracted or paper.doi_verified is False)
        if decisions.get(paper.id, default_included):
            kept.append(paper)
        else:
            excluded.append(paper)
    if not kept:
        raise HTTPException(409, "אי אפשר לאשר רשימת מקורות ריקה")
    state.papers = kept
    state.prisma["excluded_by_user"] = len(excluded)
    state.log("gate", f"sources approved by {x_operator or 'operator'}",
              kept=len(kept), excluded=len(excluded))
    run = store.load_run(sid) or RunRecord(run_id=sid)
    run.gates["sources"] = {"status": "approved", "decided_by": _op(x_operator) or "operator",
                            "at": _now(), "notes": ""}
    store.checkpointer(sid).save(state, run)
    store.set_status(sid, "sources_pending")
    return {"ok": True, "kept": len(kept), "excluded": len(excluded)}


# ---------------------------------------------------------------------------
# Run + SSE
# ---------------------------------------------------------------------------


@router.post("/surveys/{sid}/run/start")
def start_run(request: Request, sid: str):
    store, jobs = _store(request), _jobs(request)
    _get_state(store, sid)
    if jobs.is_running(sid):
        raise HTTPException(409, "ריצה כבר פעילה")
    started = jobs.start(sid)
    return {"job": "started" if started else "already-running"}


@router.get("/surveys/{sid}/run")
def get_run(request: Request, sid: str):
    store, jobs = _store(request), _jobs(request)
    _manifest_or_404(store, sid)
    run = store.load_run(sid)
    stage_rows = []
    by_id = {s["id"]: s for s in (run.stages if run else [])}
    for stage_id in orchestrator.ALL_STAGE_IDS:
        entry = by_id.get(stage_id, {"id": stage_id, "status": "pending",
                                     "started": "", "ended": "", "error": ""})
        stage_rows.append({**entry, "title": STAGE_TITLES.get(stage_id, stage_id)})
    done = sum(1 for s in stage_rows if s["status"] == "done")
    return {
        "stages": stage_rows,
        "gates": run.gates if run else {},
        "running": jobs.is_running(sid),
        "overall_pct": round(100 * done / len(stage_rows)),
        "backend": run.backend if run else get_settings().llm_backend,
        "bridge_dir": run.bridge_dir if run else "",
    }


@router.get("/surveys/{sid}/events")
def events(request: Request, sid: str,
           last_event_id: str = Header(default="0", alias="Last-Event-ID")):
    store = _store(request)
    _manifest_or_404(store, sid)
    try:
        last_id = int(last_event_id)
    except ValueError:
        last_id = 0
    bus = request.app.state.bus
    return StreamingResponse(bus.stream(sid, last_id), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache",
                                      "X-Accel-Buffering": "no"})


# ---------------------------------------------------------------------------
# Draft (gate 3)
# ---------------------------------------------------------------------------


def _claims_summary(sec) -> dict:
    summary = {"supported": 0, "uncertain": 0, "unsupported": 0}
    for claim in sec.claims:
        summary[claim.effective_status()] = summary.get(claim.effective_status(), 0) + 1
    return summary


@router.get("/surveys/{sid}/draft")
def get_draft(request: Request, sid: str):
    store = _store(request)
    state = _get_state(store, sid)
    overlay = store.load_overlay(sid)
    chapters = []
    for i, sec in enumerate(state.sections, start=1):
        pins = overlay.get("pins", {}).get(str(i), [])
        chapters.append({
            "index": i,
            "title": sec.title,
            "confidence": sec.effective_confidence(),
            "confidence_override": sec.confidence_override,
            "issues": len(sec.issues),
            "claims_summary": _claims_summary(sec),
            "user_edited": sec.user_edited,
            "stale_grounding": sec.stale_grounding,
            "pins": len([p for p in pins if p.get("status") == "open"]),
        })
    return {"chapters": chapters, "grounding_report": state.grounding_report}


@router.get("/surveys/{sid}/draft/chapters/{index}")
def get_chapter(request: Request, sid: str, index: int):
    store = _store(request)
    state = _get_state(store, sid)
    if not 1 <= index <= len(state.sections):
        raise HTTPException(404, "פרק לא נמצא")
    sec = state.sections[index - 1]
    overlay = store.load_overlay(sid)
    pins = overlay.get("pins", {}).get(str(index), [])
    return {
        "index": index,
        "title": sec.title,
        "confidence": sec.effective_confidence(),
        "confidence_override": sec.confidence_override,
        "content": sec.content,
        "claims": [c.to_dict() for c in sec.claims],
        "issues": sec.issues,
        "papers": [{"n": n + 1, "title": p.title, "apa": p.apa, "doi": p.doi}
                   for n, p in enumerate(sec.papers)],
        "pins": pins,
    }


@router.patch("/surveys/{sid}/draft/chapters/{index}")
def patch_chapter(request: Request, sid: str, index: int, body: dict,
                  x_operator: str = Header(default="")):
    store = _store(request)
    state = _get_state(store, sid)
    if not 1 <= index <= len(state.sections):
        raise HTTPException(404, "פרק לא נמצא")
    sec = state.sections[index - 1]
    new_content = str(body.get("content", ""))
    if not new_content.strip():
        raise HTTPException(422, "תוכן ריק")
    from collections import Counter
    import re as _re
    numbers_before = Counter(_re.findall(r"\d+(?:\.\d+)?%?", sec.content))
    numbers_after = Counter(_re.findall(r"\d+(?:\.\d+)?%?", new_content))
    warnings = []
    if numbers_before != numbers_after:
        warnings.append("שים לב: המספרים בטקסט השתנו — עיגון הטענות יידרש מחדש")
    lint = [{"level": i.level, "message": i.message}
            for i in markers.lint(new_content)]
    sec.content = new_content
    sec.user_edited = True
    sec.stale_grounding = True
    state.log("draft", f"chapter {index} edited by {_op(x_operator) or 'operator'}")
    store.save_state(sid, state)
    _jobs(request).invalidate_finalize(sid, "chapter edited")
    return {"lint": lint, "warnings": warnings}


@router.put("/surveys/{sid}/draft/chapters/{index}/confidence")
def put_chapter_confidence(request: Request, sid: str, index: int, body: dict,
                           x_operator: str = Header(default="")):
    store = _store(request)
    state = _get_state(store, sid)
    if not 1 <= index <= len(state.sections):
        raise HTTPException(404, "פרק לא נמצא")
    value = str(body.get("value", "")).upper().strip()
    sec = state.sections[index - 1]
    if not value:
        sec.confidence_override = None
    elif value in CONFIDENCE_LEVELS:
        sec.confidence_override = {"value": value, "by": _op(x_operator) or "operator",
                                   "at": _now(), "reason": body.get("reason", "")}
        state.log("draft", f"operator override: chapter {index} confidence "
                           f"{sec.confidence}→{value} ({_op(x_operator) or 'operator'})")
    else:
        raise HTTPException(422, f"רמת אמינות לא חוקית: {value}")
    store.save_state(sid, state)
    _jobs(request).invalidate_finalize(sid, "confidence override")
    return {"ok": True, "effective": sec.effective_confidence()}


@router.put("/surveys/{sid}/draft/claims/{claim_id}")
def put_claim(request: Request, sid: str, claim_id: str, body: dict,
              x_operator: str = Header(default="")):
    store = _store(request)
    state = _get_state(store, sid)
    status = str(body.get("status", "")).lower().strip()
    if status not in ("supported", "uncertain", "unsupported", ""):
        raise HTTPException(422, f"סטטוס לא חוקי: {status}")
    for sec in state.sections:
        for claim in sec.claims:
            if claim.id == claim_id:
                if status:
                    claim.status_override = {"value": status,
                                             "by": _op(x_operator) or "operator",
                                             "at": _now(),
                                             "reason": body.get("reason", "")}
                    state.log("draft", f"operator override: claim {claim_id} "
                                       f"{claim.status}→{status} ({_op(x_operator) or 'operator'})")
                else:
                    claim.status_override = None
                rebuild_grounding_report(state)
                store.save_state(sid, state)
                _jobs(request).invalidate_finalize(sid, "claim override")
                return {"ok": True, "effective": claim.effective_status()}
    raise HTTPException(404, "טענה לא נמצאה")


@router.post("/surveys/{sid}/draft/chapters/{index}/pins")
def add_pin(request: Request, sid: str, index: int, body: dict,
            x_operator: str = Header(default="")):
    store = _store(request)
    state = _get_state(store, sid)
    if not 1 <= index <= len(state.sections):
        raise HTTPException(404, "פרק לא נמצא")
    text = str(body.get("text", "")).strip()
    if not text:
        raise HTTPException(422, "הוראה ריקה")
    overlay = store.load_overlay(sid)
    pins = overlay.setdefault("pins", {}).setdefault(str(index), [])
    import uuid
    pin = {"id": uuid.uuid4().hex[:8], "text": text, "status": "open",
           "by": _op(x_operator) or "operator", "at": _now()}
    pins.append(pin)
    store.save_overlay(sid, overlay)
    return pin


@router.delete("/surveys/{sid}/draft/chapters/{index}/pins/{pin_id}")
def delete_pin(request: Request, sid: str, index: int, pin_id: str):
    store = _store(request)
    overlay = store.load_overlay(sid)
    pins = overlay.get("pins", {}).get(str(index), [])
    overlay["pins"][str(index)] = [p for p in pins if p.get("id") != pin_id]
    store.save_overlay(sid, overlay)
    return {"ok": True}


@router.post("/surveys/{sid}/draft/rewrite")
def rewrite(request: Request, sid: str, body: dict):
    store, jobs = _store(request), _jobs(request)
    _get_state(store, sid)
    chapters = [int(i) for i in body.get("chapters", [])]
    if not chapters:
        raise HTTPException(422, "בחר פרקים לכתיבה חוזרת")
    if not jobs.rewrite(sid, chapters):
        raise HTTPException(409, "ריצה כבר פעילה")
    return {"job": "started"}


@router.post("/surveys/{sid}/draft/approve")
def approve_draft(request: Request, sid: str, body: dict | None = None,
                  x_operator: str = Header(default="")):
    store = _store(request)
    state = _get_state(store, sid)
    overlay = store.load_overlay(sid)
    open_pins = []
    for chapter, pins in overlay.get("pins", {}).items():
        for pin in pins:
            if pin.get("status") == "open":
                open_pins.append({"chapter": chapter, "text": pin["text"]})
    if open_pins and not (body or {}).get("force"):
        raise HTTPException(409, detail={"message": "יש הוראות פתוחות שלא טופלו",
                                         "open_pins": open_pins})
    run = store.load_run(sid) or RunRecord(run_id=sid)
    run.gates["draft"] = {"status": "approved", "decided_by": _op(x_operator) or "operator",
                          "at": _now(), "notes": ""}
    state.log("gate", f"draft approved by {x_operator or 'operator'}",
              forced_over_pins=len(open_pins))
    store.checkpointer(sid).save(state, run)
    store.set_status(sid, "draft_pending")
    return {"ok": True}


# ---------------------------------------------------------------------------
# Exports
# ---------------------------------------------------------------------------

_EXPORT_PATTERNS = {"html": "survey_*.html", "pdf": "survey_*.pdf",
                    "docx": "survey_*.docx", "slides": "slides_*.md",
                    "podcast": "notebooklm_*.txt"}


def _pdf_available() -> bool:
    try:
        import playwright.sync_api  # noqa: F401
        return True
    except ImportError:
        return False


def _latest(store: SurveyStore, sid: str, fmt: str):
    files = sorted(store.outputs_dir(sid).glob(_EXPORT_PATTERNS[fmt]))
    return files[-1] if files else None


@router.get("/surveys/{sid}/exports")
def get_exports(request: Request, sid: str):
    store = _store(request)
    _manifest_or_404(store, sid)
    run = store.load_run(sid)
    finalize_stale = bool(run and any(
        s["status"] == "stale" for s in run.stages
        if s["id"] in ("html", "extras", "citations")))
    formats = []
    for fmt in _EXPORT_PATTERNS:
        path = _latest(store, sid, fmt)
        if fmt == "pdf" and not _pdf_available() and path is None:
            status = "unavailable"
        elif path is None:
            status = "idle"
        elif finalize_stale:
            status = "stale"
        else:
            status = "ready"
        formats.append({
            "format": fmt,
            "status": status,
            "bytes": path.stat().st_size if path else 0,
            "generated_at": _now() if path else "",
        })
    return {"formats": formats}


@router.post("/surveys/{sid}/exports")
def generate_exports(request: Request, sid: str, body: dict | None = None):
    store = _store(request)
    state = _get_state(store, sid)
    ctx = _ctx(store, sid)
    wanted = (body or {}).get("formats") or list(_EXPORT_PATTERNS)
    results: dict[str, Any] = {}
    for fmt in wanted:
        try:
            if fmt == "html":
                results[fmt] = run_html_generator(ctx, state)
            elif fmt == "docx":
                results[fmt] = build_docx(ctx, state)
            elif fmt == "slides":
                results[fmt] = build_slides(ctx, state)
            elif fmt == "podcast":
                results[fmt] = build_podcast_text(ctx, state)
            elif fmt == "pdf":
                results[fmt] = _print_pdf(store, ctx, state, sid)
        except Exception as exc:  # noqa: BLE001
            results[fmt] = f"error: {exc}"
    store.save_state(sid, state)
    return {"results": {k: str(v) for k, v in results.items()}}


def _print_pdf(store: SurveyStore, ctx, state, sid: str) -> str:
    if not _pdf_available():
        raise RuntimeError("PDF דורש Playwright + Chromium (התקן: pip install litreview[pdf])")
    html_path = _latest(store, sid, "html")
    if html_path is None:
        html_path = run_html_generator(ctx, state)
    from playwright.sync_api import sync_playwright
    pdf_path = store.outputs_dir(sid) / (Path(html_path).stem + ".pdf")
    import os
    executable = "/opt/pw-browsers/chromium" if os.path.exists("/opt/pw-browsers/chromium") else None
    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path=executable) if executable \
            else p.chromium.launch()
        page = browser.new_page()
        page.goto(f"file://{Path(html_path).resolve()}")
        page.wait_for_timeout(1200)
        page.pdf(path=str(pdf_path), format="A4",
                 margin={"top": "18mm", "bottom": "18mm",
                         "left": "16mm", "right": "16mm"})
        browser.close()
    return str(pdf_path)


from pathlib import Path  # noqa: E402

_MEDIA = {"html": "text/html", "pdf": "application/pdf",
          "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
          "slides": "text/markdown", "podcast": "text/plain"}


@router.get("/surveys/{sid}/exports/{fmt}/download")
def download_export(request: Request, sid: str, fmt: str, inline: int = 0):
    store = _store(request)
    _manifest_or_404(store, sid)
    if fmt not in _EXPORT_PATTERNS:
        raise HTTPException(404, "פורמט לא מוכר")
    path = _latest(store, sid, fmt)
    if path is None:
        raise HTTPException(404, "הפלט טרם הופק")
    disposition = "inline" if inline else "attachment"
    return FileResponse(str(path), media_type=_MEDIA[fmt],
                        headers={"Content-Disposition":
                                 f'{disposition}; filename="{path.name}"'})

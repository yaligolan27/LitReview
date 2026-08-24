"""Hunter behaviors: refine counter semantics (the spec §16 trap), multilang
guarantee, saturation, and transparency blocks — offline in mock mode."""

import json
from pathlib import Path

from litreview import config
from litreview.agents.research_planner import brief_from_config
from litreview.agents.source_hunter import build_queries, run_source_hunter
from litreview.agents.toc_architect import run_toc_architect
from litreview.core.context import RunContext
from litreview.core.events import NullEmitter
from litreview.core.llm import LLM
from litreview.core.state import SurveyState


def _ctx(tmp_path: Path) -> RunContext:
    settings = config.get_settings()
    return RunContext(settings=settings, llm=LLM(settings, bridge_dir=tmp_path / "b"),
                      workdir=tmp_path, emitter=NullEmitter())


def _state() -> SurveyState:
    state = SurveyState()
    state.brief = brief_from_config({
        "topic": "כלי סקירה", "search_topic": "literature review automation",
        "subtopics": ["citation verification"],
        "languages": ["English", "Hebrew"],
    })
    return state


def test_multilang_hebrew_query_enters_first_and_uncapped(tmp_path, monkeypatch):
    monkeypatch.setenv("SURVEY_MAX_QUERIES", "1")
    config.reset_settings()
    ctx = _ctx(tmp_path)
    state = _state()
    run_toc_architect(ctx, state)
    queries = build_queries(ctx, state)
    # Hebrew multilang query is first and survives the cap of 1.
    assert queries[0].language == "Hebrew"
    assert queries[0].text == "כלי סקירה"
    assert len([q for q in queries if q.origin != "multilang"]) == 1


def test_refine_rounds_counter_runs_requested_rounds(tmp_path, monkeypatch):
    monkeypatch.setenv("SURVEY_REFINE_ROUNDS", "2")
    config.reset_settings()
    ctx = _ctx(tmp_path)
    state = _state()
    run_toc_architect(ctx, state)
    run_source_hunter(ctx, state)
    assert state.source_routing["refine_rounds"] == 2


def test_legacy_refine_flag_value_two_means_two_rounds(monkeypatch):
    # The original tool silently DISABLED the round for the value 2 (spec §16).
    monkeypatch.delenv("SURVEY_REFINE_ROUNDS", raising=False)
    monkeypatch.setenv("SURVEY_REFINE_ROUND", "2")
    config.reset_settings()
    assert config.get_settings().refine_rounds == 2
    monkeypatch.setenv("SURVEY_REFINE_ROUND", "0")
    config.reset_settings()
    assert config.get_settings().refine_rounds == 0


def test_hunter_fills_transparency_blocks(tmp_path):
    ctx = _ctx(tmp_path)
    state = _state()
    run_toc_architect(ctx, state)
    run_source_hunter(ctx, state)

    assert state.papers, "mock provider must return papers"
    assert state.prisma["identified"] >= state.prisma["after_dedup"]
    routing = state.source_routing
    assert routing["active_sources"] == ["mockdb"]
    assert "Hebrew" in routing["languages_searched"]
    assert routing["languages_requested"] == ["English", "Hebrew"]
    assert state.dedup_stats["engine"] in ("rapidfuzz", "difflib")
    assert state.timeline_years == sorted(state.timeline_years)


def test_state_serializes_after_hunt(tmp_path):
    ctx = _ctx(tmp_path)
    state = _state()
    run_toc_architect(ctx, state)
    run_source_hunter(ctx, state)
    payload = json.dumps(state.to_dict(), ensure_ascii=False)
    assert "mockdb" in payload

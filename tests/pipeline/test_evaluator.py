from litreview import config
from litreview.agents.evaluator import run_evaluator
from litreview.core.context import RunContext
from litreview.core.events import NullEmitter
from litreview.core.llm import LLM
from litreview.core.state import Paper, SurveySection, SurveyState


def _ctx(tmp_path):
    settings = config.get_settings()
    return RunContext(settings=settings, llm=LLM(settings, bridge_dir=tmp_path),
                      workdir=tmp_path, emitter=NullEmitter())


def _state(confidences, supported_pct=80.0, unsupported_pct=5.0) -> SurveyState:
    state = SurveyState()
    state.cited_papers = [
        Paper(id=f"p{i}", title=f"t{i}", confidence=c, source=f"s{i % 3}",
              source_type="journal-article")
        for i, c in enumerate(confidences)]
    state.papers = list(state.cited_papers)
    state.sections = [SurveySection(title="א", content="תוכן [1]")]
    state.toc = [type("T", (), {"chapter": "א"})()]
    state.grounding_report = {"supported_pct": supported_pct,
                             "unsupported_pct": unsupported_pct,
                             "by_chapter": []}
    state.citation_report = {"dead_citations": 0, "missing_fields": [],
                            "doi_mismatch": []}
    state.charts = [{"title": "x", "svg": "<svg/>"}] * 3
    state.prisma = {"svg": "<svg/>"}
    return state


def test_score_in_range_and_metrics_present(tmp_path):
    state = _state(["HIGH"] * 6, supported_pct=90)
    run_evaluator(_ctx(tmp_path), state)
    card = state.scorecard
    assert 0 <= card["score"] <= 100
    assert set(card["metrics"]) == {
        "supported_claims", "source_quality", "citation_integrity",
        "low_unsupported", "hebrew_quality", "source_diversity",
        "toc_match", "chart_reliability", "coherence"}
    assert card["metrics"]["supported_claims"] == 9.0
    assert not card["below_threshold"]


def test_emerging_counts_as_low_not_zero(tmp_path):
    state = _state(["EMERGING"] * 6)
    run_evaluator(_ctx(tmp_path), state)
    assert state.scorecard["metrics"]["source_quality"] == 1.5   # 10 × 0.15


def test_small_pool_penalty(tmp_path):
    state = _state(["HIGH"] * 3)   # n<5 → ×0.85
    run_evaluator(_ctx(tmp_path), state)
    assert state.scorecard["metrics"]["source_quality"] == 8.5


def test_below_threshold_flag(tmp_path):
    state = _state(["EMERGING"] * 2, supported_pct=10.0, unsupported_pct=70.0)
    state.charts = []
    state.prisma = {}
    run_evaluator(_ctx(tmp_path), state)
    assert state.scorecard["below_threshold"]
    assert state.scorecard["metrics"]["chart_reliability"] == 3.0

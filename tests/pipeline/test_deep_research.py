from litreview import config
from litreview.agents.deep_research import (
    classify_tier,
    clean_finding,
    run_deep_research,
)
from litreview.core.context import RunContext
from litreview.core.events import NullEmitter
from litreview.core.llm import LLM
from litreview.core.state import Paper, ResearchBrief, SurveyState


def _ctx(tmp_path):
    settings = config.get_settings()
    return RunContext(settings=settings, llm=LLM(settings, bridge_dir=tmp_path),
                      workdir=tmp_path, emitter=NullEmitter())


def test_clean_finding_rejects_fabrications():
    assert clean_finding({"url": "not-a-url", "heading": "h", "insight": "i"}) is None
    assert clean_finding({"url": "https://x.com/a", "heading": "", "insight": "i"}) is None
    assert clean_finding({"url": "https://x.com/a", "heading": "h", "insight": ""}) is None
    ok = clean_finding({"url": "https://example.gov/r", "heading": "h", "insight": "i"})
    assert ok and ok["tier"] == "W-T1"


def test_classify_tier_deterministic():
    assert classify_tier("https://www.nasa.gov/report") == "W-T1"
    assert classify_tier("https://something.ac.il/paper") == "W-T1"
    assert classify_tier("https://www.reuters.com/article") == "W-T2"
    assert classify_tier("https://calcalist.co.il/x") == "W-T2"
    assert classify_tier("https://myblog.medium.com/post") == "W-T3"
    assert classify_tier("https://en.wikipedia.org/wiki/X") == "W-T3"
    assert classify_tier("https://random-vendor.com/") == "W-T3"


def test_mock_run_saturation_verification_and_iron_numbering(tmp_path):
    state = SurveyState(brief=ResearchBrief(
        topic="נושא", search_topic="market topic", goals=["מיפוי"]))
    state.papers = [Paper(title="Unrelated academic paper", year=2024)]
    run_deep_research(_ctx(tmp_path), state)

    dr = state.deep_research
    # Mock round 1 returns 3 raw findings, one without a real URL → discarded.
    assert len(dr["findings"]) == 2
    # Round 2 returns [] → saturation stop recorded.
    assert dr["stats"]["rounds"] == 2
    assert dr["rounds"][-1]["new_findings"] == 0
    # Verification corroborated F2 from a different domain.
    corroborated = [f for f in dr["findings"] if f["verdict"] == "corroborated"]
    assert len(corroborated) == 1 and corroborated[0]["second_url"]
    # W numbering: corroborated first.
    assert dr["findings"][0]["w_id"] == "W1"
    assert dr["findings"][0]["verdict"] == "corroborated"
    # Entities table row kept (has a real source_url).
    assert dr["entities"]["rows"]
    assert dr["stats"]["tier_counts"]["W-T1"] >= 1


def test_disabled_flag(tmp_path, monkeypatch):
    monkeypatch.setenv("SURVEY_DEEP_RESEARCH", "0")
    config.reset_settings()
    state = SurveyState(brief=ResearchBrief(topic="x", search_topic="y"))
    run_deep_research(_ctx(tmp_path), state)
    assert state.deep_research == {}

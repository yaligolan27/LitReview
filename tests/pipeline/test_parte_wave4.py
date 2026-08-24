"""Part-E wave 4 (spec §24): full multilingual.

Guardrails pinned: translation widens the *search* only; a verbatim quote is
never translated; per-language transparency reports found/cited/requested-
but-empty; a foreign-language cited source gets a dedicated tag. All default
OFF — standard runs are unchanged.
"""

from litreview import config
from litreview.agents import deep_research as dr
from litreview.agents import source_hunter
from litreview.agents.html_generator.builders import (
    _foreign_lang_tag,
    build_language_transparency,
)
from litreview.apis import openalex, registry
from litreview.core.context import RunContext
from litreview.core.events import NullEmitter
from litreview.core.llm import LLM
from litreview.core.state import Paper, ResearchBrief, SurveyState


def _ctx(tmp_path, backend="mock", **env):
    import os
    os.environ["SURVEY_LLM_BACKEND"] = backend
    for k, v in env.items():
        os.environ[k] = v
    config.reset_settings()
    settings = config.get_settings()
    return RunContext(settings=settings, llm=LLM(settings, bridge_dir=tmp_path),
                      workdir=tmp_path, emitter=NullEmitter())


def _clear_env(*keys):
    import os
    for k in keys:
        os.environ.pop(k, None)
    config.reset_settings()


# --- language maps ----------------------------------------------------------

def test_iso_code_normalizes_names():
    assert registry.iso_code("Spanish") == "es"
    assert registry.iso_code("עברית") == "he"
    assert registry.iso_code("de") == "de"
    assert registry.iso_code("Klingon") == ""


def test_language_channels_lookup():
    assert "scielo" in registry.language_channels("es")
    assert registry.language_channels("en") == []


# --- multilingual DB routing (hunter) --------------------------------------

def test_multilang_db_search_routes_by_language(tmp_path, monkeypatch):
    ctx = _ctx(tmp_path, backend="api", SURVEY_ML_DB_ROUTING="1")
    assert not ctx.offline

    def fake_search(topic, limit=5, year_from=None, year_to=None, language=None):
        return [Paper(title=f"{language} paper", language=language, source="openalex")]
    monkeypatch.setattr(openalex, "search", fake_search)

    state = SurveyState(brief=ResearchBrief(
        search_topic="robotics", languages=["English", "Spanish", "German"]))
    papers, breakdown = source_hunter._multilang_db_search(ctx, state)
    # English is the default channel — not re-queried here; es + de are.
    assert set(breakdown) == {"es", "de"}
    assert all(p.found_via == "multilang_db" for p in papers)
    assert "openalex:language:es" in breakdown["es"]["channels"]
    _clear_env("SURVEY_LLM_BACKEND", "SURVEY_ML_DB_ROUTING")


def test_multilang_db_search_off_by_default(tmp_path):
    ctx = _ctx(tmp_path, backend="api")   # flag not set
    state = SurveyState(brief=ResearchBrief(languages=["English", "Spanish"]))
    assert source_hunter._multilang_db_search(ctx, state) == ([], {})
    _clear_env("SURVEY_LLM_BACKEND")


def test_multilang_db_search_skipped_offline(tmp_path):
    ctx = _ctx(tmp_path, backend="mock", SURVEY_ML_DB_ROUTING="1")
    assert ctx.offline
    state = SurveyState(brief=ResearchBrief(languages=["English", "Spanish"]))
    assert source_hunter._multilang_db_search(ctx, state) == ([], {})
    _clear_env("SURVEY_LLM_BACKEND", "SURVEY_ML_DB_ROUTING")


# --- multilingual deep research --------------------------------------------

def test_ml_web_runs_language_rounds(tmp_path):
    ctx = _ctx(tmp_path, backend="mock", SURVEY_ML_WEB="1")
    state = SurveyState(brief=ResearchBrief(topic="נושא", search_topic="market",
                                            goals=["מיפוי"], languages=["English"]))
    state.papers = [Paper(title="x", year=2024)]
    dr.run_deep_research(ctx, state)
    stats = state.deep_research["stats"]
    # Mock dr_plan advertises English + Spanish → only "es" is a foreign round.
    assert stats.get("languages") == ["es"]
    assert any("multilingual round" in e.get("message", "")
               for e in state.audit_log)
    _clear_env("SURVEY_LLM_BACKEND", "SURVEY_ML_WEB")


def test_standard_deep_research_has_no_language_key(tmp_path):
    ctx = _ctx(tmp_path, backend="mock")
    state = SurveyState(brief=ResearchBrief(topic="נושא", search_topic="market",
                                            goals=["x"]))
    state.papers = [Paper(title="x", year=2024)]
    dr.run_deep_research(ctx, state)
    assert "languages" not in state.deep_research["stats"]
    _clear_env("SURVEY_LLM_BACKEND")


def test_verbatim_quote_guardrail_in_system_prompt():
    # The iron rule for translation lives in the multilingual round system.
    assert "אל תתרגם" in dr._ROUND_SYSTEM_ML


def test_relevant_languages_filters_english_and_dedupes():
    state = SurveyState(brief=ResearchBrief(languages=["English"]))
    plan = {"relevant_languages": ["English", "Spanish", "es", "German"]}
    assert dr._relevant_languages(plan, state) == ["es", "de"]


def test_relevant_languages_falls_back_to_brief():
    state = SurveyState(brief=ResearchBrief(languages=["English", "French"]))
    assert dr._relevant_languages({}, state) == ["fr"]


# --- transparency + foreign-source tag (builders) --------------------------

def _ml_state():
    state = SurveyState(brief=ResearchBrief(languages=["English", "Spanish", "Japanese"]))
    state.papers = [Paper(title="a", language="en"), Paper(title="b", language="es"),
                    Paper(title="c", language="es")]
    state.cited_papers = [Paper(title="a", language="en"), Paper(title="b", language="es")]
    state.source_routing = {"multilang_db": {
        "es": {"language": "Spanish", "iso": "es", "found": 2,
               "channels": ["openalex:language:es", "scielo"]}}}
    return state


def test_language_transparency_reports_found_cited_and_empty():
    html = build_language_transparency(_ml_state())
    assert "פילוח מקורות לפי שפה" in html
    assert "ציטוטים מילוליים לא תורגמו" in html
    # Japanese was requested but produced nothing → the empty note appears.
    assert "התבקשה אך לא נמצאו מקורות" in html


def test_language_transparency_empty_without_routing():
    state = SurveyState()
    assert build_language_transparency(state) == ""


def test_foreign_lang_tag_gated_and_correct():
    state = _ml_state()
    assert _foreign_lang_tag(state, Paper(language="es")) != ""
    assert _foreign_lang_tag(state, Paper(language="en")) == ""
    # Without multilingual routing, no tag even for a foreign paper.
    assert _foreign_lang_tag(SurveyState(), Paper(language="es")) == ""

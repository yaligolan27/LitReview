"""Part-E wave 3 (spec §23, §24): Source Scout + practical mode.

Guardrails pinned: the Scout runs only on a real coverage gap; a confident
domain suppresses it; unknown databases need approval and never exceed T2;
OAI-PMH parsing is offline-pure.
"""

import pytest

from litreview import config
from litreview.agents import source_scout as scout
from litreview.agents.claim_grounder import _example_claims
from litreview.agents.html_generator.convert import convert_markers
from litreview.agents.writer import build_chapter_prompt, is_practical
from litreview.apis import oai_pmh, registry
from litreview.core import markers
from litreview.core.context import RunContext
from litreview.core.events import NullEmitter
from litreview.core.llm import LLM
from litreview.core.marker_render import to_plain_text
from litreview.core.state import ResearchBrief, SurveySection, SurveyState, TocEntry


def _ctx(tmp_path, backend="mock"):
    import os
    os.environ["SURVEY_LLM_BACKEND"] = backend
    os.environ["SURVEY_SOURCE_SCOUT"] = "1"
    config.reset_settings()
    settings = config.get_settings()
    return RunContext(settings=settings, llm=LLM(settings, bridge_dir=tmp_path),
                      workdir=tmp_path, emitter=NullEmitter())


@pytest.fixture
def clean_registry():
    p0, t0 = dict(registry.PROVIDERS), dict(registry.SOURCE_TIER)
    yield
    registry.PROVIDERS.clear()
    registry.PROVIDERS.update(p0)
    registry.SOURCE_TIER.clear()
    registry.SOURCE_TIER.update(t0)


def _routing(certain=None, active=None):
    return registry.RoutingResult(active=active or ["openalex"],
                                  certain_domains=certain or [])


# --- coverage-gap trigger logic --------------------------------------------

def test_confident_domain_suppresses_scout():
    # A certain domain → routed DBs already fit → no scouting, whatever counts.
    assert scout.coverage_gap(_routing(certain=["cs_ai"]), 3, 8, 0) == []


def test_low_unique_after_queries_triggers():
    reasons = scout.coverage_gap(_routing(), unique_count=6,
                                 executed_count=5, refine_added=9)
    assert reasons and any("מעט מקורות" in r for r in reasons)


def test_weak_refine_triggers():
    reasons = scout.coverage_gap(_routing(), unique_count=40,
                                 executed_count=5, refine_added=1)
    assert reasons and any("העמקה" in r for r in reasons)


def test_healthy_coverage_no_trigger():
    assert scout.coverage_gap(_routing(), 40, 5, 9) == []


# --- OAI-PMH parsing (offline-pure) ----------------------------------------

_OAI_XML = """<?xml version="1.0"?>
<OAI-PMH xmlns="http://www.openarchives.org/OAI/2.0/">
 <ListRecords>
  <record>
   <header><identifier>oai:x:1</identifier><datestamp>2024-05-01</datestamp></header>
   <metadata>
    <oai_dc:dc xmlns:oai_dc="http://www.openarchives.org/OAI/2.0/oai_dc/"
               xmlns:dc="http://purl.org/dc/elements/1.1/">
     <dc:title>Machine learning for legal document review</dc:title>
     <dc:creator>Cohen, Dana</dc:creator>
     <dc:creator>Levi, Noa</dc:creator>
     <dc:date>2024</dc:date>
     <dc:identifier>https://doi.org/10.1234/abc</dc:identifier>
     <dc:description>A study of ML applied to legal review.</dc:description>
     <dc:language>en</dc:language>
    </oai_dc:dc>
   </metadata>
  </record>
  <record>
   <header status="deleted"><identifier>oai:x:2</identifier></header>
  </record>
 </ListRecords>
</OAI-PMH>"""


def test_parse_oai_dc_extracts_fields_and_skips_deleted():
    papers = oai_pmh.parse_oai_dc(_OAI_XML, source="testrepo")
    assert len(papers) == 1          # the deleted record is skipped
    p = papers[0]
    assert p.title.startswith("Machine learning")
    assert p.year == 2024
    assert p.doi == "10.1234/abc"
    assert p.authors == ["Cohen, Dana", "Levi, Noa"]
    assert p.source == "testrepo"


def test_parse_oai_dc_malformed_is_empty():
    assert oai_pmh.parse_oai_dc("<not-xml", source="x") == []


def test_make_provider_filters_by_query(monkeypatch):
    monkeypatch.setattr(oai_pmh._http, "get_text", lambda *a, **k: _OAI_XML)
    search = oai_pmh.make_provider("testrepo", "https://x/oai")
    assert len(search("legal", limit=5)) == 1        # term present
    assert search("astrophysics quantum", limit=5) == []   # term absent


# --- allowlist + registration ----------------------------------------------

def test_allowlist_loads_shipped_file():
    allow = scout.load_allowlist()
    assert "zenodo" in allow and allow["zenodo"]["type"] == "oai_pmh"


def test_scouted_source_never_exceeds_t2(clean_registry):
    registry.register_provider("mysterydb", lambda *a, **k: [], tier="T1")
    assert registry.tier_for("mysterydb") == "T2"   # T1 request clamped


def test_register_oai_source_online(clean_registry):
    entry = {"type": "oai_pmh", "endpoint": "https://x/oai", "tier": "T2"}
    name = scout._register("NewRepo", entry, {}, offline=False)
    assert name == "newrepo"
    assert "newrepo" in registry.PROVIDERS
    assert registry.tier_for("newrepo") == "T2"


def test_register_skips_network_source_offline(clean_registry):
    entry = {"type": "oai_pmh", "endpoint": "https://x/oai", "tier": "T2"}
    assert scout._register("NewRepo", entry, {}, offline=True) is None
    assert "newrepo" not in registry.PROVIDERS


# --- run_source_scout end to end -------------------------------------------

def test_scout_off_returns_empty(tmp_path):
    import os
    os.environ["SURVEY_SOURCE_SCOUT"] = "0"
    config.reset_settings()
    settings = config.get_settings()
    ctx = RunContext(settings=settings, llm=LLM(settings, bridge_dir=tmp_path),
                     workdir=tmp_path, emitter=NullEmitter())
    enabled, report = scout.run_source_scout(ctx, SurveyState(), _routing(), [], [], 0)
    assert enabled == [] and report == {}
    os.environ.pop("SURVEY_SOURCE_SCOUT", None)


def test_scout_enables_connector_and_flags_unknown(tmp_path, monkeypatch):
    ctx = _ctx(tmp_path)
    monkeypatch.setattr(scout, "_suggest", lambda c, s, searched: [
        {"name": "pubmed", "reason": "biomedical angle"},       # rung 1 connector
        {"name": "MysteryDB", "reason": "unknown source"},      # needs approval
    ])
    state = SurveyState(brief=ResearchBrief(topic="t", search_topic="q"))
    enabled, report = scout.run_source_scout(
        ctx, state, _routing(), unique=[1] * 5, executed=["a"] * 5, refine_added=0)
    assert "pubmed" in enabled
    assert "mysterydb" not in [e.lower() for e in enabled]
    assert any(p["name"] == "MysteryDB" for p in report["pending_approval"])
    assert report["triggers"]
    # The scout decision is on the audit trail.
    assert any(e.get("stage") == "scout" for e in state.audit_log)
    import os
    os.environ.pop("SURVEY_SOURCE_SCOUT", None)


def test_scout_suggestion_empty_in_mock(tmp_path):
    # The mock source_scout purpose returns no suggestions → nothing enabled,
    # but the trigger + empty report are still recorded honestly.
    ctx = _ctx(tmp_path)
    state = SurveyState(brief=ResearchBrief(topic="t", search_topic="q"))
    enabled, report = scout.run_source_scout(
        ctx, state, _routing(), unique=[1] * 5, executed=["a"] * 5, refine_added=0)
    assert enabled == []
    assert report["triggers"] and report["enabled"] == []
    import os
    os.environ.pop("SURVEY_SOURCE_SCOUT", None)


# ===========================================================================
# Practical mode + [EXAMPLE] marker
# ===========================================================================

_EX = ("[EXAMPLE]חישוב דחף|מהירות פליטה 3000 מ\"ש [4]|F = ṁ·v_e = 5·3000|"
       "15,000 ניוטון[/EXAMPLE]")


def test_example_marker_lint_field_count():
    ok = markers.lint("[EXAMPLE]a|b|c|d[/EXAMPLE]")
    assert not any("EXAMPLE" in i.message for i in ok)
    bad = markers.lint("[EXAMPLE]a|b[/EXAMPLE]")
    assert any("EXAMPLE" in i.message for i in bad)


def test_example_marker_is_balance_linted_and_protected():
    # Pre-wired in BLOCK_TAGS/PROTECTED_TAGS — an unbalanced block is an error.
    assert markers.has_errors("[EXAMPLE]a|b|c|d")
    assert "EXAMPLE" in markers.PROTECTED_TAGS


def test_example_renders_as_html_card():
    html = convert_markers(_EX)
    assert "example-card" in html
    assert "דוגמה מחושבת" in html
    assert "[EXAMPLE]" not in html          # marker fully consumed


def test_example_renders_to_plain_text_for_word():
    plain = to_plain_text(_EX)
    assert "דוגמה מחושבת" in plain
    assert "[EXAMPLE]" not in plain and "/EXAMPLE" not in plain


def test_is_practical_global_and_per_chapter():
    class S:  # minimal settings stand-in
        depth = "practical"
    assert is_practical(S(), TocEntry(chapter="x"))

    class Std:
        depth = "standard"
    assert not is_practical(Std(), TocEntry(chapter="x"))
    assert is_practical(Std(), TocEntry(chapter="x", depth="practical"))


def test_writer_prompt_adds_practical_block_only_when_practical():
    state = SurveyState(brief=ResearchBrief(topic="נושא", audience="מהנדסים"))
    entry = TocEntry(chapter="פרק")
    on = build_chapter_prompt(state, entry, 1, [], practical=True)
    off = build_chapter_prompt(state, entry, 1, [], practical=False)
    assert "[EXAMPLE]" in on and "מצב פרקטי" in on and "להמחשה" in on
    assert "[EXAMPLE]" not in off and "מצב פרקטי" not in off


def test_example_value_without_source_becomes_unsupported():
    sec = SurveySection(
        content="[EXAMPLE]דוגמה|מהירות 3000|F = 5·3000|15000 ניוטון[/EXAMPLE]")
    claims = _example_claims(sec, "1")
    assert len(claims) == 1 and claims[0].status == "unsupported"


def test_example_value_with_citation_is_ok():
    sec = SurveySection(
        content="[EXAMPLE]דוגמה|מהירות 3000 [4]|F = 5·3000 [4]|15000 ניוטון [4][/EXAMPLE]")
    assert _example_claims(sec, "1") == []


def test_example_marked_illustration_is_ok():
    sec = SurveySection(
        content="[EXAMPLE]דוגמה|ערכים להמחשה בלבד|F = 5·3000|15000 ניוטון[/EXAMPLE]")
    assert _example_claims(sec, "1") == []


def test_example_without_numbers_is_ok():
    sec = SurveySection(
        content="[EXAMPLE]דוגמה איכותית|הנחות מילוליות|תיאור התהליך|מסקנה מילולית[/EXAMPLE]")
    assert _example_claims(sec, "1") == []

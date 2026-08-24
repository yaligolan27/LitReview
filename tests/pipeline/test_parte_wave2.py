"""Part-E wave 2 (spec §21, §24): reliability signals + deep web mode.

Every test pins a guardrail: a network failure never lowers a score
(checked≠valid); the predatory list flags but never removes; the 10th metric
leaves the default scorecard byte-identical; dr_trace without a real primary
URL is honest ("not_found"); standard deep-research is unchanged.
"""

from litreview import config
from litreview.agents.evaluator import run_evaluator
from litreview.agents.html_generator.builders import _reliability_panel
from litreview.apis import crossref, openalex, semantic_scholar
from litreview.core import reliability_signals as rs
from litreview.core.context import RunContext
from litreview.core.events import NullEmitter
from litreview.core.llm import LLM
from litreview.core.state import (
    Claim,
    Paper,
    ResearchBrief,
    SurveySection,
    SurveyState,
)


def _ctx(tmp_path):
    settings = config.get_settings()
    return RunContext(settings=settings, llm=LLM(settings, bridge_dir=tmp_path),
                      workdir=tmp_path, emitter=NullEmitter())


# --- checked≠valid: offline enrich never invents or penalises ---------------

def test_offline_enrich_marks_network_signals_unchecked():
    rs.reset_predatory_cache()
    paper = Paper(title="t", doi="10.1/x", journal="Some Journal",
                  citation_count=50, authors=["Doe, J."])
    block = rs.enrich(paper, offline=True)
    sig = block["signals"]
    # Network-dependent signals are unchecked (not fabricated, not zero-scored).
    for name in ("author", "journal", "institution", "self_citation", "errata"):
        assert sig[name]["status"] == "unchecked"
    # The no-network anchor signal is present, so the score is not None.
    assert sig["citation_context"]["status"] == "ok"
    assert block["score"] is not None
    assert block["checked"] >= 1
    # Score is stored on the paper too.
    assert paper.reliability_signals is block


def test_score_aggregates_only_checked_signals():
    # Two papers differ ONLY in a network signal we cannot check offline;
    # their offline scores must be identical (unchecked ⇒ out of denominator).
    a = Paper(title="a", doi="10.1/a", citation_count=200, journal="J")
    b = Paper(title="b", citation_count=200, journal="J")   # no DOI at all
    sa = rs.enrich(a, offline=True)["score"]
    sb = rs.enrich(b, offline=True)["score"]
    assert sa == sb   # the missing/《unchecked》signals never move the score


# --- predatory list: flags, never removes -----------------------------------

def test_predatory_list_flags_but_never_removes(tmp_path, monkeypatch):
    csv = tmp_path / "pred.csv"
    csv.write_text("# header\nname,issn,list_source\n"
                   "Fake Predatory Journal,1234-5678,test list\n", encoding="utf-8")
    monkeypatch.setattr(rs, "_PREDATORY", rs.PredatoryList(csv))

    flagged = Paper(title="p", journal="Fake Predatory Journal", citation_count=3)
    clean = Paper(title="q", journal="Nature", citation_count=3)
    fblock = rs.enrich(flagged, offline=True)
    cblock = rs.enrich(clean, offline=True)

    assert fblock["signals"]["predatory"]["status"] == "flag"
    assert fblock["flags"] >= 1
    assert cblock["signals"]["predatory"]["status"] == "ok"
    # The paper is still fully scored — nothing was removed or nulled.
    assert fblock["score"] is not None


def test_empty_predatory_list_is_unchecked_not_clean(tmp_path, monkeypatch):
    # The shipped file has only a header → no list → we cannot vouch for a journal.
    monkeypatch.setattr(rs, "_PREDATORY", rs.PredatoryList("data/predatory_journals.csv"))
    paper = Paper(title="p", journal="Whatever Journal", citation_count=1)
    block = rs.enrich(paper, offline=True)
    assert block["signals"]["predatory"]["status"] == "unchecked"


# --- online path (connectors monkeypatched, no real network) ----------------

def test_online_signals_compute_from_connectors(monkeypatch):
    rs.reset_predatory_cache()
    work = {
        "authorships": [{
            "author": {"id": "https://openalex.org/A1"},
            "institutions": [{"display_name": "MIT"}],
        }],
        "primary_location": {"source": {"id": "https://openalex.org/S1"}},
    }
    monkeypatch.setattr(openalex, "fetch_work_by_doi",
                        lambda doi: {"status": "ok", "work": work})
    monkeypatch.setattr(openalex, "author_profile",
                        lambda aid: {"status": "ok", "h_index": 45, "works_count": 120,
                                     "orcid": "0000-1", "display_name": "A. Author",
                                     "concepts": ["Robotics"]})
    monkeypatch.setattr(openalex, "source_profile",
                        lambda sid: {"status": "ok", "two_year_mean_citedness": 6.0,
                                     "is_in_doaj": True, "is_core": True,
                                     "display_name": "Top Journal"})
    monkeypatch.setattr(crossref, "updates",
                        lambda doi: {"status": "ok", "has_errata": False,
                                     "has_concern": False, "update_kinds": [],
                                     "funders": ["NSF"], "has_funding": True})
    monkeypatch.setattr(semantic_scholar, "references",
                        lambda paper, limit=25: [Paper(title="r", authors=["Other, X."])])

    paper = Paper(title="t", doi="10.1/x", journal="Top Journal",
                  citation_count=150, authors=["Author, A."])
    block = rs.enrich(paper, offline=False)
    sig = block["signals"]
    assert sig["author"]["status"] == "ok" and sig["author"]["points"] >= 0.9
    assert sig["journal"]["status"] == "ok"
    assert sig["institution"]["status"] == "ok" and "MIT" in sig["institution"]["detail"]
    assert sig["self_citation"]["status"] == "ok"     # 0/1 self-refs
    assert sig["errata"]["status"] == "ok"
    assert sig["funding"]["status"] == "ok"
    assert block["score"] is not None and block["checked"] >= 7


def test_network_failure_on_one_signal_is_unchecked(monkeypatch):
    rs.reset_predatory_cache()
    # OpenAlex work fetch fails (NetworkError → status unchecked upstream);
    # Crossref works. Author/journal become unchecked, but the score still
    # computes from the signals that DID resolve — and is not penalised.
    # The self-citation lookup is a separate network call — stub it to []
    # ("references unavailable" → unchecked) so the test is fully hermetic.
    monkeypatch.setattr(openalex, "fetch_work_by_doi", lambda doi: {"status": "unchecked"})
    monkeypatch.setattr(semantic_scholar, "references", lambda paper, limit=25: [])
    monkeypatch.setattr(crossref, "updates",
                        lambda doi: {"status": "ok", "has_errata": False,
                                     "has_concern": False, "update_kinds": [],
                                     "funders": [], "has_funding": False})
    paper = Paper(title="t", doi="10.1/x", journal="J", citation_count=80)
    block = rs.enrich(paper, offline=False)
    assert block["signals"]["author"]["status"] == "unchecked"
    assert block["signals"]["journal"]["status"] == "unchecked"
    assert block["score"] is not None   # from citation_context + errata


# --- evaluator: 10th metric only when flag on, weights stay summed to 1 ------

def _eval_state():
    state = SurveyState(brief=ResearchBrief(search_topic="robotics"))
    state.cited_papers = [Paper(id=f"p{i}", title=f"t{i}", confidence="HIGH",
                                source=f"s{i}", source_type="journal-article",
                                citation_count=40) for i in range(6)]
    state.papers = list(state.cited_papers)
    state.sections = [SurveySection(title="א", content="תוכן [1]")]
    state.toc = [type("T", (), {"chapter": "א"})()]
    state.grounding_report = {"supported_pct": 85.0, "unsupported_pct": 5.0}
    state.citation_report = {"dead_citations": 0, "missing_fields": [], "doi_mismatch": []}
    state.charts = [{"title": "x", "svg": "<svg/>"}]
    state.prisma = {"svg": "<svg/>"}
    return state


def test_scorecard_default_has_nine_metrics(tmp_path):
    # Flag OFF (conftest default) → exactly the original nine metrics.
    state = _eval_state()
    run_evaluator(_ctx(tmp_path), state)
    assert "verification_depth" not in state.scorecard["metrics"]
    assert len(state.scorecard["metrics"]) == 9
    assert abs(sum(state.scorecard["weights"].values()) - 1.0) < 1e-9


def test_scorecard_tenth_metric_when_flag_on(tmp_path, monkeypatch):
    monkeypatch.setenv("SURVEY_RELIABILITY_SIGNALS", "1")
    config.reset_settings()
    state = _eval_state()
    run_evaluator(_ctx(tmp_path), state)
    metrics = state.scorecard["metrics"]
    assert "verification_depth" in metrics
    assert len(metrics) == 10
    # Renormalised weights still sum to 1.0.
    assert abs(sum(state.scorecard["weights"].values()) - 1.0) < 1e-9
    # Cited papers were actually enriched.
    assert all(p.reliability_signals for p in state.cited_papers)


# --- deep web mode ----------------------------------------------------------

def test_deep_mode_traces_primary_and_is_honest(tmp_path, monkeypatch):
    from litreview.agents.deep_research import run_deep_research
    monkeypatch.setenv("SURVEY_DR_DEPTH", "deep")
    config.reset_settings()
    state = SurveyState(brief=ResearchBrief(topic="נושא", search_topic="market",
                                            goals=["מיפוי"]))
    state.papers = [Paper(title="Unrelated", year=2024)]
    run_deep_research(_ctx(tmp_path), state)
    stats = state.deep_research["stats"]
    assert stats["depth"] == "deep"
    assert "primary_traced" in stats
    # Mock dr_trace returns no traces → the stat finding is honestly marked.
    stat_findings = [f for f in state.deep_research["findings"]
                     if f["type"] == "stat"]
    assert stat_findings and stat_findings[0].get("primary_traced") == "not_found"
    assert stats["primary_traced"] == 0


def test_standard_mode_unchanged_no_depth_key(tmp_path):
    from litreview.agents.deep_research import run_deep_research
    state = SurveyState(brief=ResearchBrief(topic="נושא", search_topic="market",
                                            goals=["מיפוי"]))
    state.papers = [Paper(title="Unrelated", year=2024)]
    run_deep_research(_ctx(tmp_path), state)
    stats = state.deep_research["stats"]
    assert "depth" not in stats            # standard mode adds no deep keys
    assert "primary_traced" not in stats
    # No finding got a trace attempt.
    assert not any("primary_traced" in f for f in state.deep_research["findings"])


# --- builders panel is invisible unless signals populated -------------------

def test_reliability_panel_empty_without_signals():
    assert _reliability_panel(Paper(title="t")) == ""


def test_reliability_panel_renders_when_populated():
    paper = Paper(title="t")
    rs.enrich(paper, offline=True)
    html = _reliability_panel(paper)
    assert html.startswith("<details")
    assert "אותות אמינות" in html


# --- connector status tagging (checked≠valid at the source) -----------------

def test_crossref_updates_status_tagging():
    # Empty DOI → n/a, never a network attempt.
    assert crossref.updates("")["status"] == "n/a"


def test_cross_consensus_signal_reads_grounder_flag():
    papers = [Paper(id="a", title="a", authors=["Smith, J."]),
              Paper(id="b", title="b", authors=["Chen, L."])]
    sec = SurveySection(title="x", papers=papers,
                        claims=[Claim(text="t", citations=[1, 2], status="supported",
                                      cross_corroborated=True)])
    state = SurveyState(sections=[sec])
    keys = rs._consensus_keys(state)
    assert id(papers[0]) in keys and id(papers[1]) in keys

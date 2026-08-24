"""M0 exit test: full SurveyState JSON round-trip incl. paper identity."""

from litreview.core.checkpoints import Checkpointer, RunRecord
from litreview.core.state import (
    Claim,
    Paper,
    ResearchBrief,
    SurveySection,
    SurveyState,
    TocEntry,
)


def _sample_state() -> SurveyState:
    p1 = Paper(id="W1", title="ReAct: Synergizing Reasoning and Acting", year=2023,
               authors=["Yao, S."], doi="10.48550/arXiv.2210.03629", source="openalex",
               tier="T1", confidence="HIGH", doi_verified=True, language="en",
               source_type="journal-article", citation_count=1842)
    p2 = Paper(id="W2", title="מערכות סוכנים אוטונומיים", year=2024, authors=["כהן, ד."],
               source="openalex", tier="T1", confidence="LIMITED", language="he",
               source_type="journal-article")
    sec = SurveySection(
        title="ארכיטקטורות סוכן",
        content="הספרות מבחינה בין גישות [1] ו-[2].",
        confidence="MODERATE",
        papers=[p1, p2],
        claims=[Claim(id="c1", text="טענה", citations=[1], status="supported", chapter="2")],
    )
    state = SurveyState(
        brief=ResearchBrief(topic="סוכני AI", search_topic="AI agents", author="מאיה"),
        toc=[TocEntry(chapter="מבוא", sections=["רקע"], keywords_en=["agents"])],
        papers=[p1, p2],
        sections=[sec],
        cited_papers=[p1],
    )
    state.log("test", "hello", n=1)
    state.prisma = {"identified": 10, "included": 2}
    return state


def test_roundtrip_preserves_content():
    state = _sample_state()
    restored = SurveyState.from_dict(state.to_dict())

    assert restored.brief.topic == "סוכני AI"
    assert restored.toc[0].keywords_en == ["agents"]
    assert restored.sections[0].content == state.sections[0].content
    assert restored.sections[0].claims[0].status == "supported"
    assert restored.prisma["identified"] == 10
    assert restored.audit_log[-1]["message"] == "hello"


def test_roundtrip_unifies_paper_identity():
    restored = SurveyState.from_dict(_sample_state().to_dict())
    sec_paper = restored.sections[0].papers[0]
    pool_paper = next(p for p in restored.papers if p.id == "W1")
    assert sec_paper is pool_paper
    assert restored.cited_papers[0] is pool_paper


def test_checkpointer_save_load(tmp_path):
    state = _sample_state()
    run = RunRecord(run_id="r1", backend="mock")
    run.mark("hunt", "running")
    run.mark("hunt", "done")

    cp = Checkpointer(tmp_path / "wd")
    cp.save(state, run)

    loaded_state = cp.load_state()
    loaded_run = cp.load_run()
    assert loaded_state is not None and loaded_run is not None
    assert loaded_state.sections[0].title == "ארכיטקטורות סוכן"
    assert loaded_run.is_done("hunt")
    assert not loaded_run.is_done("write")


def test_run_record_invalidate():
    run = RunRecord()
    run.mark("write", "done")
    run.mark("ground", "done")
    run.invalidate(["write", "ground", "html"])
    assert run.stage("write")["status"] == "stale"
    assert run.stage("html")["status"] == "pending"


def test_claim_and_section_overrides():
    sec = SurveySection(title="t", confidence="HIGH")
    assert sec.effective_confidence() == "HIGH"
    sec.confidence_override = {"value": "LIMITED", "by": "נועה"}
    assert sec.effective_confidence() == "LIMITED"

    claim = Claim(status="unsupported")
    claim.status_override = {"value": "supported", "by": "מאיה", "reason": "בדקתי במקור"}
    assert claim.effective_status() == "supported"

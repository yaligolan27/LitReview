from litreview.core.citation_manager import run_citation_manager
from litreview.core.state import Paper, SurveySection, SurveyState


def _paper(i: int, doi: str = "") -> Paper:
    return Paper(id=f"P{i}", title=f"Paper number {i} on topic",
                 year=2020 + i % 5, authors=[f"Author{i}, A."],
                 doi=doi or f"10.1000/p{i}", source_type="journal-article")


def test_global_renumbering_and_cited_only_bibliography():
    p1, p2, p3, p4 = (_paper(i) for i in range(1, 5))
    state = SurveyState()
    # Chapter 1 cites its [1],[2]; chapter 2 re-uses p2 as its local [1] and
    # cites local [2] (=p4). p3 is assigned but never cited → dropped.
    state.sections = [
        SurveySection(title="א", content="טענה ראשונה [1]. טענה שנייה [2].",
                      papers=[p1, p2]),
        SurveySection(title="ב", content="עוד טענה [1]. ומסקנה [2]. וטווח [1-2].",
                      papers=[p2, p4] + [p3]),
    ]
    run_citation_manager(None, state)

    # p1→[1], p2→[2] globally; chapter 2's local [1] becomes [2], local [2]→[3].
    assert "[1]" in state.sections[0].content and "[2]" in state.sections[0].content
    assert "[2]" in state.sections[1].content and "[3]" in state.sections[1].content
    assert "[2-3]" in state.sections[1].content or "[2,3]" in state.sections[1].content
    assert [p.id for p in state.cited_papers] == ["P1", "P2", "P4"]
    assert state.citation_report["entries"] == 3
    assert state.citation_report["uncited_dropped"] == 1
    assert all(p.apa for p in state.cited_papers)


def test_dead_citation_removed_and_reported():
    state = SurveyState()
    state.sections = [SurveySection(title="א", content="טענה עם ציטוט מת [7].",
                                    papers=[_paper(1)])]
    run_citation_manager(None, state)
    assert "[7]" not in state.sections[0].content
    assert state.citation_report["dead_citations"] == 1


def test_duplicate_paper_across_chapters_merges_to_one_entry():
    shared_doi = "10.1000/shared"
    a = _paper(1, doi=shared_doi)
    b = _paper(2, doi=shared_doi)   # same DOI, different object
    state = SurveyState()
    state.sections = [
        SurveySection(title="א", content="ציטוט [1].", papers=[a]),
        SurveySection(title="ב", content="ציטוט [1].", papers=[b]),
    ]
    run_citation_manager(None, state)
    assert len(state.cited_papers) == 1
    assert state.citation_report["duplicate_sources_merged"] == 1


def test_web_citations_untouched():
    state = SurveyState()
    state.sections = [SurveySection(title="א", content="ממצא שוק [W1] וטענה [1].",
                                    papers=[_paper(1)])]
    run_citation_manager(None, state)
    assert "[W1]" in state.sections[0].content


def test_executive_out_of_range_citations_stripped():
    state = SurveyState()
    state.sections = [SurveySection(title="א", content="טענה [1].", papers=[_paper(1)])]
    state.executive_summary = "מסקנה חשובה [1] ומסקנה שגויה [9]."
    run_citation_manager(None, state)
    assert "[1]" in state.executive_summary
    assert "[9]" not in state.executive_summary

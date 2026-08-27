from litreview.apis.retraction import RetractionWatch, check_paper
from litreview.core.state import Paper


def _watch(tmp_path, rows: str = "") -> RetractionWatch:
    csv_path = tmp_path / "rw.csv"
    csv_path.write_text("Title,OriginalPaperDOI,Reason\n" + rows, encoding="utf-8")
    return RetractionWatch(csv_path)


def test_openalex_flag_wins(tmp_path):
    paper = Paper(title="Fine paper", is_retracted=True, retraction_note="OpenAlex flag")
    ok, note = check_paper(paper, _watch(tmp_path), [0], use_crossref=False)
    assert ok and note == "OpenAlex flag"


def test_title_heuristics(tmp_path):
    watch = _watch(tmp_path)
    for title in ("RETRACTED: A bad study", "Retraction of: earlier claims",
                  "retracted: something"):
        ok, note = check_paper(Paper(title=title), watch, [0], use_crossref=False)
        assert ok, title
    ok, _ = check_paper(Paper(title="A perfectly normal title"), watch, [0],
                        use_crossref=False)
    assert not ok


def test_local_retraction_watch_by_doi_and_title(tmp_path):
    watch = _watch(tmp_path,
                   "Bad Science Study,10.1000/bad,Data fabrication\n"
                   "Another Withdrawn Paper,,Plagiarism\n")
    ok, note = check_paper(Paper(title="X", doi="https://doi.org/10.1000/BAD"),
                           watch, [0], use_crossref=False)
    assert ok and "Data fabrication" in note
    ok, note = check_paper(Paper(title="Another Withdrawn Paper!"), watch, [0],
                           use_crossref=False)
    assert ok and "Plagiarism" in note


def test_missing_csv_is_empty_index(tmp_path):
    watch = RetractionWatch(tmp_path / "nope.csv")
    ok, _ = check_paper(Paper(title="Clean"), watch, [0], use_crossref=False)
    assert not ok


def test_crossref_budget_not_spent_when_disabled(tmp_path):
    budget = [5]
    check_paper(Paper(title="Clean", doi="10.1/x"), _watch(tmp_path), budget,
                use_crossref=False)
    assert budget[0] == 5

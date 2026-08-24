from litreview.core.dedup import dedupe, normalize_doi, normalize_title
from litreview.core.state import Paper


def test_normalize_doi():
    assert normalize_doi("https://doi.org/10.1038/NATURE12373") == "10.1038/nature12373"
    assert normalize_doi("doi:10.1000/x") == "10.1000/x"
    assert normalize_doi("dx.doi.org/10.1000/x") == "10.1000/x"
    assert normalize_doi("https://arxiv.org/abs/2210.03629") == ""
    assert normalize_doi("not-a-doi") == ""
    assert normalize_doi("") == ""


def test_normalize_title_hebrew_niqqud_and_punctuation():
    assert normalize_title("Deep Learning: A Survey!") == "deep learning a survey"
    assert normalize_title("סְקִירָה") == normalize_title("סקירה")


def test_dedupe_by_doi_merges_and_upgrades():
    a = Paper(title="Paper A", doi="10.1000/abc", citation_count=5)
    b = Paper(title="Paper A (v2)", doi="https://doi.org/10.1000/ABC",
              citation_count=90, abstract="full abstract", is_open_access=True)
    unique, stats = dedupe([a, b])
    assert len(unique) == 1
    assert stats["by_doi"] == 1
    kept = unique[0]
    assert kept.citation_count == 90
    assert kept.abstract == "full abstract"
    assert kept.is_open_access


def test_dedupe_fuzzy_same_year():
    a = Paper(title="Autonomous AI agents in organizations", year=2024, doi="")
    b = Paper(title="Autonomous AI Agents in Organizations.", year=2024, doi="")
    unique, stats = dedupe([a, b])
    assert len(unique) == 1
    assert stats["by_fuzzy"] == 1


def test_dedupe_similar_but_different_year_and_author_kept():
    a = Paper(title="Graph neural networks for molecule generation prediction",
              year=2020, authors=["Smith, J."])
    b = Paper(title="Graph neural networks for molecular generation and prediction tasks",
              year=2023, authors=["Chen, L."])
    unique, _ = dedupe([a, b])
    assert len(unique) == 2


def test_dedupe_stats_shape():
    unique, stats = dedupe([Paper(title="X", doi="10.1/x")])
    assert stats["found"] == 1 and stats["kept"] == 1 and stats["removed"] == 0
    assert stats["engine"] in ("rapidfuzz", "difflib")

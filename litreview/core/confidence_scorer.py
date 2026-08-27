"""Source confidence rating — spec §9.4d (core/confidence_scorer.py).

Two historical fixes are baked in (per the spec):
1. The peer-reviewed publication-type dictionary covers every provider's
   vocabulary (Crossref "journal-article", OpenAlex "article",
   Semantic Scholar "JournalArticle", ...).
2. A fresh paper (≤3 years) with 0 citations is HIGH, not LIMITED — it has
   not had time to accumulate citations.
"""

from __future__ import annotations

from datetime import date

from .state import Paper

PREPRINT_SOURCE_TYPES = {"preprint", "posted-content", "postedcontent"}
PREPRINT_VENUES = {"arxiv", "biorxiv", "medrxiv", "ssrn", "research square", "techrxiv"}

PEER_REVIEWED_TYPES = {
    "journal-article", "journalarticle", "conference-paper", "proceedings-article",
    "conference", "article", "review", "review-article", "book-chapter",
    "report", "report-component",
}

AUTHORITATIVE_REPORT_SOURCES = {"nasa_ntrs", "osti"}

HIGH_CITATIONS = 10
FRESH_YEARS = 3


def _is_preprint(paper: Paper) -> bool:
    st = (paper.source_type or "").strip().lower()
    if st in PREPRINT_SOURCE_TYPES:
        return True
    if paper.tier == "T3":
        return True
    venue = (paper.journal or "").strip().lower()
    if any(v in venue for v in PREPRINT_VENUES):
        return True
    if paper.source == "arxiv":
        return True
    return False


def score_paper(paper: Paper, current_year: int | None = None) -> str:
    year_now = current_year or date.today().year

    if _is_preprint(paper):
        return "EMERGING"

    st = (paper.source_type or "").strip().lower()
    if st in PEER_REVIEWED_TYPES:
        if paper.citation_count >= HIGH_CITATIONS:
            return "HIGH"
        if paper.year and (year_now - paper.year) <= FRESH_YEARS:
            return "HIGH"
        return "MODERATE"

    if paper.tier == "T1" and paper.source in AUTHORITATIVE_REPORT_SOURCES:
        return "MODERATE"

    return "LIMITED"


def score_section_confidence(papers: list[Paper]) -> str:
    """Chapter confidence from its assigned sources — spec §9.6c."""
    highs = sum(1 for p in papers if p.confidence == "HIGH")
    moderates = sum(1 for p in papers if p.confidence == "MODERATE")
    if highs >= 3:
        return "HIGH"
    if highs >= 1 or moderates >= 2:
        return "MODERATE"
    if moderates >= 1:
        return "LIMITED"
    return "EMERGING"

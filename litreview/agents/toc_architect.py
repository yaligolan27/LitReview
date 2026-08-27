"""Stage 2 — TOC Architect (spec §9.2).

Builds the default table of contents. Every chapter carries ``keywords_en``
(the pure-Hebrew-title fix): fixed chapters get canonical English keywords,
subtopic chapters get the subtopic itself, so source assignment always has
Latin tokens to work with.
"""

from __future__ import annotations

from ..core.context import RunContext
from ..core.state import ResearchBrief, SurveyState, TocEntry


def _topic_keywords(brief: ResearchBrief) -> list[str]:
    tokens = [t for t in brief.search_topic.replace("-", " ").split() if len(t) >= 3]
    return tokens[:6]


def build_default_toc(brief: ResearchBrief) -> list[TocEntry]:
    topic_kw = _topic_keywords(brief)
    subtopics = brief.subtopics or []
    if brief.scope_preset == "summary":
        subtopics = subtopics[:2]

    toc: list[TocEntry] = [
        TocEntry(
            chapter="מבוא",
            sections=["רקע", "שאלות מחקר", "מתודולוגיה", "מבנה הסקירה"],
            keywords_en=["introduction", "overview", *topic_kw],
        ),
    ]
    if brief.scope_preset != "summary":
        toc.append(TocEntry(
            chapter="רקע תיאורטי",
            sections=["הגדרות", "תיאוריות מרכזיות", "התפתחות היסטורית"],
            keywords_en=["theory", "definitions", "foundations", *topic_kw],
        ))
    for sub in subtopics:
        toc.append(TocEntry(
            chapter=sub if not _is_latin(sub) else sub,
            sections=["הגדרה", "מצב הידע", "אתגרים"],
            keywords_en=[sub, *topic_kw],
        ))
    if brief.scope_preset != "summary":
        toc.append(TocEntry(
            chapter="ניתוח ביקורתי",
            sections=["השוואה בין גישות", "סתירות בספרות", "פערים", "מגבלות"],
            keywords_en=["comparison", "analysis", "limitations", "gaps", *topic_kw],
        ))
    toc.append(TocEntry(
        chapter="דיון ומסקנות",
        sections=["סיכום הממצאים", "מסקנות", "כיווני מחקר עתידיים"],
        keywords_en=["discussion", "conclusions", "future work", *topic_kw],
    ))
    return toc


def _is_latin(text: str) -> bool:
    return any("a" <= ch.lower() <= "z" for ch in text)


def backfill_keywords(state: SurveyState) -> None:
    """Every chapter gets English search keywords (the Hebrew-title fix)."""
    for entry in state.toc:
        if not entry.keywords_en:
            entry.keywords_en = ([entry.chapter] if _is_latin(entry.chapter) else []) + \
                _topic_keywords(state.brief)


def run_toc_architect(ctx: RunContext, state: SurveyState) -> SurveyState:
    if state.toc:
        # A TOC supplied by config / the web UI wins over the default build.
        state.log("toc", "using provided TOC", chapters=len(state.toc))
    else:
        state.toc = build_default_toc(state.brief)
        state.log("toc", "default TOC built", chapters=len(state.toc))
    # Nispachim are filtered from the writing flow (spec §9.2).
    state.toc = [t for t in state.toc if t.chapter.strip() != "נספחים"]
    backfill_keywords(state)
    return state

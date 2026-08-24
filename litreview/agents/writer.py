"""Stage 6 — Writer (spec §9.6).

Writes every chapter from its assigned sources only. Assignment is
bilingual: Latin tokens from the chapter title PLUS the chapter's
``keywords_en`` (the pure-Hebrew-title fix from spec §16 — a Hebrew chapter
title alone yields zero Latin tokens and would get zero sources).
"""

from __future__ import annotations

import re

from ..core.confidence_scorer import score_section_confidence
from ..core.context import RunContext
from ..core.state import Paper, SurveySection, SurveyState, TocEntry

TOP_PAPERS_PER_CHAPTER = 8

# Chapters about failure/criticism/history may cite retracted papers — as
# subjects, not as valid knowledge (spec §9.6a).
_RETRACTED_ALLOWED = ("כשל", "ביקורת", "סתיר", "מגבל", "היסטור",
                      "retract", "criticism", "failure", "history",
                      "controvers", "limitation")

_SYSTEM = (
    "אתה כותב אקדמי מומחה הכותב פרק בסקירת ספרות בעברית. "
    "אתה מסתמך אך ורק על המקורות שסופקו לך, ומצטט אותם במספרים [n]. "
    "לעולם אינך ממציא מקורות, מספרים או עובדות."
)


def chapter_allows_retracted(title: str) -> bool:
    lowered = title.lower()
    return any(k in lowered for k in _RETRACTED_ALLOWED)


def _tokens(text: str) -> set[str]:
    return {t for t in re.findall(r"[a-z0-9]+", text.lower()) if len(t) >= 3}


def find_relevant_papers(entry: TocEntry, papers: list[Paper],
                         top_n: int = TOP_PAPERS_PER_CHAPTER) -> list[Paper]:
    pool = [p for p in papers
            if not p.is_retracted or chapter_allows_retracted(entry.chapter)]
    keywords = _tokens(entry.chapter)
    for kw in entry.keywords_en:
        keywords |= _tokens(kw)
    if not keywords:
        # Nothing to match on — fall back to citation-count ranking.
        ranked = sorted(pool, key=lambda p: p.citation_count, reverse=True)
        return ranked[:top_n]

    scored: list[tuple[int, int, Paper]] = []
    for paper in pool:
        haystack = f"{paper.title} {paper.abstract}".lower()
        score = sum(1 for kw in keywords if kw in haystack)
        scored.append((score, paper.citation_count, paper))
    scored.sort(key=lambda t: (t[0], t[1]), reverse=True)
    top = [p for score, _, p in scored[:top_n] if score > 0]
    if len(top) < min(3, len(pool)):
        # Guarantee a floor of sources per chapter (fix for empty chapters).
        seen = {id(p) for p in top}
        for _, _, paper in scored:
            if id(paper) not in seen:
                top.append(paper)
                seen.add(id(paper))
            if len(top) >= min(3, len(pool)):
                break
    return top[:top_n]


def _sources_block(papers: list[Paper]) -> str:
    lines = ["מקורות אקדמיים מאומתים (השתמש במספרים [n] בדיוק כפי שמופיעים כאן):"]
    for i, p in enumerate(papers, start=1):
        year = p.year or "n.d."
        abstract = (p.abstract or "").strip()[:300]
        lines.append(f"- [{i}] {p.title} ({year}). {abstract}")
        if p.has_fulltext and p.fulltext_excerpt:
            lines.append(f"      קטעים מהטקסט המלא: {p.fulltext_excerpt[:400]}")
    return "\n".join(lines)


def _evidence_note(papers: list[Paper]) -> str:
    if any(p.has_fulltext for p in papers):
        return ("חלק מהמקורות כוללים קטעים מהטקסט המלא — בסס עליהם טענות חזקות.")
    return ("המקורות כוללים תקצירים בלבד — הימנע מטענות חזקות שאינן נתמכות "
            "בתקציר; סמן אי-ודאות בלשון זהירה.")


def build_chapter_prompt(state: SurveyState, entry: TocEntry,
                         chapter_no: int, papers: list[Paper]) -> str:
    sections_list = "\n".join(
        f"  {chapter_no}.{j} {name}" for j, name in enumerate(entry.sections, start=1)
    ) or f"  {chapter_no}.1 סקירה"
    return f"""כתוב את פרק {chapter_no} בסקירת ספרות אקדמית בעברית בנושא: {state.brief.topic}
קהל היעד: {state.brief.audience or 'קוראים מקצועיים'}

כותרת הפרק: {entry.chapter}
סעיפי הפרק (חובה כותרת ### לכל סעיף, בפורמט "### {chapter_no}.1 שם הסעיף"):
{sections_list}

{_sources_block(papers)}

הערה על בסיס הראיות: {_evidence_note(papers)}

===== כללי כתיבה חובה =====
1. עברית מקצועית. מונח טכני — עברית + אנגלית בסוגריים בהופעה הראשונה.
2. מינימום 6 פסקאות לפרק, לפחות 2 פסקאות לכל סעיף.
3. כל טענה מהותית מחייבת ציטוט [n] מהרשימה למעלה. אין מקור? אל תכתוב כעובדה.
4. אסור להמציא נתונים מספריים. מספר ללא מקור ייפסל בביקורת.

===== אלמנטים ויזואליים =====
שלב 1-3 אלמנטים במקומות מתאימים: [CALLOUT:blue]כותרת: תוכן[/CALLOUT] (צבעים: red/green/orange/blue/purple), **הדגשה**.
"""


def run_writer(ctx: RunContext, state: SurveyState) -> SurveyState:
    state.sections = []
    for i, entry in enumerate(state.toc, start=1):
        papers = find_relevant_papers(entry, state.papers)
        prompt = build_chapter_prompt(state, entry, i, papers)
        content = ctx.llm.complete(prompt, purpose=f"writer:ch{i}", system=_SYSTEM)
        section = SurveySection(
            title=entry.chapter,
            content=content.strip(),
            papers=papers,
            confidence=score_section_confidence(papers),
        )
        state.sections.append(section)
        ctx.emitter.emit("progress", stage="write",
                         detail=f"chapter {i}/{len(state.toc)}: {entry.chapter} "
                                f"({len(papers)} sources)")
    state.log("write", "all chapters drafted", chapters=len(state.sections))
    return state


def revise_section(ctx: RunContext, state: SurveyState, sec: SurveySection,
                   feedback: str, chapter_no: int) -> None:
    entry = next((t for t in state.toc if t.chapter == sec.title),
                 TocEntry(chapter=sec.title))
    prompt = build_chapter_prompt(state, entry, chapter_no, sec.papers)
    prompt += f"""

===== הטיוטה הקודמת =====
{sec.content}

===== הערות תיקון (חובה לטפל בכולן) =====
{feedback}
"""
    revised = ctx.llm.complete(prompt, purpose=f"writer:ch{chapter_no}", system=_SYSTEM)
    if revised.strip():
        sec.content = revised.strip()
        sec.user_edited = False
        sec.stale_grounding = True

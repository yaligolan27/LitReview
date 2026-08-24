"""Stage 8 — Critical Reviewer (spec §9.8).

Fully deterministic — zero LLM calls, so the critique never depends on model
mood (reliability mechanism #14). M1 implements the core checks; number-
without-source regex, cross-chapter repetition and KPI checks land in M3.
"""

from __future__ import annotations

import re

from ..core import markers
from ..core.context import RunContext
from ..core.state import SurveySection, SurveyState

MIN_CHAPTER_CHARS = 600
LOGIC_JUMP_UNSUPPORTED_PCT = 40.0

# A number with a unit, no [n] nearby → "number without source" (spec §9.8).
_UNIT_NUMBER = re.compile(
    r"\d+(?:\.\d+)?\s*(?:%|°|×|K\b|cm\b|mm\b|kg\b|GPa\b|MPa\b)")
_CITE_NEAR = re.compile(r"\[\d")
_BLOCKS = re.compile(
    r"\[(?:FORMULA|TABLE|KPI|KPI_DATA|ROI_CALC|EXAMPLE)\].*?"
    r"\[/(?:FORMULA|TABLE|KPI|KPI_DATA|ROI_CALC|EXAMPLE)\]", re.DOTALL)
_INLINE_MATH = re.compile(r"\\\(.*?\\\)")


def _numbers_without_source(content: str) -> list[str]:
    prose = _INLINE_MATH.sub(" ", _BLOCKS.sub(" ", content))
    findings = []
    for match in _UNIT_NUMBER.finditer(prose):
        window = prose[match.end():match.end() + 25]
        sentence_start = max(prose.rfind(".", 0, match.start()),
                            prose.rfind("\n", 0, match.start())) + 1
        sentence = prose[sentence_start:match.end() + 40]
        if len(sentence.strip()) <= 25:
            continue
        if not _CITE_NEAR.search(window):
            findings.append(match.group(0).strip())
    return findings


def _kpi_without_citation(content: str) -> int:
    count = 0
    for match in re.finditer(r"\[KPI\](.*?)\[/KPI\]", content, re.DOTALL):
        if not re.search(r"\[\d", match.group(1)):
            count += 1
    return count


def _shingles(content: str, size: int = 5) -> set[str]:
    prose = _BLOCKS.sub(" ", content)
    prose = re.sub(r"\[[^\]]*\]", " ", prose)
    words = re.findall(r"[\w֐-׿]+", prose)
    result = set()
    for i in range(len(words) - size + 1):
        shingle = " ".join(words[i:i + size])
        if len(shingle) >= 25:
            result.add(shingle)
    return result


def review_section(sec: SurveySection) -> list[str]:
    issues: list[str] = []

    unsupported = [c for c in sec.claims if c.effective_status() == "unsupported"]
    uncertain = [c for c in sec.claims if c.effective_status() == "uncertain"]

    for claim in unsupported:
        if claim.citations:
            issues.append(f"ציטוט שאינו תומך: \"{claim.text[:90]}\" — המקור שצוטט אינו תומך בטענה")
        else:
            issues.append(f"טענה ללא ציטוט: \"{claim.text[:90]}\"")
    for claim in uncertain:
        issues.append(f"טענה לא-ודאית: \"{claim.text[:90]}\" — רכך את הניסוח או הוסף מקור")

    if sec.claims:
        unsupported_pct = 100.0 * len(unsupported) / len(sec.claims)
        if unsupported_pct > LOGIC_JUMP_UNSUPPORTED_PCT:
            issues.append(
                f"קפיצות לוגיות: {unsupported_pct:.0f}% מהטענות אינן נתמכות — נדרש ביסוס מחדש של הפרק")

    if len(sec.content) < MIN_CHAPTER_CHARS:
        issues.append(f"פרק רדוד: {len(sec.content)} תווים בלבד (מינימום {MIN_CHAPTER_CHARS})")

    if "[" not in sec.content or not any(ch.isdigit() for ch in sec.content):
        issues.append("פרק ללא ציטוטים [n] כלל")

    if sec.effective_confidence() in ("LIMITED", "EMERGING"):
        issues.append(f"אמינות מקורות נמוכה לפרק: {sec.effective_confidence()}")

    for number in _numbers_without_source(sec.content)[:4]:
        issues.append(f"מספר ללא מקור: \"{number}\" — הוסף ציטוט [n] או הסר")

    kpi_missing = _kpi_without_citation(sec.content)
    if kpi_missing:
        issues.append(f"[KPI] ללא מקור: {kpi_missing} בלוקים בלי ציטוט [n]")

    for issue in markers.lint(sec.content):
        if issue.level == "error":
            issues.append(f"סמן שבור: {issue.message}")

    return issues


def build_feedback(sec: SurveySection) -> str:
    lines = [f"- {issue}" for issue in sec.issues]
    lines.append(
        "- בסס כל טענה על מקור עם ציטוט [n]; רכך טענות לא-ודאיות; הסר מספרים "
        "שאין להם מקור; אל תוסיף טענות חדשות ללא מקור.")
    return "\n".join(lines)


def _cross_chapter_repetitions(state: SurveyState) -> None:
    seen: dict[str, int] = {}
    reported: set[tuple[int, int]] = set()
    for i, sec in enumerate(state.sections):
        for shingle in _shingles(sec.content):
            if shingle in seen and seen[shingle] != i:
                pair = (seen[shingle], i)
                if pair not in reported:
                    reported.add(pair)
                    other = state.sections[seen[shingle]].title
                    sec.issues.append(
                        f"חזרה בין פרקים: הרצף \"{shingle[:50]}...\" מופיע גם בפרק "
                        f"\"{other}\"")
            else:
                seen[shingle] = i


def run_critical_reviewer(ctx: RunContext, state: SurveyState) -> SurveyState:
    for sec in state.sections:
        sec.issues = review_section(sec)
    _cross_chapter_repetitions(state)
    total = sum(len(s.issues) for s in state.sections)
    state.log("review", "critical review complete",
              issues=total, chapters_with_issues=sum(1 for s in state.sections if s.issues))
    return state

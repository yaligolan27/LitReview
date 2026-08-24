"""Stage 8 — Critical Reviewer (spec §9.8).

Fully deterministic — zero LLM calls, so the critique never depends on model
mood (reliability mechanism #14). M1 implements the core checks; number-
without-source regex, cross-chapter repetition and KPI checks land in M3.
"""

from __future__ import annotations

from ..core import markers
from ..core.context import RunContext
from ..core.state import SurveySection, SurveyState

MIN_CHAPTER_CHARS = 600
LOGIC_JUMP_UNSUPPORTED_PCT = 40.0


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


def run_critical_reviewer(ctx: RunContext, state: SurveyState) -> SurveyState:
    total = 0
    for sec in state.sections:
        sec.issues = review_section(sec)
        total += len(sec.issues)
    state.log("review", "critical review complete",
              issues=total, chapters_with_issues=sum(1 for s in state.sections if s.issues))
    return state

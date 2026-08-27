"""Stage 14 — Ideation Engine (spec §9.14).

Seven categories of generated ideas, fed by the knowledge gaps the grounding
found. Absolute separation: every item is marked "Generated Idea" and the
whole block opens with a disclaimer — never a research claim, never
source-grounded.
"""

from __future__ import annotations

from ..core.context import RunContext
from ..core.llm import extract_json
from ..core.state import SurveyState

CATEGORIES = {
    "further_research": "מחקר המשך",
    "product_directions": "כיווני מוצר",
    "mvp": "MVP",
    "experiments": "ניסויים",
    "business_uses": "שימושים עסקיים",
    "risks": "סיכונים",
    "open_questions": "שאלות פתוחות",
}

_SYSTEM = (
    "אתה מנוע רעיונות. הרעיונות שלך מסומנים כתוכן שנוצר על ידי המערכת — "
    "לא טענות מחקריות. החזר JSON בלבד."
)


def _gaps(state: SurveyState) -> list[str]:
    gaps = []
    for chapter in state.grounding_report.get("by_chapter", []):
        weak = chapter.get("uncertain", 0) + chapter.get("unsupported", 0)
        if weak:
            gaps.append(f"{chapter['chapter']}: {weak} טענות לא מבוססות דיין")
    return gaps


def run_ideation_engine(ctx: RunContext, state: SurveyState) -> SurveyState:
    gaps = _gaps(state)
    prompt = (
        f'נושא הסקירה: {state.brief.topic}\n'
        f'מטרות: {", ".join(state.brief.goals)}\n'
        f'פערי ידע שזוהו בעיגון הטענות:\n' +
        "\n".join(f"- {g}" for g in gaps or ["לא זוהו פערים בולטים"]) +
        "\n\nהפק 2-4 רעיונות לכל קטגוריה. החזר JSON עם המפתחות: " +
        ", ".join(CATEGORIES) +
        ' — כל ערך הוא רשימת מחרוזות בעברית.'
    )
    try:
        data = extract_json(ctx.llm.complete(prompt, purpose="ideation", system=_SYSTEM))
    except ValueError:
        data = {}
    ideation = {}
    if isinstance(data, dict):
        for key in CATEGORIES:
            items = data.get(key) or []
            ideation[key] = [str(i).strip() for i in items if str(i).strip()][:4]
    state.ideation = ideation
    state.log("ideation", "ideation complete",
              items=sum(len(v) for v in ideation.values()), gaps_used=len(gaps))
    return state

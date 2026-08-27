"""Stage 10 — Executive Translator (spec §9.10).

Takes the chapters' [KPI] blocks as hints and produces the executive
summary: opening paragraph, 4-6 [KPI_DATA] boxes, 5-7 [CONCLUSION] lines and
an explicit [ROI_CALC]. ``_parse_kpi_data`` extracts the boxes into
``state.kpi_data`` for the HTML KPI grid.
"""

from __future__ import annotations

import re

from ..core.context import RunContext
from ..core.state import SurveyState

_SYSTEM = (
    "אתה מתרגם ממצאים אקדמיים לשפת מקבלי החלטות. אתה נסמך אך ורק על תוכן "
    "הפרקים שסופקו, ואינך ממציא מספרים."
)

_KPI_DATA = re.compile(r"\[KPI_DATA\](.*?)\[/KPI_DATA\]", re.DOTALL)
_FIELD = re.compile(r"(NUM|LABEL|DESC|CITE)\s*:\s*([^|\[\]]*)")


def _collect_kpi_hints(state: SurveyState) -> list[str]:
    hints = []
    for sec in state.sections:
        for match in re.finditer(r"\[KPI\](.*?)\[/KPI\]", sec.content, re.DOTALL):
            hints.append(match.group(1).strip())
    return hints[:10]


def build_prompt(state: SurveyState) -> str:
    chapters_digest = "\n".join(
        f"## {s.title}\n{s.content[:1500]}" for s in state.sections)
    kpi_hints = _collect_kpi_hints(state)
    hints_block = ("\nרמזי KPI מהפרקים:\n" + "\n".join(f"- {h}" for h in kpi_hints)
                   if kpi_hints else "")
    return f"""כתוב תקציר מנהלים לסקירת הספרות "{state.brief.topic}" עבור {state.brief.audience or 'מקבלי החלטות'}.
{hints_block}

תוכן הפרקים:
{chapters_digest}

===== מבנה נדרש (חובה) =====
1. פסקת פתיחה של 3-4 משפטים.
2. 4-6 בלוקים של [KPI_DATA]NUM: ערך|LABEL: תווית קצרה|DESC: תיאור|CITE: [n][/KPI_DATA]
3. 5-7 בלוקים של [CONCLUSION]**שם הממצא** — הסבר עם ציטוט [n][/CONCLUSION]
4. חישוב כלכלי מפורש אחד: [ROI_CALC]X × Y × Z = סכום[/ROI_CALC]
אסור להמציא מספרים — רק ערכים שמופיעים בפרקים או נגזרים מהם בחישוב מוצהר.
"""


def parse_kpi_data(text: str) -> list[dict]:
    boxes = []
    for match in _KPI_DATA.finditer(text):
        fields = {key.upper(): value.strip()
                  for key, value in _FIELD.findall(match.group(1))}
        cite = re.search(r"CITE\s*:\s*(\[[\d,\-\s]+\])", match.group(1))
        boxes.append({
            "num": fields.get("NUM", ""),
            "label": fields.get("LABEL", ""),
            "desc": fields.get("DESC", ""),
            "cite": cite.group(1) if cite else "",
        })
    return [b for b in boxes if b["num"]]


def run_executive_translator(ctx: RunContext, state: SurveyState) -> str:
    text = ctx.llm.complete(build_prompt(state), purpose="executive",
                            system=_SYSTEM, max_tokens=2000)
    state.executive_summary = text.strip()
    state.kpi_data = parse_kpi_data(text)
    state.log("executive", "executive summary built",
              kpi_boxes=len(state.kpi_data),
              conclusions=text.count("[CONCLUSION]"))
    return state.executive_summary

"""Part-E §22.3 — automatic glossary (flag: SURVEY_GLOSSARY).

After writing: extract the 20-40 central terms with a one-line plain-Hebrew
definition each → a "מילון מונחים" appendix in the document.
"""

from __future__ import annotations

from ..core.context import RunContext
from ..core.llm import extract_json
from ..core.state import SurveyState


def run_glossary(ctx: RunContext, state: SurveyState) -> SurveyState:
    if not ctx.settings.glossary or not state.sections:
        state.log("glossary", "glossary disabled or no chapters")
        return state
    digest = "\n\n".join(f"## {s.title}\n{s.content[:1200]}" for s in state.sections[:10])
    prompt = (
        "חלץ מהטקסט את 20-40 המונחים המקצועיים המרכזיים. לכל מונח כתוב הגדרה "
        "של שורה אחת בשפה פשוטה, בלי ז'רגון. החזר JSON: "
        '{"terms": [{"term": "...", "plain_definition": "..."}]}\n\n' + digest
    )
    try:
        data = extract_json(ctx.llm.complete(prompt, purpose="glossary"))
        terms = data.get("terms", []) if isinstance(data, dict) else []
    except ValueError:
        terms = []
    state.glossary = [
        {"term": str(t.get("term", "")).strip(),
         "definition": str(t.get("plain_definition", t.get("definition", ""))).strip()}
        for t in terms
        if isinstance(t, dict) and str(t.get("term", "")).strip()
    ][:40]
    state.log("glossary", "glossary built", terms=len(state.glossary))
    return state

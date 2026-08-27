"""M8 — the Deep Interview (ראיון עומק), a new method stage before the TOC.

The single biggest lever on survey quality is how precisely the system
understands what the user wants. This agent runs an open-ended interview —
as long as the user cares to go — through the regular LLM gateway (so in
native mode the user's own Claude session is the interviewer), then distills
everything into a **research charter**: a rich markdown brief that is merged
into ``ResearchBrief`` and injected into the planner / deep-research /
writer prompts.

The interviewer NEVER generates survey content. It only asks, reflects and
summarizes. The charter influences *what* gets researched and written; every
fact still comes from the databases through the normal verification layers.
"""

from __future__ import annotations

from typing import Any

from ..core.context import RunContext
from ..core.llm import extract_json
from ..core.state import ResearchBrief

MAX_TRANSCRIPT_CHARS = 60_000       # keep the prompt bounded on marathon interviews
CHARTER_PROMPT_CAP = 4_000          # chars of charter injected into writing prompts

INTERVIEW_SYSTEM = (
    "אתה מראיין מחקר מומחה, בשלב ההכנה לכתיבת סקר ספרות אקדמי. תפקידך היחיד: "
    "להוציא מהמשתמש בשיחה את מלוא הידע, הכוונות והעדפות — לא לכתוב את הסקר, "
    "לא להציע תוכן, ולא לענות על שאלות המחקר בעצמך.\n"
    "כללי הראיון:\n"
    "1. שאל 2-4 שאלות בכל תור, ממוקדות וקצרות, בעברית.\n"
    "2. סגנון סקר: לכל שאלה הצע 3-5 אפשרויות תשובה מוכנות, קונקרטיות "
    "ומותאמות לנושא ולתשובות הקודמות — כך שהמשתמש יוכל פשוט ללחוץ. אפשרויות "
    "גנריות ('כן/לא/אולי') אסורות אלא אם השאלה באמת בינארית.\n"
    "3. העמק: כשעולה תשובה מעניינת או עמומה — שאל שאלת המשך לפני שתעבור הלאה.\n"
    "4. כל 3-4 תורות פתח את ה-intro ב'עד כה הבנתי ש…' — סיכום ביניים קצר.\n"
    "5. כסה בהדרגה את הממדים (לא בהכרח בסדר הזה):\n"
    "   א. מטרה ושימוש — למה הסקר נחוץ, מה ייעשה איתו, מי מקבל החלטה בעקבותיו.\n"
    "   ב. שאלות המחקר המדויקות — מה חייב להיענות כדי שהסקר יצליח.\n"
    "   ג. גבולות — מה בפנים ומה מחוץ לתחום, ולמה.\n"
    "   ד. קהל — מי קורא, מה הידע המוקדם שלו, כמה טכני מותר להיות.\n"
    "   ה. מחלוקות ועמדות — אילו ויכוחים בתחום חשובים, האם יש עמדה לבחון.\n"
    "   ו. מקורות — מאמרים/חוקרים/זרמים שחובה לכלול, מקורות שהמשתמש לא סומך עליהם.\n"
    "   ז. תיחום — שנים, גיאוגרפיה, שפות, סוגי פרסומים.\n"
    "   ח. התוצר — היקף, פרקים שכבר ברור שצריך, אלמנטים (נוסחאות/דוגמאות/טבלאות), טון.\n"
    "   ט. קריטריוני הצלחה — איך המשתמש יידע שהסקר טוב.\n"
    "6. אל תמהר לסיים. כשנדמה שמוצה — חפש זווית שלא כוסתה. רק כשבאמת אין "
    "חדש, סמן done_hint=true (המשתמש עדיין יכול להמשיך, ואתה ממשיך לענות).\n"
    "7. פורמט חובה — JSON יחיד:\n"
    '{"intro": "משפט פתיחה/סיכום ביניים (או ריק)", "questions": [{"text": '
    '"השאלה", "options": ["אפשרות 1", "אפשרות 2", "אפשרות 3"], "multi": '
    'false|true (אפשר לבחור כמה), "allow_other": true}], "done_hint": false|true}'
)

_CHARTER_INSTRUCTIONS = (
    'החזר JSON יחיד במבנה הבא (שדה שלא עלה בראיון — null או רשימה ריקה):\n'
    '{"charter": "מסמך markdown מפורט בעברית: מטרת הסקר ושימושו, שאלות המחקר, '
    'גבולות (בפנים/בחוץ), קהל וידע מוקדם, מחלוקות שיש לכסות, דגשי מקורות, '
    'תיחום, מבנה ותוצר רצוי, קריטריוני הצלחה, וכל דגש נוסף שעלה. כתוב כהנחיות '
    'מחייבות לצוות שכותב את הסקר.",\n'
    ' "search_topic": "נושא חיפוש באנגלית, מדויק ככל שעלה" | null,\n'
    ' "goals": ["מטרות בעברית"],\n'
    ' "subtopics_en": ["תתי-נושאים באנגלית לחיפוש במאגרים"],\n'
    ' "audience": "..." | null,\n'
    ' "year_from": שנה | null, "year_to": שנה | null,\n'
    ' "languages": ["English", ...] | [],\n'
    ' "must_include_papers": ["DOI או כותרת שחובה לכלול"],\n'
    ' "scope_preset": "summary" | "full" | null}\n'
    "אל תמציא דבר שלא נאמר בראיון."
)


def turn_to_text(turn: dict[str, Any]) -> str:
    """A survey-style turn → readable plain text (transcript + UI fallback)."""
    lines = []
    intro = str(turn.get("intro", "")).strip()
    if intro:
        lines.append(intro)
    for i, q in enumerate(turn.get("questions") or [], start=1):
        lines.append(f"{i}. {str(q.get('text', '')).strip()}")
        options = [str(o).strip() for o in (q.get("options") or []) if str(o).strip()]
        if options:
            lines.append("   אפשרויות: " + " | ".join(options))
    if turn.get("done_hint"):
        lines.append("(נראה שהתמונה מלאה — אפשר ללחוץ 'סיים ראיון והפק אמנה', "
                     "או להמשיך להוסיף.)")
    return "\n".join(lines).strip()


def normalize_turn(raw: str) -> dict[str, Any]:
    """Parse a model reply into the survey-turn shape. A free-form (non-JSON)
    reply degrades gracefully to an intro with no prepared options, so a
    serving session that answers in plain text still works."""
    try:
        data = extract_json(raw)
        assert isinstance(data, dict)
    except (ValueError, AssertionError):
        return {"intro": raw.strip(), "questions": [], "done_hint": False}
    questions = []
    for q in (data.get("questions") or [])[:6]:
        if not isinstance(q, dict) or not str(q.get("text", "")).strip():
            continue
        questions.append({
            "text": str(q["text"]).strip(),
            "options": [str(o).strip() for o in (q.get("options") or [])
                        if str(o).strip()][:6],
            "multi": bool(q.get("multi")),
            "allow_other": q.get("allow_other", True) is not False,
        })
    turn = {"intro": str(data.get("intro", "")).strip(),
            "questions": questions,
            "done_hint": bool(data.get("done_hint"))}
    if not turn["intro"] and not questions:
        return {"intro": raw.strip(), "questions": [], "done_hint": False}
    return turn


def _transcript(messages: list[dict[str, Any]]) -> str:
    lines = []
    for m in messages:
        speaker = "משתמש" if m.get("role") == "user" else "מראיין"
        lines.append(f"{speaker}: {m.get('text', '')}")
    text = "\n\n".join(lines)
    if len(text) > MAX_TRANSCRIPT_CHARS:
        text = "[…תחילת הראיון קוצרה…]\n\n" + text[-MAX_TRANSCRIPT_CHARS:]
    return text


def _brief_block(brief: ResearchBrief) -> str:
    return (
        f"נושא (כפי שהוזן בטופס): {brief.topic or '—'}\n"
        f"נושא חיפוש: {brief.search_topic or '—'}\n"
        f"מטרות: {', '.join(brief.goals) or '—'}\n"
        f"תתי-נושאים: {', '.join(brief.subtopics) or '—'}\n"
        f"קהל: {brief.audience or '—'} · שנים: {brief.year_from}–{brief.year_to} · "
        f"שפות: {', '.join(brief.languages)}"
    )


def next_turn(ctx: RunContext, brief: ResearchBrief,
              messages: list[dict[str, Any]]) -> dict[str, Any]:
    """One interviewer turn — a survey-style turn dict: opening questions on
    an empty transcript, otherwise a follow-up over the whole conversation."""
    if not messages:
        prompt = (
            "זהו פתיחת הראיון. פרטי הטופס שהמשתמש מילא:\n"
            f"{_brief_block(brief)}\n\n"
            "פתח את הראיון: intro קצר שמסביר שזהו ראיון עומק שמטרתו סקר מדויק "
            "יותר, ואז 3-4 שאלות הפתיחה החשובות ביותר לנושא הזה — כל אחת עם "
            "אפשרויות מוכנות ללחיצה. החזר JSON בפורמט המחייב."
        )
    else:
        prompt = (
            f"פרטי הטופס:\n{_brief_block(brief)}\n\n"
            f"הראיון עד כה:\n{_transcript(messages)}\n\n"
            "המשך את הראיון: התור הבא שלך כמראיין, בפורמט ה-JSON המחייב — "
            "שאלות עם אפשרויות מוכנות, מותאמות למה שכבר נענה."
        )
    raw = ctx.llm.complete(prompt, purpose="interview", system=INTERVIEW_SYSTEM)
    return normalize_turn(raw)


def build_charter(ctx: RunContext, brief: ResearchBrief,
                  messages: list[dict[str, Any]]) -> dict[str, Any]:
    """Distill the whole interview into the structured charter."""
    prompt = (
        f"פרטי הטופס:\n{_brief_block(brief)}\n\n"
        f"תמליל הראיון המלא:\n{_transcript(messages)}\n\n"
        f"{_CHARTER_INSTRUCTIONS}"
    )
    data = extract_json(ctx.llm.complete(prompt, purpose="interview_charter",
                                         system=INTERVIEW_SYSTEM))
    if not isinstance(data, dict) or not str(data.get("charter", "")).strip():
        raise ValueError("interview charter missing or malformed")
    return data


def apply_charter(brief_doc: dict[str, Any], charter: dict[str, Any]) -> list[str]:
    """Merge the charter into a brief DICT (the server's stored form),
    non-destructively: lists are extended (deduped), scalars fill only when
    the charter provides them. Returns the changed field names (audit)."""
    changed: list[str] = []

    def _extend(field: str, values: Any) -> None:
        new = [str(v).strip() for v in (values or []) if str(v).strip()]
        if not new:
            return
        current = [str(v) for v in (brief_doc.get(field) or [])]
        merged = current + [v for v in new if v not in current]
        if merged != current:
            brief_doc[field] = merged
            changed.append(field)

    def _fill(field: str, value: Any) -> None:
        if value in (None, "", []):
            return
        if brief_doc.get(field) != value:
            brief_doc[field] = value
            changed.append(field)

    _fill("charter", str(charter.get("charter", "")).strip())
    _fill("search_topic", (charter.get("search_topic") or "").strip() or None)
    _fill("audience", (charter.get("audience") or "").strip() or None)
    _extend("goals", charter.get("goals"))
    _extend("subtopics", charter.get("subtopics_en"))
    _extend("languages", charter.get("languages"))
    _extend("user_papers", charter.get("must_include_papers"))
    for field in ("year_from", "year_to"):
        value = charter.get(field)
        if isinstance(value, int) and 1900 < value < 2100:
            _fill(field, value)
    scope = charter.get("scope_preset")
    if scope in ("summary", "full"):
        _fill("scope_preset", scope)
    return changed


def charter_prompt_block(brief: ResearchBrief) -> str:
    """The injection block for writing/planning prompts ('' when no charter)."""
    if not brief.charter:
        return ""
    text = brief.charter[:CHARTER_PROMPT_CAP]
    return (
        "===== אמנת המחקר (מראיון העומק עם המשתמש — מחייב) =====\n"
        f"{text}\n"
        "פעל לפי האמנה בכל החלטת תוכן, דגש, טון והיקף. אם האמנה סותרת הנחיה "
        "כללית — האמנה גוברת, מלבד כללי הציטוט והאמינות שלעולם אינם נדחים.\n"
    )

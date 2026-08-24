"""Deterministic offline responses for every purpose (spec §7.5).

Not lorem ipsum: the mock returns *valid* answers — Hebrew chapters with
markers and [n] citations, grounder verdicts with all three statuses,
deep-research findings with URLs and quotes, and ``dr_round`` ≥ 2 returns an
empty findings list on purpose, so saturation-stop logic is exercised.
This backend is the regression baseline for the whole pipeline.
"""

from __future__ import annotations

import hashlib
import json
import re


def _seed(prompt: str) -> int:
    return int(hashlib.sha1(prompt.encode("utf-8")).hexdigest()[:8], 16)


def _claims_count(prompt: str) -> int:
    m = re.search(r"CLAIMS_COUNT:\s*(\d+)", prompt)
    return int(m.group(1)) if m else 3


def _chapter_number(purpose: str) -> int:
    m = re.search(r"(\d+)$", purpose)
    return int(m.group(1)) if m else 1


_WRITER_TEMPLATE = """בפרק זה נסקרת הספרות המרכזית בתחום, תוך הבחנה בין הגישות המרכזיות שהתפתחו בשנים האחרונות. המחקר המוקדם ביסס את המסגרת המושגית של התחום והגדיר את שאלות היסוד [1]. בהמשך, עבודות מאוחרות יותר הרחיבו את היריעה ובחנו את הסוגיה ממגוון זוויות מתודולוגיות [2].

### {n}.1 מצב הידע הנוכחי

הספרות העדכנית מצביעה על התכנסות הדרגתית סביב מספר עקרונות מרכזיים. מחקר מקיף שנערך לאחרונה מצא כי הגישות המשלבות מספר שיטות מניבות תוצאות עקביות יותר מגישות חד-ממדיות [1,2]. עם זאת, חוקרים אחדים מדגישים כי הראיות עדיין חלקיות, וכי נדרש מחקר נוסף כדי לבסס את התוקף החיצוני של הממצאים [3].

[CALLOUT:blue]נקודת מפתח: הספרות מבחינה בין הרמה התיאורטית (theoretical) לרמה היישומית — ההבחנה הזו חוזרת לאורך כל הפרק.[/CALLOUT]

יעילות התהליך מוגדרת בספרות כיחס שבין התפוקה לקלט:

[FORMULA]\\eta = P_{{out}} / P_{{in}}[/FORMULA]

כאשר: \\(\\eta\\) — היעילות; \\(P_{{out}}\\) — התפוקה בפועל; \\(P_{{in}}\\) — סך המשאבים שהושקעו [1].

### {n}.2 השוואת גישות

[TABLE]| גישה | בשלות | עלות |
| --- | --- | --- |
| גישה משולבת [BEST] | גבוהה | בינונית |
| גישה חד-ממדית | בינונית | נמוכה |
| גישה ידנית [BAD] | גבוהה | גבוהה |[/TABLE]

הטבלה ממחישה את הפער בין הגישות כפי שמתואר בספרות [2]. רמת הבשלות הכוללת של התחום מוערכת כ-[TRL:6] בקירוב.

[CASE]יישום מוסדי|פיילוט, הערכה|מוסד מחקר שהטמיע את הגישה המשולבת דיווח על שיפור עקבי בתהליכי העבודה, בכפוף למגבלות המדגם [2].[/CASE]

### {n}.3 אתגרים ומגבלות

לצד ההתקדמות, הספרות מתעדת אתגרים מהותיים. ראשית, קיימת שונות גדולה בהגדרות העבודה בין מחקרים שונים, המקשה על השוואה ישירה [3]. שנית, חלק ניכר מהמחקרים מבוססים על מדגמים מצומצמים, ולכן יש לנקוט זהירות בהכללת המסקנות [4]. חשוב לציין כי תחום זה מתפתח במהירות, וייתכן שממצאים עדכניים ישנו את התמונה.

[KPI]73%|שיעור הדיווח על שיפור במדדים המרכזיים|[1]|במחקרים שנסקרו[/KPI]

לסיכום ביניים, **הכיוון המסתמן בספרות** הוא שילוב בין גישות משלימות, תוך הקפדה על מתודולוגיה שקופה וניתנת לשחזור [1,4]. הפרקים הבאים מרחיבים את הדיון בהיבטים היישומיים של הנושא.{web_line}
"""


def complete(prompt: str, purpose: str, system: str = "") -> str:
    seed = _seed(prompt)

    if purpose == "toc_review":
        return "approved"
    if purpose in ("sources_review", "draft_review"):
        return "approved"

    if purpose == "domain_classification":
        return json.dumps({"domains": ["cs_ai"]})

    if purpose == "query_translate":
        # Translation failure for a language is silently skipped by the hunter,
        # so an empty mapping is a valid, honest mock.
        return json.dumps({"translations": {}})

    if purpose == "query_expansion":
        return json.dumps({"concept_blocks": [
            {"concept": "core method", "synonyms": ["approach"],
             "technical_terms": ["framework"], "abbreviations": []},
        ]})

    if purpose == "query_refine":
        return json.dumps({"queries": [f"coverage gap query {seed % 7}"]})

    if purpose == "toc_gaps":
        return json.dumps({"suggestions": [
            {"kind": "chapter", "title": "שיקולים אתיים ורגולציה",
             "parent": "", "reason": "היבט שאינו מכוסה בפרקים הקיימים"},
        ]})

    if purpose == "dr_plan":
        return json.dumps({
            "relevance": "medium",
            "rationale": "לנושא יש היבטי שוק ורגולציה פעילים.",
            "catalog_potential": True,
            "entity_type": "vendors",
            "subquestions": [
                {"q": "מי השחקנים המרכזיים בתחום?", "angle": "market",
                 "target_sources": ["vendor sites", "industry press"]},
                {"q": "מה מצב הרגולציה העדכני?", "angle": "regulation",
                 "target_sources": ["gov sites"]},
            ],
        })

    if purpose.startswith("dr_round"):
        round_no = _chapter_number(purpose)
        if round_no >= 2:
            return json.dumps({"round_summary": "אין ממצאים חדשים", "queries_run": 2,
                               "pages_read": 3, "findings": []})
        return json.dumps({
            "round_summary": "סבב ראשון: מיפוי שחקנים ורגולציה",
            "queries_run": 4,
            "pages_read": 6,
            "findings": [
                {"id": "F1", "type": "market", "heading": "שחקן מוביל בתחום",
                 "insight": "החברה המובילה הכריזה על מוצר חדש בתחום.",
                 "url": "https://example.gov/report-2026",
                 "source_name": "Gov Report", "date": "2026-01",
                 "quote": "The agency published its annual assessment."},
                {"id": "F2", "type": "stat", "heading": "היקף שוק",
                 "insight": "היקף השוק מוערך בכ-2 מיליארד דולר.",
                 "url": "https://example-news.com/market-size",
                 "source_name": "Industry News", "date": "2025-11",
                 "quote": "The market is estimated at $2B."},
            ],
        })

    if purpose == "dr_verify":
        return json.dumps({"verdicts": [
            {"id": "F2", "verdict": "corroborated",
             "second_url": "https://another-domain.org/analysis",
             "second_source": "Analysis Org", "note": "נתון תואם בדוח עצמאי"},
        ]})

    if purpose == "dr_contradictions":
        return json.dumps({"contradictions": []})

    if purpose == "dr_entities":
        return json.dumps({
            "entity_type": "vendors",
            "columns": ["שם", "מוצר", "סטטוס"],
            "rows": [
                {"cells": ["Vendor A", "Product X", "פעיל"],
                 "source_url": "https://example.gov/report-2026",
                 "source_name": "Gov Report"},
            ],
        })

    if purpose.startswith("dr_trace"):
        return json.dumps({"traces": []})

    if purpose == "source_scout":
        return json.dumps({"suggestions": []})

    if purpose.startswith("writer:ch"):
        web_line = ""
        if "ממצאי deep-research" in prompt:
            web_line = ("\n\nבהקשר התעשייתי, גורמים בשוק מדווחים על "
                        "התרחבות הפעילות בתחום [W1].")
        return _WRITER_TEMPLATE.format(n=_chapter_number(purpose), web_line=web_line)

    if purpose == "grounder":
        count = _claims_count(prompt)
        statuses = ["supported", "uncertain", "supported", "unsupported"]
        verdicts = []
        for i in range(count):
            status = statuses[(seed + i) % len(statuses)]
            verdicts.append({
                "index": i + 1,
                "status": status,
                "reason": "המקור תומך בטענה" if status == "supported"
                else "המקור אינו מכסה את מלוא הטענה",
                "rewrite": "" if status == "supported"
                else "על פי הספרות, ייתכן שהממצא תקף בחלק מההקשרים.",
            })
        return json.dumps(verdicts, ensure_ascii=False)

    if purpose == "executive":
        return (
            "סקירה זו ממפה את מצב הידע העדכני בתחום ומצביעה על מגמות מרכזיות.\n"
            "[KPI_DATA]NUM: 47|LABEL: מקורות|DESC: מקורות שנותחו בסקירה|CITE: [1][/KPI_DATA]\n"
            "[KPI_DATA]NUM: 68%|LABEL: עדכניות|DESC: מקורות מהשנים האחרונות|CITE: [2][/KPI_DATA]\n"
            "[KPI_DATA]NUM: 3|LABEL: גישות|DESC: משפחות גישות מרכזיות|CITE: [1][/KPI_DATA]\n"
            "[KPI_DATA]NUM: 4|LABEL: פערים|DESC: פערי מחקר מזוהים|CITE: [3][/KPI_DATA]\n"
            "[CONCLUSION]**התכנסות מתודולוגית** — הספרות מתכנסת סביב גישות משולבות [1][/CONCLUSION]\n"
            "[CONCLUSION]**פער תקינה** — היעדר מדדים אחידים מקשה על השוואה [3][/CONCLUSION]\n"
            "[CONCLUSION]**בסיס ראיות חלקי** — נדרש מחקר המשך רחב היקף [4][/CONCLUSION]\n"
            "[CONCLUSION]**רלוונטיות יישומית** — קיים ביקוש גובר בתעשייה [2][/CONCLUSION]\n"
            "[CONCLUSION]**כיוון עתידי** — שילוב שיטות הוא הכיוון המסתמן [1][/CONCLUSION]\n"
            "[ROI_CALC]חיסכון שנתי משוער = 3 תהליכים × 40 שעות × 200 ₪ = 24,000 ₪[/ROI_CALC]"
        )

    if purpose == "hebrew_editor":
        m = re.search(r"===TEXT===\n(.*?)\n===END===", prompt, re.DOTALL)
        original = m.group(1) if m else prompt
        return f"===TEXT===\n{original}\n===END==="

    if purpose == "evaluator":
        return json.dumps({"hebrew_quality": 8, "coherence": 8,
                           "notes": "מבנה ברור; ניסוח תקין."})

    if purpose == "ideation":
        return json.dumps({
            "further_research": ["בחינת הממצאים על מדגם רחב"],
            "product_directions": ["כלי תומך החלטה"],
            "mvp": ["אב-טיפוס ממוקד תרחיש אחד"],
            "experiments": ["ניסוי מבוקר להשוואת גישות"],
            "business_uses": ["שירות ניתוח לארגונים"],
            "risks": ["תלות באיכות הנתונים"],
            "open_questions": ["מהם תנאי התוקף של הממצאים?"],
        }, ensure_ascii=False)

    if purpose == "glossary":
        return json.dumps({"terms": []})

    if purpose == "web_landscape":
        return json.dumps({"summary": "", "findings": []})

    # Unknown purposes get an explicit marker so tests catch them.
    return f"MOCK-UNHANDLED-PURPOSE:{purpose}"

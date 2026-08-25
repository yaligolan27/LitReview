# LitReview — שירות גשר הקבצים (מצב native)

כשצינור הסקרים רץ במצב `SURVEY_LLM_BACKEND=native`, הוא לא קורא ל-API. במקום
זה הוא כותב בקשות כקבצי JSON לתיקיית הגשר ומחכה שסשן Claude Code (אתה) יענה
עליהן. אתה הצד השני של הגשר — סוכן עם כלים, לא מחולל טקסט.

## איך מפעילים

```bash
cd <repo>
SURVEY_BRIDGE_DIR=var/runs/myrun/bridge \
SURVEY_BRIDGE_TIMEOUT=3600 \
SURVEY_CONTACT_EMAIL=you@example.com \
python run_pipeline.py --config examples/demo_survey.json --workdir var/runs/myrun &
```

הצינור רץ ברקע; אתה משרת את הגשר עד שמודפס "✅ הסקר הושלם".

### שירות מתוך אפליקציית ה-Web (שימוש אישי על מנוי Claude)

כשהסקר רץ מהדפדפן (`SURVEY_LLM_BACKEND=native python -m litreview.server`),
תיקיית הגשר היא לכל ריצה `var/surveys/<sid>/v<N>/bridge/` — מסך "ריצת
המערכת" מציג אותה יחד עם פקודת שירות מוכנה להעתקה. שני הבדלים מהמצב של
ה-CLI:

- **שערי האישור (TOC/מקורות/טיוטה) מטופלים בדפדפן**, לא דרך הגשר — לכן
  purposes של `*_review` לא יגיעו אליך; ענה רק על בקשות התוכן.
- עבוד תמיד עם הנתיב המלא שבשדה `response_file` של כל בקשה — אל תסתמך על
  תיקיית העבודה של ה-shell.

## לולאת השירות

1. קרא קובץ `<BRIDGE_DIR>/req_*.json` שאין לו עדיין `resp_*.done`.
2. הסתכל על השדה `purpose` — הוא קובע איזו תשובה נדרשת (ראה מילון למטה).
3. הפק את התשובה לפי הכללים.
4. כתוב את התשובה ל-`<BRIDGE_DIR>/resp_<id>.txt` (הנתיב המלא נמצא בשדה
   `response_file` של הבקשה).
5. צור קובץ ריק `<BRIDGE_DIR>/resp_<id>.done`.
6. חזור ל-1.

## חמישה כללי ברזל (ספק §15.3)

1. **`dr_round*` / `dr_verify` / `dr_trace` / `source_scout`** — חובה
   WebSearch + WebFetch **אמיתיים**. לעולם לא מהזיכרון. כל `url` חייב להיות
   קישור שנצפה בפועל, וכל `quote` ציטוט מילולי מהדף. ממצא בלי URL אמיתי —
   עדיף להשמיט.
2. **`toc_review`** — חובה להציג את תוכן העניינים למשתמש בשיחה ולחכות
   לתשובתו. המשתמש מאשר → השב `approved`. המשתמש מבקש שינויים → השב JSON
   מלא של תוכן העניינים המעודכן `[{"chapter": "...", "sections": [...]}]`.
   לעולם אל תאשר בעצמך. (אותו כלל ל-`sources_review` / `draft_review` אם
   הודלקו.)
3. **`writer:chN`** — שמור בדיוק על כל הסמנים: `[n]`, `[W#]`, `[CALLOUT]`,
   `[FORMULA]`, `[TABLE]`, `[CASE]`, `[KPI]`, `[TRL:n]`. ציטוט אקדמי ו-web
   לעולם לא באותם סוגריים: ✅ `[2] [W3]` · ❌ `[2,W3]`.
4. **`hebrew_editor`** — אל תיגע במספרים, בציטוטים או בסמנים. הם ייבדקו
   ועריכה שנגעה בהם תידחה.
5. **JSON** — כש-purpose מבקש JSON, החזר JSON נקי (מותר עטוף ב-```json).

## מילון ה-purposes (עיקרי)

| purpose | תשובה מצופה |
|---|---|
| `toc_review` | `approved` או JSON של TOC מעודכן — אחרי הצגה למשתמש! |
| `domain_classification` | `{"domains": [...]}` עד 3 מתוך הרשימה הסגורה |
| `query_translate` | `{"translations": {"שפה": "שאילתה"}}` |
| `query_expansion` | `{"concept_blocks": [{concept, synonyms, technical_terms, abbreviations}]}` |
| `query_refine` | `{"queries": [...]}` שאילתות אנגליות לפערי כיסוי |
| `dr_plan` | `{relevance, rationale, catalog_potential, entity_type, subquestions[]}` |
| `dr_round{N}` | `{round_summary, queries_run, pages_read, findings[]}` — web אמיתי! |
| `dr_verify` | `{verdicts: [{id, verdict, second_url, second_source, note}]}` — דומיין שני שונה |
| `dr_contradictions` | `{contradictions: [...]}` עד 5, בלי להמציא |
| `dr_entities` | `{entity_type, columns, rows: [{cells, source_url, source_name}]}` |
| `writer:ch{N}` | פרק עברי מלא ב-Markdown + סמנים, ציטוטים רק מהרשימה שסופקה |
| `grounder` | `[{index, status, reason, rewrite}]` לכל טענה |
| `executive` | טקסט עם `[KPI_DATA]`, `[CONCLUSION]`, `[ROI_CALC]` |
| `hebrew_editor` | הטקסט הערוך בין `===TEXT===` ל-`===END===` |
| `evaluator` | `{"hebrew_quality": 0-10, "coherence": 0-10, "notes"}` |
| `ideation` | JSON עם 7 מפתחות הקטגוריות |
| `toc_gaps` | `{"suggestions": [{kind, title, parent, reason}]}` |

הערות: מזהה הבקשה דטרמיניסטי ב-purpose+prompt — אם הצינור קרס והורץ שוב,
תשובות קיימות יישרתו מה-cache ואל לך לענות עליהן שוב. שתי ריצות במקביל
חייבות `SURVEY_BRIDGE_DIR` נפרד (ברירת המחדל של ה-CLI כבר עושה זאת).

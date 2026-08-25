# LitReview — מערכת סקרי ספרות אקדמיים

מערכת שמייצרת סקרי ספרות ברמה אקדמית בעברית: מקורות אמיתיים מ-14+ מאגרים אקדמיים,
אימות כל DOI ובדיקת retraction, עיגון כל טענה למקור שצוטט, שקיפות מלאה
(PRISMA, יומן ביקורת, Scorecard) — ופלטים ב-HTML (RTL), Word, מצגת ופודקאסט.

**העיקרון המרכזי: המודל כותב טקסט; העובדות מגיעות מהמאגרים; המערכת אוכפת את
החיבור ביניהם.**

הפרויקט משכפל (clean-room, מתוך אפיון בלבד) כלי קיים ומרחיב אותו:
ראו `docs/spec.pdf` (האפיון המקורי) ו-`docs/mockup_1.html` (מוקאפ ממשק המשתמש).

## רכיבים

| שכבה | מה יש בה |
|---|---|
| `litreview/core` | מודל הנתונים (SurveyState), שער ה-LLM (native/mock/api), אורקסטרציה, checkpoint, dedup, ציטוטים, סמנים |
| `litreview/agents` | ~17 סוכני הצינור: חיפוש, אימות, deep-research, כתיבה, עיגון, ביקורת, עריכה, גרפים, הערכה, פלטים |
| `litreview/apis` | מחברים למאגרים האקדמיים + שכבת HTTP עם cache ו-retry |
| `litreview/server` | FastAPI: סקרים, גרסאות, שערי אישור, SSE | 
| `frontend/` | ממשק המשתמש (7 מסכים, RTL) |

## התקנה והרצה (מצב פיתוח)

```bash
pip install -e ".[dev]"
pytest                                   # כל הבדיקות רצות offline במצב mock

# הרצת סקר דמו בלי רשת ובלי מודל:
SURVEY_LLM_BACKEND=mock python run_pipeline.py --config examples/demo_small.json

# אפליקציית ה-Web (דשבורד, שערי אישור, עריכת טיוטה, ייצוא):
SURVEY_LLM_BACKEND=mock python -m litreview.server --port 8000
# ואז לגלוש אל http://127.0.0.1:8000
```

מצבי LLM (`SURVEY_LLM_BACKEND`): `native` (גשר קבצים מול סשן Claude Code — בלי מפתח,
ראו `SKILL.md`), `api` (מפתח Anthropic; deep-research דרך כלי web צד-שרת),
`mock` (דטרמיניסטי, לבדיקות), `auto`.

כל דגלי התצורה מרוכזים ב-`litreview/config.py` ומתועדים באפיון §14.

## פרסום כאתר (פרודקשן)

```bash
# עם קוד גישה — כל האפליקציה דורשת התחברות:
SURVEY_ACCESS_CODE=long-secret SURVEY_LLM_BACKEND=api ANTHROPIC_API_KEY=... \
  python -m litreview.server --host 0.0.0.0 --port 8000

# או בקונטיינר (Dockerfile מצורף; volume על /app/var שומר את הסקרים):
docker compose up -d
```

המדריך המלא — Render (חינם, "לחבר GitHub"), שרת פרטי עם דומיין ו-HTTPS
אוטומטי, גיבויים והחלפת קוד — ב-**`docs/DEPLOY.md`**.

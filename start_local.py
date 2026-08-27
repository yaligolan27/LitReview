#!/usr/bin/env python3
"""הלינק שלך: http://localhost:8000 — משגר בפקודה אחת.

    python start_local.py

מרים את הכול לבד, בסדר הזה:
1. שרת LitReview במצב native עם דגלי האיכות המקסימלית (אלא אם הוגדרו אחרת
   בסביבה — כל SURVEY_* שכבר מוגדר מכובד).
2. פותח את הדפדפן על http://localhost:8000.
3. מפעיל את "המנוע" — סשן Claude Code (על מנוי ה-Claude שלך, בלי מפתח API)
   שמשרת את גשר הקבצים לפי SKILL.md. ההרשאות שהוא צריך כבר מאושרות מראש
   ב-.claude/settings.json, כך שהוא רץ בלי שאלות.

Ctrl+C סוגר את המנוע ואת השרת יחד. הסקרים נשמרים ב-var/ וממשיכים מאותה
נקודה בהרצה הבאה.

אפשרויות:
    --mock        דמו בלי מנוע ובלי רשת (הצינור רץ על תשובות דטרמיניסטיות)
    --no-engine   רק השרת (תפעילי מנוע בעצמך בטרמינל אחר)
    --no-browser  בלי פתיחת דפדפן אוטומטית
    --port 8000   פורט אחר
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import time
import urllib.request
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parent

ENGINE_PROMPT = (
    "קרא את SKILL.md בשורש הריפו ושרת את גשר הקבצים של LitReview ללא הפסקה: "
    "סרוק כל 2-3 שניות את כל תיקיות ה-bridge תחת var/surveys/*/v*/bridge "
    "לבקשות req_*.json חדשות, ענה על כל בקשה לפי הכללים (כתיבה לנתיב "
    "response_file המלא + קובץ .done), והמשך לשרת עד שאעצור אותך. "
    "בקשות deep-research מחייבות חיפוש web אמיתי; בקשות interview — "
    "פורמט הסקר המובנה שב-system."
)

QUALITY_DEFAULTS = {
    "SURVEY_BRIDGE_TIMEOUT": "3600",
    "SURVEY_RELIABILITY_SIGNALS": "1",
    "SURVEY_DR_DEPTH": "deep",
    "SURVEY_SOURCE_SCOUT": "1",
}


def _health_ok(port: int) -> bool:
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/health",
                                    timeout=2) as resp:
            return resp.status == 200
    except Exception:  # noqa: BLE001
        return False


def main() -> int:
    parser = argparse.ArgumentParser(description="LitReview local launcher")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--mock", action="store_true",
                        help="דמו בלי מנוע ובלי רשת")
    parser.add_argument("--no-engine", action="store_true")
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args()

    env = os.environ.copy()
    env.setdefault("SURVEY_LLM_BACKEND", "mock" if args.mock else "native")
    if not args.mock:
        for key, value in QUALITY_DEFAULTS.items():
            env.setdefault(key, value)

    url = f"http://localhost:{args.port}"
    print(f"▶ מרים את שרת LitReview ({env['SURVEY_LLM_BACKEND']})…")
    server = subprocess.Popen(
        [sys.executable, "-m", "litreview.server",
         "--port", str(args.port), "--data-dir", "var"],
        cwd=ROOT, env=env)

    try:
        for _ in range(60):
            if server.poll() is not None:
                print("✗ השרת נפל בעלייה. אם זו התקנה ראשונה הריצי: "
                      "pip install -e \".[server]\"")
                return 1
            if _health_ok(args.port):
                break
            time.sleep(0.5)
        else:
            print("✗ השרת לא עלה בזמן — בדקי את הפלט למעלה.")
            return 1

        print(f"\n✅ הכלי באוויר:  {url}\n")
        if not args.no_browser:
            webbrowser.open(url)

        if args.mock or args.no_engine:
            print("(רץ בלי מנוע — Ctrl+C לעצירה)")
            server.wait()
            return 0

        claude_cli = shutil.which("claude")
        if not claude_cli:
            print("⚠ ה-CLI של Claude Code לא נמצא. התקיני מ: "
                  "https://claude.com/claude-code — ובינתיים השרת רץ; "
                  "אפשר לפתוח מנוע ידנית בטרמינל אחר. Ctrl+C לעצירה.")
            server.wait()
            return 0

        print("▶ מפעיל את המנוע (סשן Claude Code על המנוי שלך).")
        print("  השאירי את החלון הזה פתוח כל עוד סקר רץ. Ctrl+C עוצר הכול.\n")
        subprocess.call([claude_cli, ENGINE_PROMPT], cwd=ROOT)
        return 0
    except KeyboardInterrupt:
        return 0
    finally:
        if server.poll() is None:
            server.terminate()
            try:
                server.wait(timeout=5)
            except subprocess.TimeoutExpired:
                server.kill()
        print("\n⏹ LitReview נעצר. הסקרים שמורים ב-var/ — נתראה בהרצה הבאה.")


if __name__ == "__main__":
    sys.exit(main())

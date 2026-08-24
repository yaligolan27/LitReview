"""Section builders for the survey document (spec §9.16, M1 subset)."""

from __future__ import annotations

import html
from datetime import date

from ...core.state import Paper, SurveyState
from .convert import convert_markers

_LANG_NAMES = {"en": "אנגלית", "he": "עברית", "de": "גרמנית", "fr": "צרפתית",
               "es": "ספרדית", "zh": "סינית", "ja": "יפנית", "ru": "רוסית",
               "pt": "פורטוגזית", "ar": "ערבית"}


def esc(text: str) -> str:
    return html.escape(str(text or ""), quote=False)


def count_cited_languages(cited: list[Paper]) -> list[str]:
    """Honest language counting (spec §9.16): distinct ``Paper.language`` among
    *cited* papers only; a paper without a language code counts as English."""
    langs = {(p.language or "en").split("-")[0].lower() for p in cited}
    return sorted(langs)


def build_cover(state: SurveyState) -> str:
    cited = state.cited_papers
    langs = count_cited_languages(cited) if cited else []
    total_claims = state.grounding_report.get("total_claims", 0)
    supported_pct = state.grounding_report.get("supported_pct", 0)
    years = state.timeline_years
    year_range = f"{min(years)}–{max(years)}" if years else "—"
    metrics = [
        (len(cited), "מקורות מצוטטים"),
        (len(state.sections), "פרקים"),
        (total_claims, "טענות שנבדקו"),
        (f"{supported_pct}%", "טענות נתמכות"),
        (", ".join(_LANG_NAMES.get(l, l) for l in langs) or "—", "שפות המקורות"),
        (year_range, "טווח שנים"),
    ]
    metric_html = "\n".join(
        f'<div class="metric"><div class="n">{esc(n)}</div><div class="l">{esc(l)}</div></div>'
        for n, l in metrics
    )
    author = f" · {esc(state.brief.author)}" if state.brief.author else ""
    return f"""<div class="cover">
<div class="kicker">סקר ספרות · {date.today().year}</div>
<h1>{esc(state.brief.topic)}</h1>
<div class="sub">סקירה שיטתית{author} · {date.today().strftime('%d.%m.%Y')}</div>
<div class="metrics">{metric_html}</div>
</div>"""


def build_reliability_notice(state: SurveyState) -> str:
    parts = ["מסמך זה נכתב בסיוע AI. העובדות נאספו ממאגרים אקדמיים ואומתו ככל הניתן."]
    unverified = [i + 1 for i, p in enumerate(state.cited_papers)
                  if p.doi and p.doi_verified is False]
    if unverified:
        refs = ", ".join(f"[{n}]" for n in unverified)
        parts.append(f"המאמרים {refs} לא אומתו מול Crossref.")
    not_checked = [i + 1 for i, p in enumerate(state.cited_papers)
                   if p.doi and p.doi_verified is None]
    if not_checked:
        refs = ", ".join(f"[{n}]" for n in not_checked)
        parts.append(f"בדיקת ה-DOI של {refs} לא הושלמה עקב תקלת רשת.")
    if state.retracted_papers:
        parts.append(f"זוהו {len(state.retracted_papers)} מאמרים שנמשכו מהספרות והם מסומנים.")
    return f'<div class="notice">⚠️ <b>הערת אמינות:</b> {" ".join(parts)}</div>'


def build_toc(state: SurveyState) -> str:
    items = []
    for entry in state.toc:
        secs = " · ".join(esc(s) for s in entry.sections)
        items.append(f"<li>{esc(entry.chapter)}"
                     + (f'<div class="secs">{secs}</div>' if secs else "")
                     + "</li>")
    return f"""<div class="toc-box">
<h3>תוכן עניינים</h3>
<ol>{''.join(items)}</ol>
</div>"""


def build_sections(state: SurveyState) -> str:
    out = []
    for i, sec in enumerate(state.sections, start=1):
        conf = sec.effective_confidence() or "EMERGING"
        out.append(f"""<h2 class="chapter"><span>{i}. {esc(sec.title)}</span>
<span class="badge {conf}">{conf}</span></h2>""")
        out.append(convert_markers(sec.content))
        for svg in sec.diagrams:
            out.append(f'<figure>{svg}</figure>')
    return "\n".join(out)


def build_transparency(state: SurveyState) -> str:
    g = state.grounding_report
    d = state.dedup_stats
    p = state.prisma
    rows = [
        ("מקורות שזוהו בחיפוש", p.get("identified", "—")),
        ("כפילויות שהוסרו", p.get("duplicates_removed", "—")),
        ("מקורות לאחר ניפוי", p.get("after_dedup", "—")),
        ("שאילתות שהורצו", p.get("queries", "—")),
        ("טענות שנבדקו", g.get("total_claims", "—")),
        ("נתמכות / לא-ודאיות / לא-נתמכות",
         f"{g.get('supported', 0)} / {g.get('uncertain', 0)} / {g.get('unsupported', 0)}"),
        ("מנוע ניפוי כפילויות", f"{d.get('engine', '—')} (סף {d.get('threshold', '—')})"),
    ]
    table = "".join(f"<tr><td>{esc(k)}</td><td><b>{esc(v)}</b></td></tr>" for k, v in rows)

    prisma_steps = []
    flow = [
        (f"זוהו: {p.get('identified', 0)} מקורות", True),
        (f"ניפוי כפילויות: הוסרו {p.get('duplicates_removed', 0)}", True),
        (f"נסקרו: {p.get('after_dedup', 0)} מקורות", True),
        (f"הוצאו: {p.get('excluded_retracted', 0)} שנמשכו · {p.get('doi_unverified', 0)} ללא אימות DOI", True),
        (f"נכללו בסקר: {len(state.cited_papers)} מקורות מצוטטים", True),
    ]
    for i, (label, _) in enumerate(flow):
        prisma_steps.append(f'<div class="step">{esc(label)}</div>')
        if i < len(flow) - 1:
            prisma_steps.append('<div class="arrow">↓</div>')

    audit_lines = "".join(
        f"<div>[{esc(e.get('at', ''))}] {esc(e.get('stage', ''))}: {esc(e.get('message', ''))}</div>"
        for e in state.audit_log
    )
    return f"""<h2 class="chapter"><span>שקיפות ובקרת איכות</span></h2>
<div class="transparency">
<table>{table}</table>
<h3>תרשים PRISMA</h3>
<div class="prisma-flow">{''.join(prisma_steps)}</div>
<details><summary>יומן ביקורת מלא ({len(state.audit_log)} רשומות)</summary>
<div class="audit">{audit_lines}</div></details>
</div>"""


def _verification_label(paper: Paper) -> str:
    if paper.is_retracted:
        return '<span class="vlabel bad">RETRACTED</span>'
    if paper.doi and paper.doi_verified is True:
        return '<span class="vlabel ok">✓ אומת (DOI)</span>'
    if paper.doi and paper.doi_verified is None:
        return '<span class="vlabel na">DOI לא נבדק</span>'
    if paper.doi and paper.doi_verified is False:
        return '<span class="vlabel warn">DOI לא אומת</span>'
    if paper.url:
        return '<span class="vlabel na">קישור ציבורי</span>'
    return '<span class="vlabel warn">אין קישור</span>'


def build_bibliography(state: SurveyState) -> str:
    items = []
    for paper in state.cited_papers:
        apa = esc(paper.apa)
        if paper.doi:
            link = f"https://doi.org/{paper.doi}" if not paper.doi.startswith("http") else paper.doi
            apa = apa.replace(esc(link), f'<a href="{link}">{esc(link)}</a>') \
                if esc(link) in apa else apa + f' <a href="{link}">{esc(link)}</a>'
        elif paper.url:
            apa += f' <a href="{esc(paper.url)}">{esc(paper.url)}</a>'
        items.append(f"<li>{apa} {_verification_label(paper)}</li>")
    return f"""<h2 class="chapter"><span>ביבליוגרפיה</span></h2>
<p class="secs">רק מקורות שצוטטו בפועל בגוף הסקירה נכללים ברשימה ({len(items)} מקורות).</p>
<ol class="bib">{''.join(items)}</ol>"""

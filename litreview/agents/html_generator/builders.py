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


def build_executive(state: SurveyState) -> str:
    if not state.executive_summary:
        return ""
    import re as _re
    text = state.executive_summary
    opening = text.split("[", 1)[0].strip()
    kpi_html = "".join(
        f'<div class="kpi-box"><div class="num">{esc(b["num"])}</div>'
        f'<div class="label">{esc(b["label"])}</div>'
        f'<div class="desc">{esc(b["desc"])} '
        f'{convert_markers(b["cite"], drop_kpi=False) if b["cite"] else ""}</div></div>'
        for b in state.kpi_data)
    conclusions = _re.findall(r"\[CONCLUSION\](.*?)\[/CONCLUSION\]", text, _re.DOTALL)
    conclusions_html = "".join(
        f"<li>{convert_markers(c.strip(), drop_kpi=False).replace('<p>', '').replace('</p>', '')}</li>"
        for c in conclusions)
    roi = _re.search(r"\[ROI_CALC\](.*?)\[/ROI_CALC\]", text, _re.DOTALL)
    roi_html = f'<div class="roi">💰 {esc(roi.group(1).strip())}</div>' if roi else ""
    return f"""<div class="exec">
<h3>תקציר מנהלים</h3>
<p>{esc(opening)}</p>
<div class="kpi-grid">{kpi_html}</div>
<ul class="conclusions">{conclusions_html}</ul>
{roi_html}
</div>"""


def build_scorecard(state: SurveyState) -> str:
    card = state.scorecard
    if not card:
        return ""
    rows = []
    metrics = card.get("metrics", {})
    titles = card.get("titles", {})
    for key, value in metrics.items():
        pct = round(value * 10)
        rows.append(
            f'<div class="metric-row"><span>{esc(titles.get(key, key))}</span>'
            f'<div class="bar"><span style="width:{pct}%"></span></div>'
            f'<b>{value}</b></div>')
    warn = ""
    if card.get("below_threshold"):
        warn = (f'<div class="score-warn">⚠️ ציון הסקר ({card["score"]}) נמוך מסף '
                f'האיכות ({card["threshold"]}). המסמך מופק, אך מומלץ להרחיב את '
                f'בסיס המקורות ולחזק את עיגון הטענות.</div>')
    return f"""<div class="scorecard">
<div class="score-line"><span class="score-num">{card.get("score", "—")}</span>
<span>/ 100 · ציון איכות שהמערכת נתנה לסקר שהיא עצמה כתבה</span></div>
{''.join(rows)}
{warn}
</div>"""


def build_charts(state: SurveyState) -> str:
    figures = [c for c in state.charts if c.get("title") != "PRISMA" and c.get("svg")]
    if not figures:
        return ""
    figs = "".join(f'<figure>{c["svg"]}</figure>' for c in figures)
    return f"""<h2 class="chapter"><span>נתונים ומגמות</span></h2>
<p class="secs">כל הגרפים חושבו בקוד מנתוני המקורות בפועל — אף מספר אינו מגיע מהמודל.</p>
<div class="charts">{figs}</div>"""


def build_ideation(state: SurveyState) -> str:
    from ..ideation_engine import CATEGORIES
    if not state.ideation or not any(state.ideation.values()):
        return ""
    blocks = []
    for key, title in CATEGORIES.items():
        items = state.ideation.get(key) or []
        if not items:
            continue
        lis = "".join(
            f'<li>{esc(i)} <span class="gen-badge">Generated Idea</span></li>'
            for i in items)
        blocks.append(f"<h4>{esc(title)}</h4><ul>{lis}</ul>")
    return f"""<h2 class="chapter"><span>רעיונות שנוצרו על ידי המערכת</span></h2>
<div class="ideation">
<p><b>⚠️ פרק זה אינו חלק מסקירת הספרות.</b> כל פריט כאן הוא רעיון שנוצר על ידי
המערכת — לא טענה מחקרית ולא מבוסס מקור אקדמי.</p>
{''.join(blocks)}
</div>"""


def build_web_sources(state: SurveyState) -> str:
    findings = (state.deep_research or {}).get("findings") or []
    cited = [f for f in findings if f.get("w_id")]
    if not cited:
        return ""
    stats = (state.deep_research or {}).get("stats") or {}
    stats_line = (f"סבבים: {stats.get('rounds', '—')} · שאילתות: "
                  f"{stats.get('queries', '—')} · דפים שנקראו: {stats.get('pages', '—')} · "
                  f"ממצאים: {len(findings)} · אוששו: {stats.get('corroborated', 0)}")
    items = []
    for f in cited:
        verdict = ""
        if f.get("verdict") == "corroborated":
            verdict = ' <span class="vlabel ok">✓✓ מאושש</span>'
        elif f.get("verdict") == "disputed":
            verdict = ' <span class="vlabel warn">⚠ שנוי במחלוקת</span>'
        quote = f'<div class="quote">"{esc(f.get("quote", ""))}"</div>' if f.get("quote") else ""
        items.append(
            f'<li id="wsrc-{esc(str(f["w_id"])[1:])}"><span class="wnum">[{esc(f["w_id"])}]</span> '
            f'{esc(f.get("heading", ""))} — <a href="{esc(f.get("url", ""))}">'
            f'{esc(f.get("source_name") or f.get("url", ""))}</a> '
            f'({esc(f.get("date", ""))}) <span class="vlabel na">{esc(f.get("tier", ""))}</span>'
            f'{verdict}{quote}</li>')
    return f"""<h2 class="chapter"><span>מחקר עומק — מקורות פתוחים</span></h2>
<p class="secs">שכבה נפרדת מהביבליוגרפיה האקדמית. {esc(stats_line)}</p>
<ol class="wsrc">{''.join(items)}</ol>"""


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

    if p.get("svg"):
        prisma_steps = [p["svg"]]
    else:
        prisma_steps = []
        flow = [
            f"זוהו: {p.get('identified', 0)} מקורות",
            f"ניפוי כפילויות: הוסרו {p.get('duplicates_removed', 0)}",
            f"נסקרו: {p.get('after_dedup', 0)} מקורות",
            f"הוצאו: {p.get('excluded_retracted', 0)} שנמשכו · "
            f"{p.get('doi_unverified', 0)} ללא אימות DOI",
            f"נכללו בסקר: {len(state.cited_papers)} מקורות מצוטטים",
        ]
        for i, label in enumerate(flow):
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

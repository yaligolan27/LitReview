"""Stage 13 — Visualizer (spec §9.13).

Five SVG charts, all computed in code from real state data — no number ever
comes from the model (reliability mechanism #18). Hand-built SVG with grid
lines, value labels, a legend and a source note under every chart.
"""

from __future__ import annotations

import html
from collections import Counter

from ..core.context import RunContext
from ..core.state import SurveyState

W, H = 640, 300
PAD_L, PAD_R, PAD_T, PAD_B = 56, 20, 28, 56

CONFIDENCE_COLORS = {"HIGH": "#2e7d32", "MODERATE": "#1565c0",
                     "LIMITED": "#e65100", "EMERGING": "#c62828"}
PALETTE = ["#1a3a8f", "#4285f4", "#7b1fa2", "#0d9488", "#e65100",
           "#c62828", "#5e35b1", "#2e7d32"]


def _esc(text: str) -> str:
    return html.escape(str(text), quote=True)


def bar_chart(title: str, data: list[tuple[str, int]], source_note: str,
              rotate_labels: bool = False) -> str:
    if not data:
        return ""
    max_val = max(v for _, v in data) or 1
    plot_w = W - PAD_L - PAD_R
    plot_h = H - PAD_T - PAD_B
    bar_w = plot_w / len(data)
    parts = [f'<svg viewBox="0 0 {W} {H}" xmlns="http://www.w3.org/2000/svg" '
             f'role="img" aria-label="{_esc(title)}" style="max-width:100%;height:auto">']
    parts.append(f'<text x="{W / 2}" y="18" text-anchor="middle" font-size="14" '
                 f'font-weight="700" fill="#0a1535">{_esc(title)}</text>')
    for i in range(5):
        y = PAD_T + plot_h * i / 4
        value = round(max_val * (4 - i) / 4)
        parts.append(f'<line x1="{PAD_L}" y1="{y:.1f}" x2="{W - PAD_R}" y2="{y:.1f}" '
                     f'stroke="#e0e4f0" stroke-width="1"/>')
        parts.append(f'<text x="{PAD_L - 8}" y="{y + 4:.1f}" text-anchor="end" '
                     f'font-size="10" fill="#5a627a">{value}</text>')
    for i, (label, value) in enumerate(data):
        x = PAD_L + i * bar_w + bar_w * 0.15
        bh = plot_h * value / max_val
        y = PAD_T + plot_h - bh
        parts.append(f'<rect x="{x:.1f}" y="{y:.1f}" width="{bar_w * 0.7:.1f}" '
                     f'height="{bh:.1f}" rx="3" fill="#1a3a8f"/>')
        parts.append(f'<text x="{x + bar_w * 0.35:.1f}" y="{y - 5:.1f}" text-anchor="middle" '
                     f'font-size="10" font-weight="700" fill="#1a3a8f">{value}</text>')
        label_y = H - PAD_B + 16
        transform = ""
        if rotate_labels:
            transform = (f' transform="rotate(-35 {x + bar_w * 0.35:.1f} {label_y})"')
        parts.append(f'<text x="{x + bar_w * 0.35:.1f}" y="{label_y}" text-anchor="middle" '
                     f'font-size="9.5" fill="#1a1a2e"{transform}>{_esc(str(label)[:18])}</text>')
    parts.append(f'<text x="{W / 2}" y="{H - 8}" text-anchor="middle" font-size="9.5" '
                 f'fill="#5a627a">{_esc(source_note)}</text>')
    parts.append("</svg>")
    return "".join(parts)


def pie_chart(title: str, data: list[tuple[str, int]], source_note: str,
              colors: dict[str, str] | None = None) -> str:
    data = [(k, v) for k, v in data if v > 0]
    if not data:
        return ""
    total = sum(v for _, v in data)
    cx, cy, r = 190, (H + 10) / 2, 92
    parts = [f'<svg viewBox="0 0 {W} {H}" xmlns="http://www.w3.org/2000/svg" '
             f'role="img" aria-label="{_esc(title)}" style="max-width:100%;height:auto">']
    parts.append(f'<text x="{W / 2}" y="18" text-anchor="middle" font-size="14" '
                 f'font-weight="700" fill="#0a1535">{_esc(title)}</text>')
    import math
    angle = -math.pi / 2
    for i, (label, value) in enumerate(data):
        frac = value / total
        end = angle + 2 * math.pi * frac
        color = (colors or {}).get(label, PALETTE[i % len(PALETTE)])
        if len(data) == 1:
            parts.append(f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="{color}"/>')
        else:
            x1, y1 = cx + r * math.cos(angle), cy + r * math.sin(angle)
            x2, y2 = cx + r * math.cos(end), cy + r * math.sin(end)
            large = 1 if frac > 0.5 else 0
            parts.append(f'<path d="M{cx},{cy} L{x1:.1f},{y1:.1f} '
                         f'A{r},{r} 0 {large} 1 {x2:.1f},{y2:.1f} Z" fill="{color}"/>')
        mid = (angle + end) / 2
        if frac >= 0.06:
            lx, ly = cx + r * 0.62 * math.cos(mid), cy + r * 0.62 * math.sin(mid)
            parts.append(f'<text x="{lx:.1f}" y="{ly:.1f}" text-anchor="middle" '
                         f'font-size="11" font-weight="700" fill="#fff">'
                         f'{round(100 * frac)}%</text>')
        angle = end
    legend_x, legend_y = 360, 60
    for i, (label, value) in enumerate(data):
        color = (colors or {}).get(label, PALETTE[i % len(PALETTE)])
        y = legend_y + i * 22
        parts.append(f'<rect x="{legend_x}" y="{y - 10}" width="12" height="12" rx="2" '
                     f'fill="{color}"/>')
        parts.append(f'<text x="{legend_x + 18}" y="{y}" font-size="11" fill="#1a1a2e">'
                     f'{_esc(str(label)[:26])} ({value})</text>')
    parts.append(f'<text x="{W / 2}" y="{H - 8}" text-anchor="middle" font-size="9.5" '
                 f'fill="#5a627a">{_esc(source_note)}</text>')
    parts.append("</svg>")
    return "".join(parts)


def prisma_svg(state: SurveyState) -> str:
    p = state.prisma
    steps = [
        f"זוהו בחיפוש: {p.get('identified', 0)} מקורות",
        f"ניפוי כפילויות: הוסרו {p.get('duplicates_removed', 0)} → נותרו {p.get('after_dedup', 0)}",
        f"נסקרו: {p.get('after_dedup', 0)} מקורות",
        f"הוצאו: {p.get('excluded_retracted', 0)} שנמשכו (retracted) · "
        f"{p.get('doi_unverified', 0)} לא אומת DOI"
        + (f" · {p.get('excluded_by_user', 0)} הוחרגו ידנית" if p.get("excluded_by_user") else ""),
        f"נכללו בסקר: {len(state.cited_papers)} מקורות מצוטטים",
    ]
    box_w, box_h, gap = 430, 42, 24
    height = len(steps) * (box_h + gap) + 30
    parts = [f'<svg viewBox="0 0 640 {height}" xmlns="http://www.w3.org/2000/svg" '
             f'role="img" aria-label="PRISMA" style="max-width:100%;height:auto">']
    for i, label in enumerate(steps):
        x = (640 - box_w) / 2
        y = 16 + i * (box_h + gap)
        parts.append(f'<rect x="{x}" y="{y}" width="{box_w}" height="{box_h}" rx="10" '
                     f'fill="#f8f9ff" stroke="#1a3a8f" stroke-width="1.6"/>')
        parts.append(f'<text x="320" y="{y + box_h / 2 + 4}" text-anchor="middle" '
                     f'font-size="12.5" font-weight="600" fill="#0a1535" direction="rtl">'
                     f'{_esc(label)}</text>')
        if i < len(steps) - 1:
            ay = y + box_h
            parts.append(f'<line x1="320" y1="{ay}" x2="320" y2="{ay + gap}" '
                         f'stroke="#1a3a8f" stroke-width="1.6" marker-end="url(#arr)"/>')
    parts.insert(1, '<defs><marker id="arr" markerWidth="8" markerHeight="8" refX="4" '
                    'refY="4" orient="auto"><path d="M0,0 L8,4 L0,8 Z" fill="#1a3a8f"/>'
                    '</marker></defs>')
    parts.append("</svg>")
    return "".join(parts)


_SOURCE_TYPE_HE = {"journal-article": "מאמרי כתב-עת", "review": "מאמרי סקירה",
                   "proceedings-article": "מאמרי כנסים", "preprint": "קדם-פרסומים",
                   "report": "דוחות", "book-chapter": "פרקי ספרים",
                   "dataset": "מאגרי נתונים"}


def run_visualizer(ctx: RunContext, state: SurveyState) -> SurveyState:
    pool = state.cited_papers or state.papers
    charts: list[dict] = []

    years = [p.year for p in pool if p.year]
    if years:
        counter = Counter(years)
        lo, hi = min(years), max(years)
        data = [(str(y), counter.get(y, 0)) for y in range(lo, hi + 1)]
        charts.append({"title": "פרסומים לפי שנה",
                       "svg": bar_chart("כמות פרסומים לפי שנה", data,
                                        f"מקור: שנות הפרסום של {len(pool)} המקורות שצוטטו"),
                       })

    type_counts = Counter(_SOURCE_TYPE_HE.get(p.source_type, p.source_type or "אחר")
                          for p in pool)
    charts.append({"title": "התפלגות סוגי מקורות",
                   "svg": pie_chart("התפלגות סוגי מקורות",
                                    sorted(type_counts.items(), key=lambda t: -t[1]),
                                    "מקור: מטא-דאטה של המקורות המצוטטים")})

    conf_counts = Counter(p.confidence or "EMERGING" for p in pool)
    ordered = [(level, conf_counts.get(level, 0))
               for level in ("HIGH", "MODERATE", "LIMITED", "EMERGING")]
    charts.append({"title": "רמות אמינות המקורות",
                   "svg": pie_chart("רמות אמינות המקורות", ordered,
                                    "מקור: דירוג ה-Reliability Auditor",
                                    colors=CONFIDENCE_COLORS)})

    per_chapter = [(s.title[:16], len(s.papers)) for s in state.sections]
    if per_chapter:
        charts.append({"title": "מקורות לפי פרק",
                       "svg": bar_chart("מקורות שהוקצו לכל פרק", per_chapter,
                                        "מקור: שיבוץ המקורות של ה-Writer",
                                        rotate_labels=True)})

    prisma = prisma_svg(state)
    charts.append({"title": "PRISMA", "svg": prisma})
    state.prisma["svg"] = prisma

    state.charts = [c for c in charts if c.get("svg")]
    state.log("visualize", "charts built", charts=len(state.charts))
    return state

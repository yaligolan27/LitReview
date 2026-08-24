"""Marker → HTML conversion, full order (spec §9.16).

Order matters, and the formula-placeholder trick is load-bearing: after
``_mathify`` the content contains ``\\[...\\]`` — if the formula regex ran
again over converted text, nested formula boxes would appear. So formulas
are pulled into ``\\x00FML{i}\\x00`` placeholders (step 4) and restored only
after paragraph splitting (step 10).
"""

from __future__ import annotations

import html
import re

_TRL = re.compile(r"\[TRL:(\d)\]")
_KPI_BLOCK = re.compile(r"\[KPI\](.*?)\[/KPI\]", re.DOTALL)
_CALLOUT = re.compile(r"\[CALLOUT(?::([a-zA-Z]+))?\](.*?)\[/CALLOUT\]", re.DOTALL)
_FORMULA = re.compile(r"\[FORMULA\](.*?)\[/FORMULA\]|\$\$(.*?)\$\$|\\\[(.*?)\\\]",
                      re.DOTALL)
_CASE = re.compile(r"\[CASE\](.*?)\[/CASE\]", re.DOTALL)
_TABLE = re.compile(r"\[TABLE\](.*?)\[/TABLE\]", re.DOTALL)
_WCITE = re.compile(r"\[(W\d+(?:\s*,\s*W\d+)*)\]")
_CITE = re.compile(r"\[(\d+(?:\s*[-–,]\s*\d+)*)\]")
_BOLD = re.compile(r"\*\*(.+?)\*\*")
_H4 = re.compile(r"^####\s+(.*)$", re.MULTILINE)
_H3 = re.compile(r"^###\s+(.*)$", re.MULTILINE)
_H2 = re.compile(r"^##\s+(.*)$", re.MULTILINE)

_BLOCK_OPENERS = ("<div", "<h1", "<h2", "<h3", "<h4", "<table", "<ul", "<ol",
                  "<pre", "<figure", "<details", "<p")


def _callout(match: re.Match) -> str:
    color = (match.group(1) or "blue").lower()
    body = match.group(2).strip()
    first_line = body.split("\n", 1)[0]
    if ":" in first_line and len(first_line.split(":", 1)[0]) <= 60:
        head, _, rest = body.partition(":")
        body = f"<strong>{head.strip()}:</strong> {rest.strip()}"
    return f'<div class="callout {color}">{body}</div>'


def _mathify(latex: str) -> str:
    """Normalize any formula content to display-math \\[...\\] for MathJax."""
    inner = latex.strip()
    inner = re.sub(r"^\$\$|\$\$$", "", inner).strip()
    inner = re.sub(r"^\\\[|\\\]$", "", inner).strip()
    return f'<div class="formula">\\[{inner}\\]</div>'


def _case_card(match: re.Match) -> str:
    parts = [p.strip() for p in match.group(1).split("|")]
    name = parts[0] if parts else ""
    tags = parts[1] if len(parts) > 1 else ""
    content = parts[2] if len(parts) > 2 else ""
    tags_html = "".join(f'<span class="tag">{t.strip()}</span>'
                        for t in tags.split(",") if t.strip())
    return (f'<div class="case-card"><div class="case-head">📋 מקרה בוחן: {name} '
            f'{tags_html}</div><div>{content}</div></div>')


def _md_table(match: re.Match) -> str:
    rows = [r.strip() for r in match.group(1).strip().splitlines() if r.strip()]
    rows = [r for r in rows if not re.fullmatch(r"\|?[\s\-:|]+\|?", r)]
    if not rows:
        return ""
    html_rows = []
    for i, row in enumerate(rows):
        cells = [c.strip() for c in row.strip("|").split("|")]
        tag = "th" if i == 0 else "td"
        rendered = []
        for cell in cells:
            css = ""
            if "[BEST]" in cell:
                css = ' class="best"'
                cell = cell.replace("[BEST]", "").strip()
            elif "[BAD]" in cell:
                css = ' class="bad"'
                cell = cell.replace("[BAD]", "").strip()
            rendered.append(f"<{tag}{css}>{cell}</{tag}>")
        html_rows.append("<tr>" + "".join(rendered) + "</tr>")
    return f'<table class="tbl">{"".join(html_rows)}</table>'


def convert_markers(text: str, drop_kpi: bool = True) -> str:
    text = html.escape(text, quote=False)

    # 1. TRL badges
    text = _TRL.sub(lambda m: f'<span class="trl">TRL {m.group(1)}</span>', text)
    # 2. Chapter [KPI] blocks are dropped (KPIs live in the executive summary)
    if drop_kpi:
        text = _KPI_BLOCK.sub("", text)
    # 3. Callouts
    text = _CALLOUT.sub(_callout, text)
    # 4. Formulas → placeholders (nesting guard)
    formulas: list[str] = []

    def _stash(match: re.Match) -> str:
        content = next(g for g in match.groups() if g is not None)
        formulas.append(_mathify(content))
        return f"\x00FML{len(formulas) - 1}\x00"

    text = _FORMULA.sub(_stash, text)
    # 5. Case cards
    text = _CASE.sub(_case_card, text)
    # 6. Tables
    text = _TABLE.sub(_md_table, text)
    # 7. Web citations → anchored, visually distinct
    text = _WCITE.sub(
        lambda m: f'<cite class="wcite"><a href="#wsrc-{m.group(1).split(",")[0].strip()[1:]}">'
                  f'[{m.group(1)}]</a></cite>', text)
    # 8. Academic citations
    text = _CITE.sub(lambda m: f"<cite>[{m.group(1)}]</cite>", text)
    # 9. Bold + headings
    text = _BOLD.sub(r"<strong>\1</strong>", text)
    text = _H4.sub(r"<h4>\1</h4>", text)
    text = _H3.sub(r"<h3>\1</h3>", text)
    text = _H2.sub(r"<h3>\1</h3>", text)
    # 10. Paragraphs, then restore formulas (placeholders split cleanly)
    text = _paragraphs(text)
    for i, formula in enumerate(formulas):
        text = text.replace(f"\x00FML{i}\x00", formula)
    return text


def _paragraphs(text: str) -> str:
    out: list[str] = []
    for block in re.split(r"\n\s*\n", text):
        block = block.strip()
        if not block:
            continue
        if block.startswith(_BLOCK_OPENERS) or block.startswith("\x00"):
            out.append(block)
        else:
            block = block.replace("\n", "<br>")
            out.append(f"<p>{block}</p>")
    return "\n".join(out)

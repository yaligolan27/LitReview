"""Marker → HTML conversion (spec §9.16, M1 subset).

Order matters: escape first, then block markers, then cites, then inline
formatting, then paragraph wrapping (which must not wrap existing block
elements). The formula-placeholder trick from the spec arrives with
[FORMULA] support in M3.
"""

from __future__ import annotations

import html
import re

_CALLOUT = re.compile(r"\[CALLOUT(?::([a-zA-Z]+))?\](.*?)\[/CALLOUT\]", re.DOTALL)
_WCITE = re.compile(r"\[(W\d+(?:\s*,\s*W\d+)*)\]")
_CITE = re.compile(r"\[(\d+(?:\s*[-,]\s*\d+)*)\]")
_BOLD = re.compile(r"\*\*(.+?)\*\*")
_H4 = re.compile(r"^####\s+(.*)$", re.MULTILINE)
_H3 = re.compile(r"^###\s+(.*)$", re.MULTILINE)
_H2 = re.compile(r"^##\s+(.*)$", re.MULTILINE)

_BLOCK_OPENERS = ("<div", "<h1", "<h2", "<h3", "<h4", "<table", "<ul", "<ol",
                  "<pre", "<figure", "<details", "<p")


def _callout(match: re.Match) -> str:
    color = (match.group(1) or "blue").lower()
    body = match.group(2).strip()
    if ":" in body.split("\n", 1)[0] and len(body.split(":", 1)[0]) <= 60:
        head, _, rest = body.partition(":")
        body = f"<strong>{head.strip()}:</strong> {rest.strip()}"
    return f'<div class="callout {color}">{body}</div>'


def convert_markers(text: str) -> str:
    text = html.escape(text, quote=False)
    text = _CALLOUT.sub(_callout, text)
    text = _WCITE.sub(lambda m: f'<cite class="wcite">[{m.group(1)}]</cite>', text)
    text = _CITE.sub(lambda m: f"<cite>[{m.group(1)}]</cite>", text)
    text = _BOLD.sub(r"<strong>\1</strong>", text)
    text = _H4.sub(r"<h4>\1</h4>", text)
    text = _H3.sub(r"<h3>\1</h3>", text)
    text = _H2.sub(r"<h3>\1</h3>", text)   # writers sometimes emit ## inside chapters
    return _paragraphs(text)


def _paragraphs(text: str) -> str:
    out: list[str] = []
    for block in re.split(r"\n\s*\n", text):
        block = block.strip()
        if not block:
            continue
        if block.startswith(_BLOCK_OPENERS):
            out.append(block)
        else:
            block = block.replace("\n", "<br>")
            out.append(f"<p>{block}</p>")
    return "\n".join(out)

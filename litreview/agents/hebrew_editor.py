"""Stage 11 — Hebrew Editor (spec §9.11).

Improves the language and is FORBIDDEN from touching facts. Every edit runs
through ``safe_to_apply`` — the strongest guard in the system: rejected if
the edit is empty, changes length beyond ×0.5–×2.2, changes the set of
citations ([n] or [W#]), changes the protected-marker census, changes any
number, or introduces marker lint errors. A rejected edit leaves the
original text fully intact.
"""

from __future__ import annotations

import re
from collections import Counter

from ..core import markers
from ..core.context import RunContext
from ..core.state import SurveyState

_CITE = re.compile(r"\[(?:W?\d+(?:\s*[-,]\s*W?\d+)*)\]")
# Capture an optional attached sign (hyphen-minus or U+2212) ONLY when it does
# not immediately follow a digit/dot — so "2020-2026" stays two unsigned tokens
# while a standalone "-0.8" keeps its sign. Without the sign, flipping -0.8 -> 0.8
# was invisible to the guard (review finding).
_NUMBER = re.compile(r"(?<![\d.])[-−]?\d+(?:\.\d+)?%?")
_CALLOUT_COLOR = re.compile(r"\[CALLOUT:([a-zA-Z]+)\]")
_TEXT_BLOCK = re.compile(r"===TEXT===\n(.*?)\n===END===", re.DOTALL)

LEN_MIN_RATIO = 0.5
LEN_MAX_RATIO = 2.2

_SYSTEM_HE = (
    "אתה עורך לשון עברי לטקסט אקדמי. שפר ניסוח, זרימה ופיסוק בלבד. "
    "אסור בהחלט: לשנות מספרים, ציטוטים [n]/[W#], סמנים בסוגריים מרובעים, "
    "או עובדות. החזר את הטקסט הערוך בין ===TEXT=== ל-===END===."
)
_SYSTEM_GENERIC = (
    "You are a language editor for academic text. Improve wording and flow only. "
    "Never change numbers, citations [n]/[W#], square-bracket markers, or facts. "
    "Return the edited text between ===TEXT=== and ===END===."
)


def _citations_set(text: str) -> frozenset[str]:
    return frozenset(m.group(0) for m in _CITE.finditer(text))


def _number_sequence(text: str) -> list[str]:
    # Ordered list, not a multiset: reordering numbers (e.g. "from 100 to 250"
    # -> "from 250 to 100") is a factual inversion the multiset would miss.
    return _NUMBER.findall(text)


def _callout_colors(text: str) -> list[str]:
    return [c.lower() for c in _CALLOUT_COLOR.findall(text)]


def safe_to_apply(original: str, edited: str) -> tuple[bool, str]:
    if not edited.strip():
        return False, "empty edit"
    ratio = len(edited) / max(1, len(original))
    if not (LEN_MIN_RATIO <= ratio <= LEN_MAX_RATIO):
        return False, f"length ratio {ratio:.2f} outside {LEN_MIN_RATIO}–{LEN_MAX_RATIO}"
    if _citations_set(edited) != _citations_set(original):
        return False, "citation set changed"
    if markers.marker_census(edited) != markers.marker_census(original):
        return False, "marker census changed"
    # marker_census counts CALLOUT color-agnostically; a red->green flip changes
    # meaning (danger vs. success) and must be caught here.
    if _callout_colors(edited) != _callout_colors(original):
        return False, "callout color changed"
    # Ordered comparison catches both a changed value and reordered numbers.
    if _number_sequence(edited) != _number_sequence(original):
        return False, "numbers changed"
    if markers.has_errors(edited) and not markers.has_errors(original):
        return False, "edit introduced marker lint errors"
    return True, ""


def run_hebrew_editor(ctx: RunContext, state: SurveyState) -> SurveyState:
    lang = (state.brief.output_language or "he").lower()
    system = _SYSTEM_HE if lang == "he" else _SYSTEM_GENERIC
    applied = rejected = 0
    for sec in state.sections:
        prompt = (f"ערוך את הטקסט הבא לעברית מקצועית וזורמת.\n"
                  f"===TEXT===\n{sec.content}\n===END===") if lang == "he" else \
                 (f"Edit the following text for professional flow.\n"
                  f"===TEXT===\n{sec.content}\n===END===")
        reply = ctx.llm.complete(prompt, purpose="hebrew_editor", system=system,
                                 max_tokens=4000)
        match = _TEXT_BLOCK.search(reply)
        edited = match.group(1) if match else reply.strip()
        ok, reason = safe_to_apply(sec.content, edited)
        if ok:
            if edited != sec.content:
                applied += 1
            sec.content = edited
        else:
            rejected += 1
            state.log("edit_language",
                      f"unsafe edit rejected for '{sec.title}': {reason}")
    state.log("edit_language", "language editing complete",
              applied=applied, rejected=rejected)
    return state

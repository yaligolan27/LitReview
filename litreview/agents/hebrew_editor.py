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
_NUMBER = re.compile(r"\d+(?:\.\d+)?%?")
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


def _numbers_counter(text: str) -> Counter:
    return Counter(_NUMBER.findall(text))


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
    if _numbers_counter(edited) != _numbers_counter(original):
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

"""The marker language — linter + safe autofix (spec §10, §13).

Markers are how the Writer expresses design ([CALLOUT], [FORMULA], [TABLE],
[CASE], [KPI], [TRL:n], ...) and become styled HTML/Word. The linter blocks
unbalanced block tags (error level); warnings cover invalid CALLOUT colors,
TRL out of 1..9, and malformed CASE/KPI field counts. Autofix applies only
corrections that cannot be wrong (invalid color → blue, TRL clamped);
unbalanced tags are never auto-closed (dangerous).
"""

from __future__ import annotations

import re
from dataclasses import dataclass

BLOCK_TAGS = ("CALLOUT", "FORMULA", "TABLE", "CASE", "KPI", "KPI_DATA",
              "CONCLUSION", "ROI_CALC", "EXAMPLE")
VALID_CALLOUT_COLORS = {"red", "green", "orange", "blue", "purple"}

# The protected marker set the Hebrew editor must not change (spec §9.11).
PROTECTED_TAGS = ("CALLOUT", "/CALLOUT", "FORMULA", "/FORMULA", "TABLE", "/TABLE",
                  "CASE", "/CASE", "KPI", "/KPI", "TRL", "KPI_DATA", "/KPI_DATA",
                  "CONCLUSION", "/CONCLUSION", "ROI_CALC", "/ROI_CALC",
                  "EXAMPLE", "/EXAMPLE")


@dataclass
class LintIssue:
    level: str    # "error" | "warning"
    message: str


def _open_count(text: str, tag: str) -> int:
    if tag == "CALLOUT":
        return len(re.findall(r"\[CALLOUT(?::[a-zA-Z]+)?\]", text))
    return len(re.findall(rf"\[{tag}\]", text))


def _close_count(text: str, tag: str) -> int:
    return len(re.findall(rf"\[/{tag}\]", text))


def lint(text: str) -> list[LintIssue]:
    issues: list[LintIssue] = []
    for tag in BLOCK_TAGS:
        opens, closes = _open_count(text, tag), _close_count(text, tag)
        if opens != closes:
            issues.append(LintIssue(
                "error", f"unbalanced [{tag}] tags: {opens} open / {closes} close"))

    for match in re.finditer(r"\[CALLOUT:([a-zA-Z]+)\]", text):
        color = match.group(1).lower()
        if color not in VALID_CALLOUT_COLORS:
            issues.append(LintIssue("warning", f"invalid CALLOUT color '{color}'"))

    for match in re.finditer(r"\[TRL:(-?\d+)\]", text):
        val = int(match.group(1))
        if not 1 <= val <= 9:
            issues.append(LintIssue("warning", f"TRL out of range: {val}"))

    for match in re.finditer(r"\[CASE\](.*?)\[/CASE\]", text, re.DOTALL):
        if match.group(1).count("|") < 2:
            issues.append(LintIssue("warning", "CASE block needs 3 |-separated fields"))

    for match in re.finditer(r"\[KPI\](.*?)\[/KPI\]", text, re.DOTALL):
        if match.group(1).count("|") < 3:
            issues.append(LintIssue("warning", "KPI block needs 4 |-separated fields"))

    return issues


def has_errors(text: str) -> bool:
    return any(i.level == "error" for i in lint(text))


def autofix(text: str) -> str:
    """Only unambiguous fixes: invalid CALLOUT color → blue, TRL clamped to 1..9."""

    def fix_color(match: re.Match) -> str:
        color = match.group(1).lower()
        return match.group(0) if color in VALID_CALLOUT_COLORS else "[CALLOUT:blue]"

    def fix_trl(match: re.Match) -> str:
        val = max(1, min(9, int(match.group(1))))
        return f"[TRL:{val}]"

    text = re.sub(r"\[CALLOUT:([a-zA-Z]+)\]", fix_color, text)
    text = re.sub(r"\[TRL:(-?\d+)\]", fix_trl, text)
    return text


_HEBREW_CHARS = re.compile(r"[א-ת]")


def lint_formulas(text: str) -> list[LintIssue]:
    """Part-E §22.1: real LaTeX validation of [FORMULA] blocks.

    Cheap deterministic checks always run (balanced braces, \\left/\\right
    pairing, no Hebrew inside math — it breaks RTL rendering); when
    matplotlib is installed its mathtext parser validates the LaTeX itself.
    A failing formula is an error that sends the chapter back to the writer.
    """
    issues: list[LintIssue] = []
    try:
        from matplotlib.mathtext import MathTextParser
        parser: object | None = MathTextParser("agg")
    except ImportError:
        parser = None

    for match in re.finditer(r"\[FORMULA\](.*?)\[/FORMULA\]", text, re.DOTALL):
        latex = match.group(1).strip()
        label = latex[:40].replace("\n", " ")
        if latex.count("{") != latex.count("}"):
            issues.append(LintIssue("error", f"נוסחה עם סוגריים לא מאוזנים: {label}"))
            continue
        if len(re.findall(r"\\left\b", latex)) != len(re.findall(r"\\right\b", latex)):
            issues.append(LintIssue("error", f"נוסחה עם \\left/\\right לא מזווגים: {label}"))
            continue
        if _HEBREW_CHARS.search(latex):
            issues.append(LintIssue("error",
                                    f"תווים עבריים בתוך נוסחה (שוברים RTL): {label}"))
            continue
        if parser is not None:
            # mathtext does not know \text-style commands — strip them first.
            cleaned = re.sub(r"\\(?:text|operatorname|mathrm)\{([^{}]*)\}", r"\1", latex)
            cleaned = cleaned.replace("$", "")
            try:
                parser.parse(f"${cleaned}$")  # type: ignore[attr-defined]
            except Exception:  # noqa: BLE001 - parser raises ValueError subclasses
                issues.append(LintIssue("error", f"נוסחה שנכשלה בפרסינג LaTeX: {label}"))
    return issues


def marker_census(text: str) -> dict[str, int]:
    """Tag → count, used by the language editor's safety guard."""
    census: dict[str, int] = {}
    for tag in PROTECTED_TAGS:
        if tag == "TRL":
            census[tag] = len(re.findall(r"\[TRL:\d+\]", text))
        elif tag.startswith("/"):
            census[tag] = len(re.findall(rf"\[/{tag[1:]}\]", text))
        elif tag == "CALLOUT":
            census[tag] = _open_count(text, "CALLOUT")
        else:
            census[tag] = len(re.findall(rf"\[{tag}\]", text))
    return census

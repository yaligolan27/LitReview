"""Stage 7 — Claim Grounder (spec §9.7).

Claim extraction is deterministic code (no LLM). One LLM call judges all of
a chapter's claims against the sources they cite; enforcement then applies
two hard rules: a factual claim without a citation is at best "uncertain",
and softened rewrites for uncertain/unsupported claims are applied to the
content automatically.
"""

from __future__ import annotations

import re

from ..core.context import RunContext
from ..core.llm import extract_json
from ..core.state import Claim, SurveySection, SurveyState

_FACT_TRIGGERS = (
    "מחקר", "מצא", "נמצא", "הוכ", "הראה", "מצביע", "ניסוי", "תוצא", "דיווח",
    "שיפור", "הפחת", "עליי", "ירידה", "%",
    "study", "found", "showed", "research", "results", "demonstrat",
    "improv", "reduc",
)

_CITE = re.compile(r"\[(\d+(?:\s*[-,]\s*\d+)*)\]")
_WCITE = re.compile(r"\[W\d+(?:\s*,\s*W\d+)*\]")
_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+|\n\n+")

_SYSTEM = (
    "אתה בודק עיגון טענות בסקירת ספרות. לכל טענה קבע האם המקורות שצוטטו בה "
    "באמת תומכים בה. אתה מחזיר JSON בלבד."
)


def strip_for_claims(text: str) -> str:
    """Remove marker blocks and formatting, keeping prose and citations."""
    text = re.sub(r"\[(?:TABLE|FORMULA|CASE|KPI|KPI_DATA|CONCLUSION|ROI_CALC|EXAMPLE)\]"
                  r".*?\[/(?:TABLE|FORMULA|CASE|KPI|KPI_DATA|CONCLUSION|ROI_CALC|EXAMPLE)\]",
                  " ", text, flags=re.DOTALL)
    text = re.sub(r"\[CALLOUT(?::[a-zA-Z]+)?\](.*?)\[/CALLOUT\]", r" \1 ", text, flags=re.DOTALL)
    text = re.sub(r"\[TRL:\d+\]", " ", text)
    text = re.sub(r"^#{1,6}\s.*$", " ", text, flags=re.MULTILINE)
    text = text.replace("**", "")
    return text


def extract_claims(sec: SurveySection, chapter_label: str, max_claims: int) -> list[Claim]:
    claims: list[Claim] = []
    prose = strip_for_claims(sec.content)
    web_claims = 0
    for raw in _SENTENCE_SPLIT.split(prose):
        sentence = " ".join(raw.split()).strip()
        if not sentence:
            continue
        cites = _CITE.findall(sentence)
        wcites = _WCITE.findall(sentence)
        numbers: list[int] = []
        for token in cites:
            for part in token.split(","):
                part = part.strip()
                if "-" in part:
                    try:
                        lo, hi = (int(x) for x in part.split("-", 1))
                        numbers.extend(range(lo, hi + 1))
                    except ValueError:
                        pass
                else:
                    try:
                        numbers.append(int(part))
                    except ValueError:
                        pass

        if numbers and len(sentence) >= 15:
            claims.append(Claim(text=sentence, citations=sorted(set(numbers)),
                                chapter=chapter_label))
        elif wcites and not numbers:
            web_claims += 1     # grounded by the deep-research layer, judged there
        elif not numbers and len(sentence) >= 35 and \
                any(t in sentence for t in _FACT_TRIGGERS):
            claims.append(Claim(text=sentence, citations=[], chapter=chapter_label))
        if len(claims) >= max_claims:
            break
    for i, claim in enumerate(claims, start=1):
        claim.id = f"{chapter_label}:{i}"
    sec._web_claims = web_claims  # type: ignore[attr-defined]  # transient, per extraction
    return claims


def _judge_prompt(sec: SurveySection, claims: list[Claim]) -> str:
    lines = [f"CLAIMS_COUNT: {len(claims)}", "", "המקורות של הפרק:"]
    for i, p in enumerate(sec.papers, start=1):
        abstract = (p.abstract or "")[:500]
        lines.append(f"[{i}] {p.title} ({p.year or 'n.d.'}): {abstract}")
        if p.has_fulltext and p.fulltext_excerpt:
            lines.append(f"    טקסט מלא: {p.fulltext_excerpt[:400]}")
    lines.append("")
    lines.append("הטענות לבדיקה:")
    for i, c in enumerate(claims, start=1):
        cited = ",".join(str(n) for n in c.citations) or "ללא ציטוט"
        lines.append(f"{i}. ({cited}) {c.text}")
    lines.append("")
    lines.append(
        'החזר JSON: רשימה של אובייקטים {"index": n, "status": '
        '"supported"|"uncertain"|"unsupported", "reason": "...", "rewrite": "..."} '
        "— rewrite הוא ניסוח מרוכך של הטענה (רק אם אינה נתמכת במלואה, אחרת ריק)."
    )
    return "\n".join(lines)


def _apply_verdicts(sec: SurveySection, claims: list[Claim], verdicts) -> None:
    by_index = {}
    if isinstance(verdicts, list):
        for v in verdicts:
            try:
                by_index[int(v.get("index"))] = v
            except (TypeError, ValueError):
                continue
    for i, claim in enumerate(claims, start=1):
        v = by_index.get(i, {})
        status = str(v.get("status", "uncertain")).lower()
        if status not in ("supported", "uncertain", "unsupported"):
            status = "uncertain"
        claim.status = status
        claim.reason = str(v.get("reason", ""))
        claim.rewrite = str(v.get("rewrite", ""))

        # Rule 1: a factual claim with no citation is at most "uncertain".
        if not claim.citations and claim.status == "supported":
            claim.status = "uncertain"
            claim.reason = (claim.reason + " (טענה ללא ציטוט)").strip()
        # Rule 2: softened rewrite applied to the content automatically.
        if claim.status in ("uncertain", "unsupported") and claim.rewrite \
                and claim.text in sec.content:
            sec.content = sec.content.replace(claim.text, claim.rewrite, 1)
            claim.text = claim.rewrite


def _mark_cross_corroborated(sec: SurveySection, claims: list[Claim]) -> None:
    """Part-E §21.2 signal 9 — deterministic, no network: a supported claim
    cited by 2+ sources whose author groups are disjoint gets a
    "cross-corroborated" tag (independent research groups agree)."""
    for claim in claims:
        if claim.effective_status() != "supported" or len(claim.citations) < 2:
            continue
        author_sets = []
        for n in claim.citations:
            if 1 <= n <= len(sec.papers):
                authors = {a.split(",")[0].strip().lower()
                           for a in sec.papers[n - 1].authors if a.strip()}
                if authors:
                    author_sets.append(authors)
        for i in range(len(author_sets)):
            for j in range(i + 1, len(author_sets)):
                if author_sets[i].isdisjoint(author_sets[j]):
                    claim.cross_corroborated = True
                    break
            if claim.cross_corroborated:
                break


def run_claim_grounder(ctx: RunContext, state: SurveyState,
                       only_sections: list[SurveySection] | None = None) -> SurveyState:
    targets = only_sections if only_sections is not None else state.sections
    for chapter_no, sec in enumerate(state.sections, start=1):
        if sec not in targets:
            continue
        claims = extract_claims(sec, chapter_label=str(chapter_no),
                                max_claims=ctx.settings.max_claims)
        if claims:
            try:
                verdicts = extract_json(
                    ctx.llm.complete(_judge_prompt(sec, claims),
                                     purpose="grounder", system=_SYSTEM))
            except ValueError:
                verdicts = []
                ctx.log_line("ground", f"chapter {chapter_no}: unparseable verdicts",
                             level="warn")
            _apply_verdicts(sec, claims, verdicts)
            _mark_cross_corroborated(sec, claims)
        sec.claims = claims
        sec.stale_grounding = False

    _build_report(state)
    state.log("ground", "claim grounding complete",
              total=state.grounding_report.get("total_claims", 0),
              supported_pct=state.grounding_report.get("supported_pct", 0))
    return state


def _build_report(state: SurveyState) -> None:
    total = supported = uncertain = unsupported = web = 0
    by_chapter = []
    for i, sec in enumerate(state.sections, start=1):
        counts = {"supported": 0, "uncertain": 0, "unsupported": 0}
        for claim in sec.claims:
            counts[claim.effective_status()] = counts.get(claim.effective_status(), 0) + 1
        sec_web = getattr(sec, "_web_claims", 0)
        by_chapter.append({"chapter": sec.title, "total": len(sec.claims),
                           **counts, "web_claims": sec_web})
        total += len(sec.claims)
        supported += counts["supported"]
        uncertain += counts["uncertain"]
        unsupported += counts["unsupported"]
        web += sec_web

    def pct(n: int) -> float:
        return round(100.0 * n / total, 1) if total else 0.0

    cross = sum(1 for sec in state.sections for c in sec.claims
                if c.cross_corroborated)
    state.grounding_report = {
        "total_claims": total,
        "supported": supported, "uncertain": uncertain, "unsupported": unsupported,
        "supported_pct": pct(supported), "uncertain_pct": pct(uncertain),
        "unsupported_pct": pct(unsupported),
        "web_claims": web,
        "cross_corroborated": cross,
        "by_chapter": by_chapter,
    }

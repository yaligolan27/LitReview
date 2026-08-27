"""Part-E wave 2 — reliability signals (spec §21).

Nine independent trust signals per *cited* paper, behind
``SURVEY_RELIABILITY_SIGNALS`` (default OFF). The compass is unchanged: a
signal is *evidence for the reader*, never an automatic gate. Nothing here
removes a paper — the predatory-journal list is display-only, and a possible
retraction is surfaced as a warning, not a deletion (retraction removal stays
the auditor's job, from its four dedicated sources).

The score honours the checked≠valid discipline (reliability mechanism #4):
each signal reports ``ok`` / ``flag`` (checked) or ``unchecked`` / ``n/a``
(no verdict). ``reliability_score`` is the weighted mean over the *checked*
signals only, so a network outage drops signals out of the denominator — it
never lowers the score. All signals with ``ok``/``flag`` carry ``points`` in
[0, 1]; the aggregate is ``100 * Σ(w·points) / Σ(w)`` over those.

Wiring note (a deliberate divergence from the plan's "reliability_auditor"):
enrichment runs at the top of the Evaluator stage, not the S2 auditor —
``cited_papers`` only exists after the Citation Manager, and the cap is "only
the cited papers". Running it in S2 would enrich hundreds of never-cited
papers. See ``run_reliability_signals``.
"""

from __future__ import annotations

import csv
import re
from pathlib import Path

from ..apis import crossref, openalex, semantic_scholar
from .context import RunContext
from .state import Paper, SurveyState

# Per-signal weights (sum = 1.0). Renormalized over the checked subset.
_WEIGHTS = {
    "author": 0.15,
    "journal": 0.15,
    "predatory": 0.10,
    "institution": 0.08,
    "self_citation": 0.12,
    "citation_context": 0.15,
    "errata": 0.13,
    "funding": 0.05,
    "cross_consensus": 0.07,
}

_CHECKED = ("ok", "flag")
_FUNDING_TERMS = ("funded by", "funding", "grant", "מומן", "מימון", "מענק")
_COI_TERMS = ("conflict of interest", "competing interest", "ניגוד עניינים",
              "no competing", "declare no")


# ---------------------------------------------------------------------------
# Predatory-journal list — local, manual, DISPLAY-ONLY (never auto-rejects)
# ---------------------------------------------------------------------------


class PredatoryList:
    """Loaded once from ``data/predatory_journals.csv``. A missing or empty
    file means "no list available" → the predatory signal stays *unchecked*
    (honest: absence of a list is not a clean bill of health)."""

    def __init__(self, path: str | Path = "data/predatory_journals.csv"):
        self.by_name: dict[str, str] = {}
        self.by_issn: dict[str, str] = {}
        self._load(Path(path))

    def _load(self, path: Path) -> None:
        if not path.exists():
            return
        try:
            with open(path, encoding="utf-8", errors="replace") as fh:
                rows = [ln for ln in fh if ln.strip() and not ln.lstrip().startswith("#")]
            for row in csv.DictReader(rows):
                low = {k.lower().strip(): (v or "").strip() for k, v in row.items() if k}
                name = _norm_journal(low.get("name") or low.get("journal") or "")
                issn = re.sub(r"[^0-9xX]", "", low.get("issn") or "")
                src = low.get("list_source") or low.get("source") or "רשימה מקומית"
                if name:
                    self.by_name[name] = src
                if issn:
                    self.by_issn[issn] = src
        except (OSError, csv.Error):
            pass

    @property
    def loaded(self) -> bool:
        return bool(self.by_name or self.by_issn)

    def match(self, journal: str) -> str:
        return self.by_name.get(_norm_journal(journal), "")


def _norm_journal(name: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s]", " ", (name or "").lower())).strip()


_PREDATORY: PredatoryList | None = None


def _predatory_list() -> PredatoryList:
    global _PREDATORY
    if _PREDATORY is None:
        _PREDATORY = PredatoryList()
    return _PREDATORY


def reset_predatory_cache() -> None:
    global _PREDATORY
    _PREDATORY = None


# ---------------------------------------------------------------------------
# Individual signals — each returns {status, label, detail, points}
# ---------------------------------------------------------------------------


def _sig(status: str, label: str, detail: str = "", points: float | None = None) -> dict:
    return {"status": status, "label": label, "detail": detail, "points": points}


def _author_signal(work: dict | None, offline: bool, topic_terms: set[str]) -> dict:
    label = "פרופיל מחבר"
    if offline or not work:
        return _sig("unchecked", label, "לא נבדק (אין גישת רשת/עבודה)")
    authorships = work.get("authorships") or []
    author_id = ""
    for a in authorships:
        author_id = ((a.get("author") or {}).get("id")) or ""
        if author_id:
            break
    if not author_id:
        return _sig("unchecked", label, "מזהה מחבר לא זמין")
    prof = openalex.author_profile(author_id)
    if prof.get("status") != "ok":
        return _sig("unchecked", label, "פרופיל המחבר לא נבדק")
    h = prof.get("h_index") or 0
    points = 1.0 if h >= 40 else 0.8 if h >= 20 else 0.6 if h >= 10 \
        else 0.4 if h >= 5 else 0.25
    bits = [f"h-index {h}", f"{prof.get('works_count') or 0} עבודות"]
    if prof.get("orcid"):
        bits.append("ORCID מאומת")
        points = min(1.0, points + 0.05)
    concepts = {c.lower() for c in prof.get("concepts") or []}
    if topic_terms and concepts and (topic_terms & {w for c in concepts for w in c.split()}):
        bits.append("חפיפת תחום לנושא")
    name = prof.get("display_name") or "מחבר ראשון"
    return _sig("ok", label, f"{name}: " + ", ".join(bits), points)


def _journal_signal(paper: Paper, work: dict | None, offline: bool) -> dict:
    label = "פרופיל כתב-עת"
    if offline or not work:
        return _sig("unchecked", label, "לא נבדק (אין גישת רשת)")
    source_id = (((work.get("primary_location") or {}).get("source") or {}).get("id")) or ""
    if not source_id:
        return _sig("unchecked", label, "מזהה כתב-עת לא זמין")
    prof = openalex.source_profile(source_id)
    if prof.get("status") != "ok":
        return _sig("unchecked", label, "פרופיל כתב-העת לא נבדק")
    cited = prof.get("two_year_mean_citedness") or 0.0
    points = 1.0 if cited >= 5 else 0.8 if cited >= 2 else 0.6 if cited >= 1 \
        else 0.4 if cited > 0 else 0.25
    bits = [f"citedness דו-שנתי {cited:.2f}"]
    if prof.get("is_in_doaj"):
        bits.append("ב-DOAJ (OA לגיטימי)")
        points = min(1.0, points + 0.05)
    if prof.get("is_core"):
        bits.append("OpenAlex core")
    return _sig("ok", label, f"{prof.get('display_name') or paper.journal}: "
                + ", ".join(bits), points)


def _predatory_signal(paper: Paper) -> dict:
    label = "בדיקת רשימת חשד"
    plist = _predatory_list()
    if not plist.loaded:
        # No local list → we genuinely cannot assess this. Honest: unchecked.
        return _sig("unchecked", label, "אין רשימת חשד מקומית טעונה")
    if not paper.journal:
        return _sig("n/a", label, "אין שם כתב-עת")
    hit = plist.match(paper.journal)
    if hit:
        return _sig("flag", label,
                    f"⚠️ כתב-העת מופיע ברשימת חשד ({hit}). סימון לתשומת לב "
                    "הקורא בלבד — המקור לא הוסר.", 0.1)
    return _sig("ok", label, "לא נמצא ברשימות חשד מקומיות", 0.8)


def _institution_signal(work: dict | None, offline: bool) -> dict:
    label = "שיוך מוסדי"
    if offline or not work:
        return _sig("unchecked", label, "לא נבדק")
    names: list[str] = []
    for a in work.get("authorships") or []:
        for inst in a.get("institutions") or []:
            n = inst.get("display_name")
            if n and n not in names:
                names.append(n)
    if not names:
        return _sig("unchecked", label, "לא צוין שיוך מוסדי")
    return _sig("ok", label, "; ".join(names[:3]), 0.6)


def _self_citation_signal(paper: Paper, offline: bool) -> dict:
    label = "ציטוט-עצמי"
    if offline or not (paper.doi or paper.id):
        return _sig("unchecked", label, "לא נבדק")
    refs = semantic_scholar.references(paper, limit=25)
    if not refs:
        return _sig("unchecked", label, "רשימת מקורות לא זמינה")
    own = {_norm_name(a) for a in paper.authors if a}
    if not own:
        return _sig("unchecked", label, "שמות מחברים לא זמינים")
    self_refs = sum(1 for r in refs
                    if own & {_norm_name(a) for a in r.authors if a})
    ratio = self_refs / len(refs)
    if ratio > 0.4:
        return _sig("flag", label,
                    f"⚠️ שיעור ציטוט-עצמי גבוה: {self_refs}/{len(refs)} "
                    f"({ratio:.0%})", 0.3)
    return _sig("ok", label, f"ציטוט-עצמי {self_refs}/{len(refs)} ({ratio:.0%})", 0.85)


def _citation_context_signal(paper: Paper) -> dict:
    """Coarse but always-available (no extra network): citation volume buckets.
    Anchors the score offline-with-data so it is not None just because the
    live-lookup signals could not run."""
    label = "היקף ציטוט"
    c = paper.citation_count or 0
    points = 1.0 if c >= 100 else 0.8 if c >= 30 else 0.6 if c >= 10 \
        else 0.4 if c >= 1 else 0.2
    note = f"{c} ציטוטים" + (" — מאמר טרי/לא-מצוטט עדיין" if c == 0 else "")
    return _sig("ok", label, note, points)


def _errata_signal(updates: dict | None) -> dict:
    label = "תיקונים/Crossmark"
    if not updates or updates.get("status") != "ok":
        return _sig("unchecked", label, "לא נבדק")
    if updates.get("has_concern"):
        kinds = ", ".join(updates.get("update_kinds") or [])
        return _sig("flag", label,
                    f"⚠️ Crossmark מציין חשש ({kinds}). סימון לקורא — לאימות "
                    "מול מקורות ה-retraction.", 0.1)
    if updates.get("has_errata"):
        return _sig("ok", label, "פורסם תיקון (erratum/correction) — מהלך תקין", 0.7)
    return _sig("ok", label, "אין תיקונים/חששות ב-Crossmark", 0.9)


def _funding_signal(paper: Paper, updates: dict | None) -> dict:
    label = "מימון/גילוי COI"
    text = f"{paper.abstract} {paper.fulltext_excerpt}".lower()
    has_coi = any(t in text for t in _COI_TERMS)
    funders = (updates or {}).get("funders") if updates and updates.get("status") == "ok" else None
    if funders:
        detail = "מומן: " + "; ".join(funders[:3])
        if has_coi:
            detail += " · הצהרת COI בטקסט"
        return _sig("ok", label, detail, 0.8)
    if has_coi:
        return _sig("ok", label, "הצהרת ניגוד עניינים/מימון מופיעה בטקסט", 0.75)
    if any(t in text for t in _FUNDING_TERMS):
        return _sig("ok", label, "אזכור מימון בטקסט", 0.6)
    return _sig("unchecked", label, "אין נתוני מימון/COI זמינים")


def _consensus_signal(consensus: bool) -> dict:
    label = "קונצנזוס בין-מחקרי"
    if consensus:
        return _sig("ok", label,
                    "המקור תומך בטענה שאוששה על-ידי ≥2 קבוצות מחברים נפרדות", 1.0)
    return _sig("unchecked", label, "לא נקבע קונצנזוס עבור מקור זה")


def _norm_name(name: str) -> str:
    # "Family, Given" and "Given Family" collapse to a comparable surname token.
    part = name.split(",")[0] if "," in name else name.split()[-1] if name.split() else name
    return re.sub(r"[^\w]", "", part.lower())


# ---------------------------------------------------------------------------
# Aggregation
# ---------------------------------------------------------------------------


def enrich(paper: Paper, *, topic_terms: set[str] | None = None,
           consensus: bool = False, offline: bool = False) -> dict:
    """Compute the 9 signals for one paper, store on ``paper.reliability_signals``
    and return the block. Network signals are skipped when ``offline``."""
    topic_terms = topic_terms or set()

    work = None
    updates = None
    if not offline and paper.doi:
        fetched = openalex.fetch_work_by_doi(paper.doi)
        work = fetched.get("work") if fetched.get("status") == "ok" else None
        updates = crossref.updates(paper.doi)

    signals = {
        "author": _author_signal(work, offline, topic_terms),
        "journal": _journal_signal(paper, work, offline),
        "predatory": _predatory_signal(paper),
        "institution": _institution_signal(work, offline),
        "self_citation": _self_citation_signal(paper, offline),
        "citation_context": _citation_context_signal(paper),
        "errata": _errata_signal(updates),
        "funding": _funding_signal(paper, updates),
        "cross_consensus": _consensus_signal(consensus),
    }

    num = den = 0.0
    checked = 0
    for name, sig in signals.items():
        if sig["status"] in _CHECKED and sig.get("points") is not None:
            w = _WEIGHTS[name]
            num += w * float(sig["points"])
            den += w
            checked += 1
    score = round(100 * num / den) if den > 0 else None

    block = {
        "score": score,
        "tier": _tier_label(score),
        "checked": checked,
        "flags": sum(1 for s in signals.values() if s["status"] == "flag"),
        "signals": signals,
    }
    paper.reliability_signals = block
    return block


def _tier_label(score: int | None) -> str:
    if score is None:
        return "לא נבדק"
    return "גבוהה" if score >= 75 else "בינונית" if score >= 50 \
        else "מוגבלת" if score >= 25 else "נמוכה"


# ---------------------------------------------------------------------------
# Stage entry — enrich the cited papers (capped) at the top of the Evaluator
# ---------------------------------------------------------------------------


def _topic_terms(brief) -> set[str]:
    raw = f"{brief.search_topic} {' '.join(brief.subtopics)}".lower()
    return {w for w in re.findall(r"[a-z]{4,}", raw)}


def _consensus_keys(state: SurveyState) -> set[int]:
    """Object-identity keys of papers cited by a cross-corroborated claim.
    cited_papers and section.papers share objects in memory, so id() matches."""
    keys: set[int] = set()
    for sec in state.sections:
        for claim in sec.claims:
            if getattr(claim, "cross_corroborated", False):
                for n in claim.citations:
                    if 1 <= n <= len(sec.papers):
                        keys.add(id(sec.papers[n - 1]))
    return keys


def run_reliability_signals(ctx: RunContext, state: SurveyState) -> None:
    settings = ctx.settings
    if not settings.reliability_signals:
        return
    topic_terms = _topic_terms(state.brief)
    consensus = _consensus_keys(state)
    pool = state.cited_papers[:settings.signals_cap]
    for paper in pool:
        try:
            enrich(paper, topic_terms=topic_terms,
                   consensus=id(paper) in consensus, offline=ctx.offline)
        except Exception as exc:   # a signal must never break finalization
            paper.reliability_signals = {
                "score": None, "tier": "לא נבדק", "checked": 0, "flags": 0,
                "signals": {}, "error": str(exc)[:120]}
    scored = [p.reliability_signals.get("score") for p in pool
              if p.reliability_signals.get("score") is not None]
    state.log("signals", "reliability signals computed",
              enriched=len(pool),
              capped=len(state.cited_papers) > settings.signals_cap,
              mean_score=round(sum(scored) / len(scored)) if scored else None)

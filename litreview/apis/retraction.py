"""Retraction checks — four sources in order of reliability (spec §9.4a):

1. OpenAlex ``is_retracted`` (already on the Paper — the most reliable signal)
2. Title heuristics ("RETRACTED", "retracted:", "retraction of")
3. Local Retraction Watch CSV (``data/retraction_watch.csv`` — manual
   download only, deliberate safety policy: no automatic fetching)
4. Crossref relations/updates mentioning retract/withdraw/removal
   (budgeted: at most ``retraction_crossref_cap`` calls per run)
"""

from __future__ import annotations

import csv
import re
from pathlib import Path

from ..core.dedup import normalize_doi, normalize_title
from ..core.state import Paper
from . import _http

_TITLE_PATTERNS = (
    re.compile(r"^\s*retracted\b", re.IGNORECASE),
    re.compile(r"\bretracted:", re.IGNORECASE),
    re.compile(r"\bretraction of\b", re.IGNORECASE),
)

_CROSSREF_WORKS = "https://api.crossref.org/works"
_RETRACT_WORDS = ("retract", "withdraw", "removal")


class RetractionWatch:
    """The local CSV, loaded once. Missing file = empty index (fine)."""

    def __init__(self, path: str | Path = "data/retraction_watch.csv"):
        self.by_doi: dict[str, str] = {}
        self.by_title: dict[str, str] = {}
        self._load(Path(path))

    def _load(self, path: Path) -> None:
        if not path.exists():
            return
        try:
            with open(path, encoding="utf-8", errors="replace") as fh:
                for row in csv.DictReader(fh):
                    lowered = {k.lower().strip(): (v or "").strip()
                               for k, v in row.items() if k}
                    doi = normalize_doi(lowered.get("originalpaperdoi")
                                        or lowered.get("doi") or "")
                    title = normalize_title(lowered.get("title") or "")
                    reason = lowered.get("reason") or lowered.get("retractionnature") \
                        or "listed in Retraction Watch"
                    if doi:
                        self.by_doi[doi] = reason
                    if title:
                        self.by_title[title] = reason
        except (OSError, csv.Error):
            pass

    def lookup(self, paper: Paper) -> str:
        doi = normalize_doi(paper.doi)
        if doi and doi in self.by_doi:
            return self.by_doi[doi]
        title = normalize_title(paper.title)
        if title and title in self.by_title:
            return self.by_title[title]
        return ""


def _crossref_retraction(doi: str) -> str:
    """Source 4: Crossref relation / update-to entries. Empty = not retracted.
    Raises NetworkError upward — the caller must not treat it as 'clean'."""
    data = _http.get_json(f"{_CROSSREF_WORKS}/{doi}")
    message = (data or {}).get("message") or {}
    for update in message.get("update-to") or []:
        utype = str(update.get("type", "")).lower()
        if any(w in utype for w in _RETRACT_WORDS):
            return f"Crossref update-to: {utype}"
    relations = message.get("relation") or {}
    for rel_name in relations:
        if any(w in rel_name.lower() for w in _RETRACT_WORDS):
            return f"Crossref relation: {rel_name}"
    return ""


def check_paper(paper: Paper, watch: RetractionWatch,
                crossref_budget: list[int], use_crossref: bool = True) -> tuple[bool, str]:
    """Returns (is_retracted, note). ``crossref_budget`` is a single-element
    mutable counter shared across the run (spec: cap 60 Crossref calls)."""
    if paper.is_retracted:
        return True, paper.retraction_note or "flagged by OpenAlex"

    for pattern in _TITLE_PATTERNS:
        if pattern.search(paper.title or ""):
            return True, "retraction marker in title"

    note = watch.lookup(paper)
    if note:
        return True, f"Retraction Watch: {note}"

    if use_crossref and paper.doi and crossref_budget[0] > 0:
        crossref_budget[0] -= 1
        try:
            note = _crossref_retraction(paper.doi)
        except (_http.NotFoundError, _http.NetworkError):
            note = ""   # could not check — never counts as retracted
        if note:
            return True, note

    return False, ""

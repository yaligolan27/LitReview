"""Duplicate removal — spec §10 (core/dedup.py).

DOI-first, then fuzzy title matching with year / first-author / high-similarity
confirmation. RapidFuzz is used when installed; difflib otherwise (no install
requirement). Merging upgrades the kept record with missing fields.
"""

from __future__ import annotations

import re
import unicodedata

from .state import Paper

try:
    from rapidfuzz import fuzz as _rf_fuzz

    _ENGINE = "rapidfuzz"

    def similarity(a: str, b: str) -> float:
        return float(_rf_fuzz.token_sort_ratio(a, b))

except ImportError:  # pragma: no cover - depends on environment
    from difflib import SequenceMatcher

    _ENGINE = "difflib"

    def similarity(a: str, b: str) -> float:
        ta = " ".join(sorted(a.split()))
        tb = " ".join(sorted(b.split()))
        return SequenceMatcher(None, ta, tb).ratio() * 100.0


_DOI_PREFIXES = ("https://doi.org/", "http://doi.org/", "https://dx.doi.org/",
                 "http://dx.doi.org/", "doi.org/", "dx.doi.org/", "doi:")


def normalize_doi(doi: str) -> str:
    """Lowercase, strip URL/label prefixes; arXiv links are not DOIs; must
    start with ``10.`` — otherwise returns empty."""
    if not doi:
        return ""
    d = doi.strip().lower()
    for prefix in _DOI_PREFIXES:
        if d.startswith(prefix):
            d = d[len(prefix):]
    d = d.strip()
    if "arxiv.org" in d:
        return ""
    if not d.startswith("10."):
        return ""
    return d


def normalize_title(title: str) -> str:
    """NFKD (drops diacritics/niqqud), lowercase, punctuation→space, collapse."""
    if not title:
        return ""
    t = unicodedata.normalize("NFKD", title)
    t = "".join(ch for ch in t if not unicodedata.combining(ch))
    t = t.lower()
    t = re.sub(r"[^\w\s]", " ", t, flags=re.UNICODE)
    t = re.sub(r"\s+", " ", t).strip()
    return t


def _first_author(paper: Paper) -> str:
    return normalize_title(paper.authors[0]) if paper.authors else ""


def _merge_into(keep: Paper, new: Paper) -> None:
    """The kept record upgrades itself with anything the duplicate knows."""
    if not keep.doi and new.doi:
        keep.doi = new.doi
    if not keep.authors and new.authors:
        keep.authors = list(new.authors)
    if not keep.abstract and new.abstract:
        keep.abstract = new.abstract
    if not keep.year and new.year:
        keep.year = new.year
    if not keep.journal and new.journal:
        keep.journal = new.journal
    if not keep.url and new.url:
        keep.url = new.url
    if not keep.pdf_url and new.pdf_url:
        keep.pdf_url = new.pdf_url
    if not keep.language and new.language:
        keep.language = new.language
    if not keep.source_type and new.source_type:
        keep.source_type = new.source_type
    keep.citation_count = max(keep.citation_count, new.citation_count)
    keep.is_open_access = keep.is_open_access or new.is_open_access
    keep.is_retracted = keep.is_retracted or new.is_retracted
    if not keep.retraction_note and new.retraction_note:
        keep.retraction_note = new.retraction_note


def dedupe(papers: list[Paper], threshold: int = 92) -> tuple[list[Paper], dict]:
    unique: list[Paper] = []
    by_doi: dict[str, Paper] = {}
    stats = {"found": len(papers), "removed": 0, "kept": 0,
             "by_doi": 0, "by_fuzzy": 0, "engine": _ENGINE, "threshold": threshold}

    for paper in papers:
        doi = normalize_doi(paper.doi)
        if doi and doi in by_doi:
            _merge_into(by_doi[doi], paper)
            stats["removed"] += 1
            stats["by_doi"] += 1
            continue

        duplicate_of: Paper | None = None
        norm = normalize_title(paper.title)
        if norm:
            for kept in unique:
                kept_norm = normalize_title(kept.title)
                if not kept_norm:
                    continue
                if norm == kept_norm:
                    duplicate_of = kept
                    break
                sim = similarity(norm, kept_norm)
                if sim < threshold:
                    continue
                if paper.year and kept.year and paper.year == kept.year:
                    duplicate_of = kept
                    break
                if _first_author(paper) and _first_author(paper) == _first_author(kept):
                    duplicate_of = kept
                    break
                if sim >= 97:
                    duplicate_of = kept
                    break

        if duplicate_of is not None:
            _merge_into(duplicate_of, paper)
            stats["removed"] += 1
            stats["by_fuzzy"] += 1
            continue

        unique.append(paper)
        if doi:
            by_doi[doi] = paper

    stats["kept"] = len(unique)
    return unique, stats

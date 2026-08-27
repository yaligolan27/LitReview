"""DBLP connector — T1, computer science core (spec §11.2). No abstracts;
DOI backfill (M2) fills missing DOIs by title."""

from __future__ import annotations

from ..core.state import Paper
from . import _http

BASE = "https://dblp.org/search/publ/api"

_TYPE_MAP = {
    "journal articles": "journal-article",
    "conference and workshop papers": "proceedings-article",
    "books and theses": "book-chapter",
    "informal publications": "preprint",
}


def _normalize(hit: dict) -> Paper:
    info = hit.get("info") or {}
    authors_raw = ((info.get("authors") or {}).get("author")) or []
    if isinstance(authors_raw, dict):
        authors_raw = [authors_raw]
    authors = [a.get("text", "") if isinstance(a, dict) else str(a) for a in authors_raw]
    year = None
    if str(info.get("year", "")).isdigit():
        year = int(info["year"])
    return Paper(
        id=f"dblp:{info.get('key', hit.get('@id', ''))}",
        title=(info.get("title") or "").rstrip("."),
        year=year,
        authors=authors[:25],
        journal=info.get("venue") or "",
        doi=info.get("doi", "") or "",
        url=info.get("ee") or info.get("url") or "",
        source="dblp",
        source_type=_TYPE_MAP.get((info.get("type") or "").lower(), "journal-article"),
    )


def search(query: str, limit: int = 5,
           year_from: int | None = None, year_to: int | None = None) -> list[Paper]:
    try:
        data = _http.get_json(BASE, params={"q": query, "format": "json",
                                            "h": max(1, min(50, limit))})
    except _http.NotFoundError:
        return []
    hits = (((data.get("result") or {}).get("hits") or {}).get("hit")) or []
    papers = [_normalize(h) for h in hits]
    if year_from or year_to:
        papers = [p for p in papers
                  if p.year is None or (year_from or 0) <= p.year <= (year_to or 9999)]
    return papers

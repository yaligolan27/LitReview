"""DOAJ connector — T1, always on. Open-access journals — spec §11.2."""

from __future__ import annotations

import urllib.parse

from ..core.state import Paper
from . import _http

BASE = "https://doaj.org/api/search/articles"


def _normalize(item: dict) -> Paper:
    bib = item.get("bibjson") or {}
    doi = ""
    for ident in bib.get("identifier") or []:
        if (ident.get("type") or "").lower() == "doi":
            doi = ident.get("id", "")
            break
    url = ""
    for link in bib.get("link") or []:
        if link.get("url"):
            url = link["url"]
            break
    year = None
    try:
        year = int(bib.get("year"))
    except (TypeError, ValueError):
        pass
    return Paper(
        id=f"doaj:{item.get('id', '')}",
        title=bib.get("title") or "",
        abstract=(bib.get("abstract") or "")[:2000],
        year=year,
        authors=[a.get("name", "") for a in (bib.get("author") or [])][:25],
        journal=((bib.get("journal") or {}).get("title")) or "",
        doi=doi,
        url=url,
        source="doaj",
        source_type="journal-article",
        is_open_access=True,
    )


def search(query: str, limit: int = 5,
           year_from: int | None = None, year_to: int | None = None) -> list[Paper]:
    encoded = urllib.parse.quote(query, safe="")
    try:
        data = _http.get_json(f"{BASE}/{encoded}", params={"pageSize": max(1, min(50, limit))})
    except _http.NotFoundError:
        return []
    papers = [_normalize(item) for item in (data.get("results") or [])]
    if year_from or year_to:
        papers = [p for p in papers
                  if p.year is None or (year_from or 0) <= p.year <= (year_to or 9999)]
    return papers

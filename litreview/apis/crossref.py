"""Crossref connector — T1, always on. The official DOI registry: search,
DOI verification, and (M2) reverse DOI lookup by title (spec §11.2)."""

from __future__ import annotations

import re

from ..config import get_settings
from ..core.state import Paper
from . import _http

BASE = "https://api.crossref.org/works"


def _strip_jats(text: str) -> str:
    return re.sub(r"<[^>]+>", " ", text or "").strip()[:2000]


def _normalize(item: dict) -> Paper:
    year = None
    for key in ("published-print", "published-online", "issued", "created"):
        parts = ((item.get(key) or {}).get("date-parts") or [[None]])[0]
        if parts and parts[0]:
            year = parts[0]
            break
    authors = []
    for a in item.get("author") or []:
        family, given = a.get("family", ""), a.get("given", "")
        if family and given:
            authors.append(f"{family}, {given}")
        elif family or given:
            authors.append(family or given)
    titles = item.get("title") or []
    containers = item.get("container-title") or []
    return Paper(
        id=f"crossref:{item.get('DOI', '')}",
        title=titles[0] if titles else "",
        abstract=_strip_jats(item.get("abstract", "")),
        year=year,
        authors=authors[:25],
        journal=containers[0] if containers else "",
        citation_count=item.get("is-referenced-by-count") or 0,
        doi=item.get("DOI", ""),
        url=item.get("URL", ""),
        source="crossref",
        source_type=item.get("type", ""),
        language=item.get("language") or "",
    )


def search(query: str, limit: int = 5,
           year_from: int | None = None, year_to: int | None = None) -> list[Paper]:
    filters = []
    if year_from:
        filters.append(f"from-pub-date:{year_from}-01-01")
    if year_to:
        filters.append(f"until-pub-date:{year_to}-12-31")
    params: dict = {
        "query": query,
        "rows": max(1, min(50, limit)),
        "mailto": get_settings().contact_email,
    }
    if filters:
        params["filter"] = ",".join(filters)
    try:
        data = _http.get_json(BASE, params=params)
    except _http.NotFoundError:
        return []
    items = ((data or {}).get("message") or {}).get("items") or []
    return [_normalize(i) for i in items]


def verify_doi(doi: str) -> dict:
    """The critical distinction (spec §9.4c): {"checked": bool, "valid": bool}.

    A network failure means we could NOT check — callers must not downgrade
    the paper for that.
    """
    if not doi:
        return {"checked": True, "valid": False}
    try:
        _http.get_json(f"{BASE}/{doi}")
    except _http.NotFoundError:
        return {"checked": True, "valid": False}
    except _http.NetworkError:
        return {"checked": False, "valid": False}
    return {"checked": True, "valid": True}


def fetch_by_doi(doi: str) -> Paper | None:
    try:
        data = _http.get_json(f"{BASE}/{doi}")
    except (_http.NotFoundError, _http.NetworkError):
        return None
    message = (data or {}).get("message")
    return _normalize(message) if message else None

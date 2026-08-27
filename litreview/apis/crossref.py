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


def find_doi_by_title(title: str, year: int | None = None,
                      min_similarity: int = 88) -> str:
    """Reverse lookup (DOI backfill, spec §9.4b): bibliographic search, best
    match by fuzzy title similarity (≥88) and year within ±1."""
    from ..core.dedup import normalize_title, similarity

    if not title.strip():
        return ""
    try:
        data = _http.get_json(BASE, params={
            "query.bibliographic": title, "rows": 3,
            "mailto": get_settings().contact_email})
    except (_http.NotFoundError, _http.NetworkError):
        return ""
    wanted = normalize_title(title)
    for item in ((data or {}).get("message") or {}).get("items") or []:
        candidate = _normalize(item)
        if not candidate.doi:
            continue
        if similarity(wanted, normalize_title(candidate.title)) < min_similarity:
            continue
        if year and candidate.year and abs(candidate.year - year) > 1:
            continue
        return candidate.doi
    return ""


def fetch_by_doi(doi: str) -> Paper | None:
    try:
        data = _http.get_json(f"{BASE}/{doi}")
    except (_http.NotFoundError, _http.NetworkError):
        return None
    message = (data or {}).get("message")
    return _normalize(message) if message else None


# --- Part-E wave 2: Crossmark / errata / funding signal (spec §21) ---------
_ERRATA_KINDS = ("correction", "erratum", "addendum", "corrigendum")
_CONCERN_KINDS = ("retraction", "expression_of_concern", "expression of concern",
                  "removal", "withdrawal", "partial_retraction")


def updates(doi: str) -> dict:
    """Crossmark relations + funders for a DOI, status-tagged (checked≠valid).

    ``has_concern`` flags a possible retraction / expression-of-concern — a
    *display* warning only; it never removes the paper (retraction removal is
    the auditor's job, from 4 dedicated sources).
    """
    if not doi:
        return {"status": "n/a"}
    try:
        data = _http.get_json(f"{BASE}/{doi}")
    except _http.NotFoundError:
        return {"status": "not_found"}
    except _http.NetworkError:
        return {"status": "unchecked"}
    msg = (data or {}).get("message")
    if not msg:
        return {"status": "not_found"}
    relations = list(msg.get("update-to") or []) + list(msg.get("updated-by") or [])
    kinds = sorted({str(u.get("type", "")).lower().replace("-", "_")
                    for u in relations if u.get("type")})
    funders = [str(f.get("name", "")).strip()
               for f in (msg.get("funder") or []) if f.get("name")]
    return {
        "status": "ok",
        "has_errata": any(k in _ERRATA_KINDS for k in kinds),
        "has_concern": any(k.replace("_", " ") in _CONCERN_KINDS or k in _CONCERN_KINDS
                           for k in kinds),
        "update_kinds": kinds,
        "funders": funders[:8],
        "has_funding": bool(funders),
    }

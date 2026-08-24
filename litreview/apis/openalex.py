"""OpenAlex connector — T1, always on. 250M works; the only source for
``is_retracted`` and ``language`` (spec §11.2)."""

from __future__ import annotations

from typing import Any

from ..config import get_settings
from ..core.state import Paper
from . import _http

BASE = "https://api.openalex.org/works"
AUTHORS = "https://api.openalex.org/authors"
SOURCES = "https://api.openalex.org/sources"

_TYPE_MAP = {
    "article": "journal-article",
    "preprint": "preprint",
    "review": "review",
    "book-chapter": "book-chapter",
    "report": "report",
    "dissertation": "report",
    "dataset": "dataset",
}


def _reconstruct_abstract(inverted: dict | None) -> str:
    if not inverted:
        return ""
    positions: dict[int, str] = {}
    for word, indexes in inverted.items():
        for i in indexes:
            positions[i] = word
    return " ".join(positions[i] for i in sorted(positions))[:2000]


def _short_id(openalex_id: str) -> str:
    return (openalex_id or "").rsplit("/", 1)[-1]


def _normalize(work: dict) -> Paper:
    ids = work.get("ids") or {}
    doi = (ids.get("doi") or "").replace("https://doi.org/", "")
    primary = work.get("primary_location") or {}
    source_meta = primary.get("source") or {}
    oa = work.get("open_access") or {}
    return Paper(
        id=_short_id(work.get("id", "")),
        title=work.get("display_name") or "",
        abstract=_reconstruct_abstract(work.get("abstract_inverted_index")),
        year=work.get("publication_year"),
        authors=[(a.get("author") or {}).get("display_name", "")
                 for a in (work.get("authorships") or [])][:25],
        journal=source_meta.get("display_name") or "",
        citation_count=work.get("cited_by_count") or 0,
        doi=doi,
        url=primary.get("landing_page_url") or work.get("id", ""),
        source="openalex",
        is_retracted=bool(work.get("is_retracted")),
        language=work.get("language") or "",
        source_type=_TYPE_MAP.get(work.get("type", ""), work.get("type") or ""),
        pdf_url=oa.get("oa_url") or "",
        is_open_access=bool(oa.get("is_oa")),
    )


def find_doi_by_title(title: str, year: int | None = None,
                      min_similarity: int = 88) -> str:
    """DOI backfill fallback after Crossref (spec §9.4b)."""
    from ..core.dedup import normalize_title, similarity

    if not title.strip():
        return ""
    try:
        data = _http.get_json(BASE, params={
            "filter": f"title.search:{title[:200]}",
            "per-page": 3,
            "mailto": get_settings().contact_email})
    except (_http.NotFoundError, _http.NetworkError):
        return ""
    wanted = normalize_title(title)
    for work in (data or {}).get("results") or []:
        candidate = _normalize(work)
        if not candidate.doi:
            continue
        if similarity(wanted, normalize_title(candidate.title)) < min_similarity:
            continue
        if year and candidate.year and abs(candidate.year - year) > 1:
            continue
        return candidate.doi
    return ""


# --- Part-E wave 2: reliability-signal fetchers (spec §21) -----------------
# Each returns a status-tagged dict so callers keep the checked≠valid
# discipline: "ok" (checked, present), "not_found" (checked, absent),
# "unchecked" (network failure — never a score penalty), "n/a" (no input).


def _status_fetch(url: str, params: dict | None = None) -> tuple[str, Any]:
    try:
        return "ok", _http.get_json(url, params=params)
    except _http.NotFoundError:
        return "not_found", None
    except _http.NetworkError:
        return "unchecked", None


def fetch_work_by_doi(doi: str) -> dict:
    """Full OpenAlex work by DOI — carries author ids, institutions, source id
    and referenced_works, the raw material for the other signals."""
    if not doi:
        return {"status": "n/a"}
    status, data = _status_fetch(BASE, {
        "filter": f"doi:{doi}", "per-page": 1,
        "mailto": get_settings().contact_email})
    if status != "ok":
        return {"status": status}
    results = (data or {}).get("results") or []
    return {"status": "ok", "work": results[0]} if results else {"status": "not_found"}


def author_profile(author_id: str) -> dict:
    short = _short_id(author_id)
    if not short:
        return {"status": "n/a"}
    status, data = _status_fetch(f"{AUTHORS}/{short}",
                                 {"mailto": get_settings().contact_email})
    if status != "ok" or not data:
        return {"status": "not_found" if status == "ok" else status}
    stats = data.get("summary_stats") or {}
    return {
        "status": "ok",
        "h_index": stats.get("h_index"),
        "i10_index": stats.get("i10_index"),
        "works_count": data.get("works_count"),
        "cited_by_count": data.get("cited_by_count"),
        "orcid": (data.get("ids") or {}).get("orcid") or data.get("orcid") or "",
        "display_name": data.get("display_name") or "",
        "concepts": [c.get("display_name", "")
                     for c in (data.get("x_concepts") or [])[:8] if c.get("display_name")],
    }


def source_profile(source_id: str) -> dict:
    short = _short_id(source_id)
    if not short:
        return {"status": "n/a"}
    status, data = _status_fetch(f"{SOURCES}/{short}",
                                 {"mailto": get_settings().contact_email})
    if status != "ok" or not data:
        return {"status": "not_found" if status == "ok" else status}
    stats = data.get("summary_stats") or {}
    return {
        "status": "ok",
        "two_year_mean_citedness": stats.get("2yr_mean_citedness"),
        "h_index": stats.get("h_index"),
        "is_in_doaj": bool(data.get("is_in_doaj")),
        "is_core": bool(data.get("is_core")),
        "is_oa": bool(data.get("is_oa")),
        "apc_usd": data.get("apc_usd"),
        "display_name": data.get("display_name") or "",
    }


def search(query: str, limit: int = 5,
           year_from: int | None = None, year_to: int | None = None,
           language: str | None = None) -> list[Paper]:
    filters = []
    if year_from:
        filters.append(f"from_publication_date:{year_from}-01-01")
    if year_to:
        filters.append(f"to_publication_date:{year_to}-12-31")
    if language:
        filters.append(f"language:{language}")
    params: dict = {
        "search": query,
        "per-page": max(1, min(50, limit)),
        "mailto": get_settings().contact_email,
    }
    if filters:
        params["filter"] = ",".join(filters)
    try:
        data = _http.get_json(BASE, params=params)
    except _http.NotFoundError:
        return []
    return [_normalize(w) for w in (data.get("results") or [])]

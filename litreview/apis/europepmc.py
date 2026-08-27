"""Europe PMC connector — T1, biomedical core + JATS full text (spec §11.2)."""

from __future__ import annotations

from ..core.state import Paper
from . import _http

BASE = "https://www.ebi.ac.uk/europepmc/webservices/rest"

_TYPE_MAP = {
    "research-article": "journal-article",
    "review-article": "review",
    "preprint": "preprint",
}


def _normalize(item: dict) -> Paper:
    year = None
    if str(item.get("pubYear", ""))[:4].isdigit():
        year = int(str(item["pubYear"])[:4])
    pub_type = (item.get("pubType") or "").split(";")[0].strip().lower()
    return Paper(
        id=f"europepmc:{item.get('id', '')}",
        title=item.get("title") or "",
        abstract=(item.get("abstractText") or "")[:2000],
        year=year,
        authors=[a.strip() for a in (item.get("authorString") or "").split(",") if a.strip()][:25],
        journal=item.get("journalTitle") or "",
        citation_count=item.get("citedByCount") or 0,
        doi=item.get("doi", "") or "",
        url=f"https://europepmc.org/article/{item.get('source', 'MED')}/{item.get('id', '')}",
        source="europepmc",
        source_type=_TYPE_MAP.get(pub_type, pub_type or "journal-article"),
        is_open_access=(item.get("isOpenAccess") == "Y"),
    )


def search(query: str, limit: int = 5,
           year_from: int | None = None, year_to: int | None = None) -> list[Paper]:
    q = query
    if year_from or year_to:
        q += f" AND PUB_YEAR:[{year_from or 1900} TO {year_to or 2100}]"
    params = {"query": q, "format": "json", "pageSize": max(1, min(50, limit)),
              "resultType": "core"}
    try:
        data = _http.get_json(f"{BASE}/search", params=params)
    except _http.NotFoundError:
        return []
    results = ((data.get("resultList") or {}).get("result")) or []
    return [_normalize(item) for item in results]


def find_fulltext_xml(doi: str = "", title: str = "") -> str:
    """Locate a PMCID for a paper that is inEPMC and return its JATS XML
    (empty string when unavailable) — spec §9.5."""
    query = f'DOI:"{doi}"' if doi else f'TITLE:"{title}"'
    try:
        data = _http.get_json(f"{BASE}/search", params={
            "query": query, "format": "json", "pageSize": 3, "resultType": "core"})
    except (_http.NotFoundError, _http.NetworkError):
        return ""
    for item in ((data.get("resultList") or {}).get("result")) or []:
        if item.get("inEPMC") == "Y" and item.get("pmcid"):
            try:
                return _http.get_text(f"{BASE}/{item['pmcid']}/fullTextXML")
            except (_http.NotFoundError, _http.NetworkError):
                continue
    return ""

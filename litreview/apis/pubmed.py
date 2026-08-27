"""PubMed connector — T1, biomedical core (spec §11.2). NCBI E-utilities:
esearch for ids, esummary for metadata (no abstract — Europe PMC covers
biomed abstracts and full text)."""

from __future__ import annotations

from ..core.state import Paper
from . import _http

ESEARCH = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
ESUMMARY = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi"


def _normalize(item: dict) -> Paper:
    doi = ""
    for ident in item.get("articleids") or []:
        if ident.get("idtype") == "doi":
            doi = ident.get("value", "")
            break
    year = None
    pubdate = item.get("pubdate", "")
    if pubdate[:4].isdigit():
        year = int(pubdate[:4])
    return Paper(
        id=f"pubmed:{item.get('uid', '')}",
        title=item.get("title") or "",
        year=year,
        authors=[a.get("name", "") for a in (item.get("authors") or [])][:25],
        journal=item.get("fulljournalname") or item.get("source") or "",
        doi=doi,
        url=f"https://pubmed.ncbi.nlm.nih.gov/{item.get('uid', '')}/",
        source="pubmed",
        source_type="journal-article",
    )


def search(query: str, limit: int = 5,
           year_from: int | None = None, year_to: int | None = None) -> list[Paper]:
    params: dict = {"db": "pubmed", "term": query, "retmode": "json",
                    "retmax": max(1, min(50, limit)), "datetype": "pdat"}
    if year_from:
        params["mindate"] = str(year_from)
    if year_to:
        params["maxdate"] = str(year_to)
    try:
        found = _http.get_json(ESEARCH, params=params)
    except _http.NotFoundError:
        return []
    ids = ((found.get("esearchresult") or {}).get("idlist")) or []
    if not ids:
        return []
    try:
        summary = _http.get_json(ESUMMARY, params={
            "db": "pubmed", "id": ",".join(ids), "retmode": "json"})
    except (_http.NotFoundError, _http.NetworkError):
        return []
    result = summary.get("result") or {}
    return [_normalize(result[uid]) for uid in result.get("uids", []) if uid in result]

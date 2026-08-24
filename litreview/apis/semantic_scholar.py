"""Semantic Scholar connector — T2, always on; the snowballing engine
(references/citations of top papers) — spec §11.2."""

from __future__ import annotations

from ..core.state import Paper
from . import _http

BASE = "https://api.semanticscholar.org/graph/v1"
_FIELDS = ("title,abstract,year,authors,venue,citationCount,externalIds,"
           "url,openAccessPdf,publicationTypes,isOpenAccess")

_TYPE_MAP = {
    "journalarticle": "journal-article",
    "conference": "proceedings-article",
    "review": "review",
    "book": "book-chapter",
    "bookSection": "book-chapter",
}


def _normalize(item: dict) -> Paper:
    external = item.get("externalIds") or {}
    pub_types = [str(t) for t in (item.get("publicationTypes") or [])]
    source_type = ""
    for t in pub_types:
        source_type = _TYPE_MAP.get(t.lower(), t.lower())
        if source_type:
            break
    oa_pdf = item.get("openAccessPdf") or {}
    return Paper(
        id=f"s2:{item.get('paperId', '')}",
        title=item.get("title") or "",
        abstract=(item.get("abstract") or "")[:2000],
        year=item.get("year"),
        authors=[a.get("name", "") for a in (item.get("authors") or [])][:25],
        journal=item.get("venue") or "",
        citation_count=item.get("citationCount") or 0,
        doi=external.get("DOI", "") or "",
        url=item.get("url") or "",
        source="semantic_scholar",
        source_type=source_type or "journal-article",
        pdf_url=oa_pdf.get("url") or "",
        is_open_access=bool(item.get("isOpenAccess")),
    )


def search(query: str, limit: int = 5,
           year_from: int | None = None, year_to: int | None = None) -> list[Paper]:
    params: dict = {"query": query, "limit": max(1, min(50, limit)), "fields": _FIELDS}
    if year_from or year_to:
        params["year"] = f"{year_from or ''}-{year_to or ''}"
    try:
        data = _http.get_json(f"{BASE}/paper/search", params=params)
    except _http.NotFoundError:
        return []
    return [_normalize(item) for item in (data.get("data") or [])]


def _related(paper_id_or_doi: str, kind: str, limit: int) -> list[Paper]:
    ident = paper_id_or_doi
    if ident.lower().startswith("10."):
        ident = f"DOI:{ident}"
    elif ident.startswith("s2:"):
        ident = ident[3:]
    inner_key = "citedPaper" if kind == "references" else "citingPaper"
    fields = ",".join(f"{inner_key}.{f}" for f in _FIELDS.split(","))
    try:
        data = _http.get_json(f"{BASE}/paper/{ident}/{kind}",
                              params={"fields": fields, "limit": limit})
    except (_http.NotFoundError, _http.NetworkError):
        return []
    papers = []
    for row in data.get("data") or []:
        inner = row.get(inner_key)
        if inner and inner.get("title"):
            papers.append(_normalize(inner))
    return papers


def references(paper: Paper, limit: int = 20) -> list[Paper]:
    return _related(paper.doi or paper.id, "references", limit)


def citations(paper: Paper, limit: int = 20) -> list[Paper]:
    return _related(paper.doi or paper.id, "citations", limit)

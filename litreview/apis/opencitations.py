"""OpenCitations connector — snowballing helper (spec §9.3e):
related DOIs for the top papers, metadata fetched through Crossref."""

from __future__ import annotations

from ..core.state import Paper
from . import _http, crossref

BASE = "https://opencitations.net/index/coci/api/v1"


def related_dois(doi: str, limit: int = 8) -> list[str]:
    dois: list[str] = []
    for kind, key in (("references", "cited"), ("citations", "citing")):
        try:
            rows = _http.get_json(f"{BASE}/{kind}/{doi}")
        except (_http.NotFoundError, _http.NetworkError):
            continue
        for row in rows or []:
            value = (row.get(key) or "").strip()
            if value and value not in dois:
                dois.append(value)
            if len(dois) >= limit:
                break
        if len(dois) >= limit:
            break
    return dois[:limit]


def snowball(papers_with_doi: list[str], cap: int = 16) -> list[Paper]:
    """DOIs of the top papers → related DOIs → Crossref metadata (spec cap 16)."""
    collected: list[Paper] = []
    for doi in papers_with_doi:
        for related in related_dois(doi, limit=cap - len(collected)):
            paper = crossref.fetch_by_doi(related)
            if paper is not None:
                paper.found_via = "snowball"
                collected.append(paper)
            if len(collected) >= cap:
                return collected
    return collected

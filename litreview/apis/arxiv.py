"""arXiv connector — T3 (preprints → EMERGING confidence), spec §11.2.
Atom XML feed parsed with the standard library."""

from __future__ import annotations

import xml.etree.ElementTree as ET

from ..core.state import Paper
from . import _http

BASE = "https://export.arxiv.org/api/query"
_NS = {"atom": "http://www.w3.org/2005/Atom",
       "arxiv": "http://arxiv.org/schemas/atom"}


def _normalize(entry: ET.Element) -> Paper:
    def text(tag: str) -> str:
        el = entry.find(f"atom:{tag}", _NS)
        return (el.text or "").strip() if el is not None and el.text else ""

    year = None
    published = text("published")
    if published[:4].isdigit():
        year = int(published[:4])
    authors = [(a.findtext("atom:name", default="", namespaces=_NS) or "").strip()
               for a in entry.findall("atom:author", _NS)]
    url = text("id")
    pdf_url = ""
    for link in entry.findall("atom:link", _NS):
        if link.get("title") == "pdf" or link.get("type") == "application/pdf":
            pdf_url = link.get("href", "")
    doi_el = entry.find("arxiv:doi", _NS)
    doi = (doi_el.text or "").strip() if doi_el is not None and doi_el.text else ""
    return Paper(
        id=f"arxiv:{url.rsplit('/', 1)[-1]}",
        title=" ".join(text("title").split()),
        abstract=" ".join(text("summary").split())[:2000],
        year=year,
        authors=[a for a in authors if a][:25],
        journal="arXiv",
        doi=doi,
        url=url,
        source="arxiv",
        tier="T3",
        source_type="preprint",
        pdf_url=pdf_url,
        is_open_access=True,
    )


def search(query: str, limit: int = 5,
           year_from: int | None = None, year_to: int | None = None) -> list[Paper]:
    params = {"search_query": f"all:{query}", "max_results": max(1, min(50, limit)),
              "sortBy": "relevance"}
    try:
        xml_text = _http.get_text(BASE, params=params)
        root = ET.fromstring(xml_text)
    except (_http.NotFoundError, _http.NetworkError, ET.ParseError):
        return []
    papers = [_normalize(e) for e in root.findall("atom:entry", _NS)]
    if year_from or year_to:
        papers = [p for p in papers
                  if p.year is None or (year_from or 0) <= p.year <= (year_to or 9999)]
    return papers

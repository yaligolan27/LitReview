"""Topical connectors — switched on by domain routing (spec §11.2):
NASA NTRS, OSTI, INSPIRE-HEP, DataCite, plus the key-gated NASA ADS and CORE.
Kept in one module: each is a thin search() over a public JSON API.
"""

from __future__ import annotations

import os

from ..core.state import Paper
from . import _http

# --- NASA NTRS -------------------------------------------------------------

_NTRS = "https://ntrs.nasa.gov/api/citations/search"


def ntrs_search(query: str, limit: int = 5,
                year_from: int | None = None, year_to: int | None = None) -> list[Paper]:
    try:
        data = _http.get_json(_NTRS, params={"q": query, "page.size": max(1, min(50, limit))})
    except _http.NotFoundError:
        return []
    papers = []
    for item in (data.get("results") or []):
        year = None
        dist_date = str(item.get("distributionDate") or item.get("publicationDate") or "")
        if dist_date[:4].isdigit():
            year = int(dist_date[:4])
        authors = []
        for aff in item.get("authorAffiliations") or []:
            name = ((aff.get("meta") or {}).get("author") or {}).get("name", "")
            if name:
                authors.append(name)
        papers.append(Paper(
            id=f"ntrs:{item.get('id', '')}",
            title=item.get("title") or "",
            abstract=(item.get("abstract") or "")[:2000],
            year=year,
            authors=authors[:25],
            journal="NASA NTRS",
            url=f"https://ntrs.nasa.gov/citations/{item.get('id', '')}",
            source="nasa_ntrs",
            source_type="report",
        ))
    if year_from or year_to:
        papers = [p for p in papers
                  if p.year is None or (year_from or 0) <= p.year <= (year_to or 9999)]
    return papers


# --- OSTI (US Dept. of Energy) --------------------------------------------

_OSTI = "https://www.osti.gov/api/v1/records"


def osti_search(query: str, limit: int = 5,
                year_from: int | None = None, year_to: int | None = None) -> list[Paper]:
    params: dict = {"q": query, "rows": max(1, min(50, limit))}
    if year_from:
        params["publication_date_start"] = f"01/01/{year_from}"
    if year_to:
        params["publication_date_end"] = f"12/31/{year_to}"
    try:
        data = _http.get_json(_OSTI, params=params)
    except _http.NotFoundError:
        return []
    records = data if isinstance(data, list) else (data.get("records") or [])
    papers = []
    for item in records:
        year = None
        pub_date = str(item.get("publication_date") or "")
        for token in pub_date.replace("-", "/").split("/"):
            if token[:4].isdigit() and len(token) >= 4:
                year = int(token[:4])
                break
        papers.append(Paper(
            id=f"osti:{item.get('osti_id', '')}",
            title=item.get("title") or "",
            abstract=(item.get("description") or "")[:2000],
            year=year,
            authors=[a for a in (item.get("authors") or []) if isinstance(a, str)][:25],
            journal=item.get("journal_name") or "OSTI",
            doi=item.get("doi", "") or "",
            url=item.get("links", [{}])[0].get("href", "") if item.get("links") else "",
            source="osti",
            source_type="report" if "report" in str(item.get("product_type", "")).lower()
            else "journal-article",
        ))
    return papers


# --- INSPIRE-HEP -----------------------------------------------------------

_INSPIRE = "https://inspirehep.net/api/literature"


def inspire_search(query: str, limit: int = 5,
                   year_from: int | None = None, year_to: int | None = None) -> list[Paper]:
    q = query
    if year_from or year_to:
        q += f" and date {year_from or 1900}->{year_to or 2100}"
    try:
        data = _http.get_json(_INSPIRE, params={"q": q, "size": max(1, min(50, limit))})
    except _http.NotFoundError:
        return []
    papers = []
    for hit in ((data.get("hits") or {}).get("hits")) or []:
        meta = hit.get("metadata") or {}
        titles = meta.get("titles") or [{}]
        abstracts = meta.get("abstracts") or [{}]
        dois = meta.get("dois") or []
        year = None
        earliest = str(meta.get("earliest_date", ""))
        if earliest[:4].isdigit():
            year = int(earliest[:4])
        papers.append(Paper(
            id=f"inspire:{hit.get('id', '')}",
            title=titles[0].get("title", ""),
            abstract=(abstracts[0].get("value") or "")[:2000],
            year=year,
            authors=[a.get("full_name", "") for a in (meta.get("authors") or [])][:25],
            journal="INSPIRE-HEP",
            citation_count=meta.get("citation_count") or 0,
            doi=dois[0].get("value", "") if dois else "",
            url=f"https://inspirehep.net/literature/{hit.get('id', '')}",
            source="inspire_hep",
            source_type="journal-article",
        ))
    return papers


# --- DataCite --------------------------------------------------------------

_DATACITE = "https://api.datacite.org/dois"


def datacite_search(query: str, limit: int = 5,
                    year_from: int | None = None, year_to: int | None = None) -> list[Paper]:
    try:
        data = _http.get_json(_DATACITE, params={"query": query,
                                                 "page[size]": max(1, min(50, limit))})
    except _http.NotFoundError:
        return []
    papers = []
    for item in (data.get("data") or []):
        attr = item.get("attributes") or {}
        titles = attr.get("titles") or [{}]
        year = attr.get("publicationYear")
        papers.append(Paper(
            id=f"datacite:{attr.get('doi', '')}",
            title=titles[0].get("title", ""),
            year=year if isinstance(year, int) else None,
            authors=[c.get("name", "") for c in (attr.get("creators") or [])][:25],
            journal=attr.get("publisher") or "DataCite",
            citation_count=attr.get("citationCount") or 0,
            doi=attr.get("doi", "") or "",
            url=attr.get("url") or "",
            source="datacite",
            source_type=str(((attr.get("types") or {}).get("resourceTypeGeneral") or "dataset")).lower(),
        ))
    if year_from or year_to:
        papers = [p for p in papers
                  if p.year is None or (year_from or 0) <= p.year <= (year_to or 9999)]
    return papers


# --- NASA ADS (key required) ----------------------------------------------


def ads_available() -> bool:
    return bool(os.environ.get("ADS_API_TOKEN"))


def ads_search(query: str, limit: int = 5,
               year_from: int | None = None, year_to: int | None = None) -> list[Paper]:
    token = os.environ.get("ADS_API_TOKEN")
    if not token:
        return []
    q = query
    if year_from or year_to:
        q += f" year:{year_from or 1900}-{year_to or 2100}"
    try:
        data = _http.get_json(
            "https://api.adsabs.harvard.edu/v1/search/query",
            params={"q": q, "rows": max(1, min(50, limit)),
                    "fl": "title,abstract,year,author,bibcode,doi,citation_count,pub"},
            headers={"Authorization": f"Bearer {token}"})
    except _http.NotFoundError:
        return []
    papers = []
    for doc in ((data.get("response") or {}).get("docs")) or []:
        titles = doc.get("title") or [""]
        dois = doc.get("doi") or []
        papers.append(Paper(
            id=f"ads:{doc.get('bibcode', '')}",
            title=titles[0],
            abstract=(doc.get("abstract") or "")[:2000],
            year=int(doc["year"]) if str(doc.get("year", "")).isdigit() else None,
            authors=(doc.get("author") or [])[:25],
            journal=doc.get("pub") or "",
            citation_count=doc.get("citation_count") or 0,
            doi=dois[0] if dois else "",
            url=f"https://ui.adsabs.harvard.edu/abs/{doc.get('bibcode', '')}",
            source="nasa_ads",
            source_type="journal-article",
        ))
    return papers


# --- CORE (key required) ---------------------------------------------------


def core_available() -> bool:
    return bool(os.environ.get("CORE_API_KEY"))


def core_search(query: str, limit: int = 5,
                year_from: int | None = None, year_to: int | None = None) -> list[Paper]:
    key = os.environ.get("CORE_API_KEY")
    if not key:
        return []
    try:
        data = _http.get_json("https://api.core.ac.uk/v3/search/works",
                              params={"q": query, "limit": max(1, min(50, limit))},
                              headers={"Authorization": f"Bearer {key}"})
    except _http.NotFoundError:
        return []
    papers = []
    for item in (data.get("results") or []):
        year = item.get("yearPublished")
        papers.append(Paper(
            id=f"core:{item.get('id', '')}",
            title=item.get("title") or "",
            abstract=(item.get("abstract") or "")[:2000],
            year=year if isinstance(year, int) else None,
            authors=[a.get("name", "") for a in (item.get("authors") or [])][:25],
            journal=(item.get("publisher") or ""),
            doi=item.get("doi", "") or "",
            url=item.get("downloadUrl") or "",
            source="core",
            source_type="journal-article",
            is_open_access=True,
        ))
    if year_from or year_to:
        papers = [p for p in papers
                  if p.year is None or (year_from or 0) <= p.year <= (year_to or 9999)]
    return papers

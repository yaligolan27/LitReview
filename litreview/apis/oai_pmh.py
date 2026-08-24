"""Generic OAI-PMH harvester — Part-E wave 3 (spec §23).

One connector opens hundreds of repositories: given an endpoint and (optionally)
a set, it harvests Dublin Core records and adapts them to the same ``search()``
signature every provider uses. OAI-PMH is harvest-oriented (no real keyword
query), so ``search`` harvests a bounded, date-filtered page and filters
client-side by the query terms — deliberately conservative.

Trust: a repository reached this way is NOT authoritative by default. The
Source Scout registers it at **T2 at most** (never T1); ``registry.tier_for``
already defaults unknown sources to T2, and we never override that upward.
"""

from __future__ import annotations

import re
from xml.etree import ElementTree as ET

from ..core.state import Paper
from . import _http

_DEFAULT_PREFIX = "oai_dc"


def _local(tag: str) -> str:
    """Strip the XML namespace: '{http://...}title' → 'title'."""
    return tag.rsplit("}", 1)[-1]


def _text_children(dc_el) -> dict[str, list[str]]:
    """Collect Dublin Core fields (title/creator/date/identifier/…) by local
    name, tolerating any namespace prefix the repository uses."""
    fields: dict[str, list[str]] = {}
    for child in dc_el:
        name = _local(child.tag)
        value = (child.text or "").strip()
        if value:
            fields.setdefault(name, []).append(value)
    return fields


def _year(dates: list[str]) -> int | None:
    for d in dates:
        m = re.search(r"(19|20)\d{2}", d)
        if m:
            return int(m.group(0))
    return None


def _pick_doi_and_url(identifiers: list[str]) -> tuple[str, str]:
    doi = ""
    url = ""
    for ident in identifiers:
        low = ident.lower()
        if not doi and ("doi.org/" in low or low.startswith("10.")):
            doi = ident.split("doi.org/")[-1]
        if not url and low.startswith("http"):
            url = ident
    return doi, url


def parse_oai_dc(xml_text: str, source: str = "oai_pmh") -> list[Paper]:
    """Parse an OAI-PMH ListRecords/oai_dc response into Papers. Pure function
    (no network) — the unit-test seam. Deleted records and empty titles are
    skipped; a malformed document yields an empty list, never an exception."""
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return []
    papers: list[Paper] = []
    for record in root.iter():
        if _local(record.tag) != "record":
            continue
        header = next((c for c in record if _local(c.tag) == "header"), None)
        if header is not None and (header.get("status") or "").lower() == "deleted":
            continue
        dc_el = None
        for meta in record:
            if _local(meta.tag) != "metadata":
                continue
            for candidate in meta.iter():
                if _local(candidate.tag) == "dc":
                    dc_el = candidate
                    break
        if dc_el is None:
            continue
        fields = _text_children(dc_el)
        title = " ".join(fields.get("title", [])).strip()
        if not title:
            continue
        doi, url = _pick_doi_and_url(fields.get("identifier", []))
        papers.append(Paper(
            id=f"{source}:{(fields.get('identifier') or [title])[0][:120]}",
            title=title,
            abstract=" ".join(fields.get("description", []))[:2000],
            year=_year(fields.get("date", [])),
            authors=[a for a in fields.get("creator", [])][:25],
            journal=" ".join(fields.get("publisher", [])).strip(),
            doi=doi,
            url=url,
            source=source,
            source_type=(fields.get("type", [""])[0] or "").lower(),
            language=(fields.get("language", [""])[0] or "").split("-")[0].lower(),
        ))
    return papers


def _matches(paper: Paper, terms: list[str]) -> bool:
    if not terms:
        return True
    hay = f"{paper.title} {paper.abstract}".lower()
    return any(t in hay for t in terms)


def harvest(endpoint: str, *, set_spec: str = "", year_from: int | None = None,
            year_to: int | None = None, source: str = "oai_pmh",
            metadata_prefix: str = _DEFAULT_PREFIX) -> list[Paper]:
    params = {"verb": "ListRecords", "metadataPrefix": metadata_prefix}
    if set_spec:
        params["set"] = set_spec
    if year_from:
        params["from"] = f"{year_from}-01-01"
    if year_to:
        params["until"] = f"{year_to}-12-31"
    try:
        xml_text = _http.get_text(endpoint, params=params)
    except (_http.NotFoundError, _http.NetworkError):
        return []   # a harvest failure is "no results", handled like any provider
    return parse_oai_dc(xml_text, source=source)


def make_provider(name: str, endpoint: str, *, set_spec: str = "",
                  metadata_prefix: str = _DEFAULT_PREFIX):
    """Bind an endpoint into the standard provider signature so the registry
    and the Source Hunter can call it exactly like any built-in database."""

    def search(query: str, limit: int = 5,
               year_from: int | None = None, year_to: int | None = None) -> list[Paper]:
        papers = harvest(endpoint, set_spec=set_spec, year_from=year_from,
                         year_to=year_to, source=name, metadata_prefix=metadata_prefix)
        terms = [t.lower() for t in re.findall(r"[\w]{3,}", query or "")]
        filtered = [p for p in papers if _matches(p, terms)]
        return filtered[:max(1, limit)]

    return search

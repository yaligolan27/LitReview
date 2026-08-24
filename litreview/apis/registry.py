"""Provider registry + routing — spec §9.3b / §11.2 (apis/registry.py).

M1 scope: the universal core (OpenAlex, Crossref; Semantic Scholar and DOAJ
land in M2) plus the offline mock provider. Domain-profile routing, shutdown
rules and the safety net are M2 — the structures are already here so the
hunter's interface will not change.
"""

from __future__ import annotations

from typing import Callable, Protocol

from ..config import Settings
from ..core.state import Paper
from . import crossref, mock_source, openalex


class SearchFn(Protocol):
    def __call__(self, query: str, limit: int = ...,
                 year_from: int | None = ..., year_to: int | None = ...) -> list[Paper]: ...


# Default source tiers — spec §11.2.
SOURCE_TIER: dict[str, str] = {
    "openalex": "T1", "crossref": "T1", "doaj": "T1", "pubmed": "T1",
    "europepmc": "T1", "dblp": "T1", "nasa_ntrs": "T1", "osti": "T1",
    "inspire_hep": "T1", "datacite": "T1", "nasa_ads": "T1",
    "semantic_scholar": "T2", "core": "T2",
    "arxiv": "T3",
    "mockdb": "T1",
}

# These are never switched off by domain routing (spec §9.3b).
UNIVERSAL_CORE = {"openalex", "crossref", "semantic_scholar", "doaj"}

PROVIDERS: dict[str, SearchFn] = {
    "openalex": openalex.search,
    "crossref": crossref.search,
    "mockdb": mock_source.search,
}


def implemented_sources() -> list[str]:
    return [name for name in PROVIDERS if name != "mockdb"]


def active_sources(settings: Settings, offline: bool = False) -> list[str]:
    """Which providers to query. M1: universal core ∩ implemented, with the
    SURVEY_SOURCES override honored; mock mode is fully offline."""
    if offline:
        return ["mockdb"]
    override = settings.sources_override
    if override:
        if len(override) == 1 and override[0].lower() == "all":
            return implemented_sources()
        return [s for s in override if s in PROVIDERS and s != "mockdb"]
    return [s for s in implemented_sources() if s in UNIVERSAL_CORE]


def get_search(name: str) -> Callable:
    return PROVIDERS[name]


def tier_for(source: str) -> str:
    return SOURCE_TIER.get(source, "T2")

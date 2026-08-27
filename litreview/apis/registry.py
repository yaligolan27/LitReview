"""Provider registry + domain routing — spec §9.3b / §11.2 (apis/registry.py).

Routing model:

* Eight databases are on by default (the ✅ column of spec §11.2); four
  topical ones (NTRS, OSTI, INSPIRE-HEP, DataCite) switch on when their
  domain is detected; NASA ADS and CORE additionally require API keys.
* Nine domain profiles carry keywords / core sources / avoid lists.
  Keyword syntax (spec §9.3b): ``rocket*`` = token-prefix match,
  ``"launch vehicle"`` (contains a space) = substring match, ``radar`` =
  exact token; Hebrew keywords are exact tokens.
* Dual classification: keyword scores + LLM domains (auto-certain, score 2).
* A domain may switch a source OFF only under three guards: it scored ≥2 or
  was LLM-classified; the source is not in the core of another detected
  domain; the source is not in UNIVERSAL_CORE. Safety net: fewer than 4
  active sources cancels all shutdowns.
* Deliberate overlap: ``psycholog*`` sits in both biomed and social_econ so
  hybrid topics keep both domains' databases (spec §9.3b).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Callable, Protocol

from ..config import Settings
from ..core.state import Paper
from . import arxiv as arxiv_api
from . import crossref, dblp, doaj, europepmc, mock_source, openalex, pubmed
from . import semantic_scholar, topical


class SearchFn(Protocol):
    def __call__(self, query: str, limit: int = ...,
                 year_from: int | None = ..., year_to: int | None = ...) -> list[Paper]: ...


SOURCE_TIER: dict[str, str] = {
    "openalex": "T1", "crossref": "T1", "doaj": "T1", "pubmed": "T1",
    "europepmc": "T1", "dblp": "T1", "nasa_ntrs": "T1", "osti": "T1",
    "inspire_hep": "T1", "datacite": "T1", "nasa_ads": "T1",
    "semantic_scholar": "T2", "core": "T2",
    "arxiv": "T3",
    "mockdb": "T1",
}

# Never switched off by routing (spec §9.3b).
UNIVERSAL_CORE = {"openalex", "crossref", "semantic_scholar", "doaj"}

# On by default (spec §11.2 ✅ column).
DEFAULT_ON = {"openalex", "crossref", "semantic_scholar", "doaj",
              "pubmed", "europepmc", "dblp", "arxiv"}

PROVIDERS: dict[str, SearchFn] = {
    "openalex": openalex.search,
    "crossref": crossref.search,
    "semantic_scholar": semantic_scholar.search,
    "doaj": doaj.search,
    "pubmed": pubmed.search,
    "europepmc": europepmc.search,
    "dblp": dblp.search,
    "arxiv": arxiv_api.search,
    "nasa_ntrs": topical.ntrs_search,
    "osti": topical.osti_search,
    "inspire_hep": topical.inspire_search,
    "datacite": topical.datacite_search,
    "nasa_ads": topical.ads_search,
    "core": topical.core_search,
    "mockdb": mock_source.search,
}


@dataclass(frozen=True)
class DomainProfile:
    keywords: tuple[str, ...]
    core: tuple[str, ...] = ()
    avoid: tuple[str, ...] = ()


DOMAIN_PROFILES: dict[str, DomainProfile] = {
    "aerospace": DomainProfile(
        keywords=("rocket*", "spacecraft", "satellite*", "propulsion", "aerodynamic*",
                  "orbit*", "launch vehicle", "avionics", "uav", "drone*",
                  "space station", "nozzle*", "חלל", "לוויין", "טילים", 'כטב"ם'),
        core=("nasa_ntrs", "osti", "nasa_ads", "arxiv"),
        avoid=("pubmed", "europepmc", "dblp")),
    "physics_astro": DomainProfile(
        keywords=("quantum", "photon*", "plasma", "high energy", "astrophys*",
                  "cosmolog*", "particle physics", "boson", "dark matter",
                  "gravitational", "פיזיקה"),
        core=("inspire_hep", "osti", "nasa_ads", "arxiv"),
        avoid=("pubmed", "europepmc", "dblp")),
    "biomed": DomainProfile(
        keywords=("clinical", "patient*", "disease*", "therap*", "immun*", "cancer",
                  "tumor", "drug*", "vaccine*", "diabet*", "cardio*", "neuro*",
                  "psycholog*", "clinical trial", "רפואה", "מחלה", "תרופה", "חיסון"),
        core=("pubmed", "europepmc"),
        avoid=("dblp", "arxiv")),
    "cs_ai": DomainProfile(
        keywords=("algorithm*", "machine learning", "deep learning", "neural network",
                  "software", "computer vision", "language model", "database*",
                  "cybersecurity", "artificial intelligence", "llm", "בינה",
                  "תוכנה", "אלגוריתם"),
        core=("dblp", "arxiv"),
        avoid=("pubmed", "europepmc")),
    "energy_materials": DomainProfile(
        keywords=("battery*", "photovoltaic*", "solar cell", "energy storage",
                  "nuclear", "fuel cell", "alloy*", "composite*", "semiconductor*",
                  "אנרגיה", "סוללה"),
        core=("osti",),
        avoid=("dblp",)),
    "chemistry": DomainProfile(
        keywords=("chemical*", "catalys*", "molecule*", "synthesis", "organic",
                  "polymer*", "spectroscop*", "כימיה"),
        core=("osti",),
        avoid=("dblp",)),
    "earth_env": DomainProfile(
        keywords=("climate", "environment*", "geolog*", "ocean*", "atmospher*",
                  "ecosystem*", "biodiversity", "hydrolog*", "סביבה", "אקלים"),
        core=("osti",),
        avoid=("dblp",)),
    "social_econ": DomainProfile(
        keywords=("econom*", "social", "education*", "policy", "management",
                  "human resources", "market*", "psycholog*", "sociolog*",
                  "חינוך", "כלכלה", "חברה", "משאבי אנוש"),
        core=(),
        avoid=("pubmed", "dblp")),
    "defense_security": DomainProfile(
        keywords=("defense", "military", "weapon*", "radar", "missile*",
                  "national security", "ballistic*", "surveillance",
                  "ביטחון", "צבאי", "טילים", 'כטב"ם'),
        core=("nasa_ntrs", "osti"),
        avoid=("pubmed", "europepmc")),
}

CERTAIN_SCORE = 2

# --- Part-E wave 4: language routing (spec §24) ----------------------------
# Language name (any casing / English or native) → ISO 639-1 code.
LANGUAGE_ISO: dict[str, str] = {
    "english": "en", "en": "en",
    "hebrew": "he", "he": "he", "עברית": "he",
    "spanish": "es", "es": "es", "español": "es",
    "portuguese": "pt", "pt": "pt", "português": "pt",
    "french": "fr", "fr": "fr", "français": "fr",
    "german": "de", "de": "de", "deutsch": "de",
    "italian": "it", "it": "it",
    "japanese": "ja", "ja": "ja", "日本語": "ja",
    "chinese": "zh", "zh": "zh", "中文": "zh",
    "russian": "ru", "ru": "ru",
    "arabic": "ar", "ar": "ar", "العربية": "ar",
}

# ISO code → specialized databases worth trying for that language, beyond the
# universal OpenAlex ``language:`` channel. Names are for transparency and for
# the Source Scout / allowlist to resolve (OAI-PMH or connector); the always-on
# executable channel is OpenAlex language filtering.
LANGUAGE_DB_ROUTING: dict[str, list[str]] = {
    "es": ["scielo", "redalyc"],
    "pt": ["scielo"],
    "fr": ["hal"],
    "ja": ["j-stage"],
    "zh": ["cnki"],
    "de": ["core"],
}


def iso_code(language: str) -> str:
    return LANGUAGE_ISO.get((language or "").strip().lower(), "")


def language_channels(iso: str) -> list[str]:
    """Specialized DBs suggested for an ISO language (transparency/scout)."""
    return LANGUAGE_DB_ROUTING.get(iso, [])


def _tokens(text: str) -> list[str]:
    return re.findall(r"[\w\"׳״']+", text.lower(), flags=re.UNICODE)


_HEBREW = re.compile(r"[א-ת]")


def _token_matches(kw: str, token_set: set[str]) -> bool:
    if kw in token_set:
        return True
    if _HEBREW.search(kw):
        # Hebrew prefixes (ו/ה/ב/ל/מ/ש and combinations) attach to the word:
        # "וביטחון" must match the keyword "ביטחון".
        return any(tok.endswith(kw) and 0 < len(tok) - len(kw) <= 2
                   for tok in token_set)
    return False


def classify_topic(text: str) -> dict[str, int]:
    """Keyword classification → {domain: score} (only scored domains)."""
    lowered = text.lower()
    token_set = set(_tokens(text))
    scores: dict[str, int] = {}
    for domain, profile in DOMAIN_PROFILES.items():
        score = 0
        for keyword in profile.keywords:
            kw = keyword.lower()
            if kw.endswith("*"):
                stem = kw[:-1]
                if any(tok.startswith(stem) for tok in token_set):
                    score += 1
            elif " " in kw:
                if kw in lowered:
                    score += 1
            else:
                if _token_matches(kw, token_set):
                    score += 1
        if score:
            scores[domain] = score
    return scores


def _keyed_available(name: str) -> bool:
    if name == "nasa_ads":
        return topical.ads_available()
    if name == "core":
        return topical.core_available()
    return True


@dataclass
class RoutingResult:
    active: list[str] = field(default_factory=list)
    domains: dict[str, int] = field(default_factory=dict)
    llm_domains: list[str] = field(default_factory=list)
    certain_domains: list[str] = field(default_factory=list)
    core_added: list[str] = field(default_factory=list)
    dropped: list[str] = field(default_factory=list)
    override: str = ""
    safety_net_triggered: bool = False


def route(settings: Settings, topic_text: str,
          llm_domains: list[str] | None = None,
          offline: bool = False) -> RoutingResult:
    result = RoutingResult(llm_domains=list(llm_domains or []))

    if offline:
        result.active = ["mockdb"]
        result.domains = classify_topic(topic_text)
        result.override = "offline-mock"
        return result

    if settings.sources_override:
        names = settings.sources_override
        if len(names) == 1 and names[0].lower() == "all":
            result.active = [n for n in PROVIDERS if n != "mockdb" and _keyed_available(n)]
        else:
            result.active = [n for n in names if n in PROVIDERS and n != "mockdb"]
        result.override = "SURVEY_SOURCES"
        return result

    scores = classify_topic(topic_text)
    if settings.domains_override:
        forced = [d for d in settings.domains_override if d in DOMAIN_PROFILES]
        scores = {d: max(scores.get(d, 0), CERTAIN_SCORE) for d in forced} or scores
        result.override = "SURVEY_DOMAINS"
    result.domains = scores

    certain = {d for d, s in scores.items() if s >= CERTAIN_SCORE}
    certain |= {d for d in result.llm_domains if d in DOMAIN_PROFILES}
    result.certain_domains = sorted(certain)

    active = {name for name in DEFAULT_ON if _keyed_available(name)}
    for domain in certain:
        for src in DOMAIN_PROFILES[domain].core:
            if src in PROVIDERS and _keyed_available(src) and src not in active:
                active.add(src)
                result.core_added.append(src)

    # Shutdowns under the three guards.
    needed_by_other = set()
    for domain in certain:
        for other in certain:
            if other != domain:
                needed_by_other |= set(DOMAIN_PROFILES[other].core)
    dropped: list[str] = []
    for domain in certain:
        for src in DOMAIN_PROFILES[domain].avoid:
            if src in active and src not in UNIVERSAL_CORE and src not in needed_by_other:
                active.discard(src)
                dropped.append(src)

    # Safety net (spec §9.3b): fewer than 4 sources cancels every shutdown.
    if len(active) < 4:
        for src in dropped:
            active.add(src)
        result.safety_net_triggered = True
        dropped = []

    result.dropped = sorted(set(dropped))
    result.active = sorted(active)
    return result


def implemented_sources() -> list[str]:
    return [name for name in PROVIDERS if name != "mockdb"]


def active_sources(settings: Settings, offline: bool = False) -> list[str]:
    """Backward-compatible simple listing (used before routing runs)."""
    return route(settings, "", offline=offline).active


def get_search(name: str) -> Callable:
    return PROVIDERS[name]


def tier_for(source: str) -> str:
    return SOURCE_TIER.get(source, "T2")


def register_provider(name: str, search_fn: Callable, tier: str = "T2") -> str:
    """Register a provider discovered at runtime by the Source Scout
    (Part-E wave 3). The tier is CLAMPED to T2/T3 — a scouted source is never
    promoted to T1, whatever the caller passes (spec §23)."""
    PROVIDERS[name] = search_fn
    SOURCE_TIER[name] = tier if tier in ("T2", "T3") else "T2"
    return name

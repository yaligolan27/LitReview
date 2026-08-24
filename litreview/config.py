"""Central configuration: every SURVEY_* environment flag, typed, in one place.

Spec reference: §14 ("כל דגלי הסביבה"). Divergences from the original tool are
deliberate and documented inline:

* ``SURVEY_REFINE_ROUNDS`` is a real counter (0 disables). The original
  ``SURVEY_REFINE_ROUND`` was accidentally boolean — the value 2 disabled the
  round (spec §16). The legacy name is still read for compatibility: truthy
  legacy values map to 1, falsy to 0.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field, fields

_TRUTHY = {"1", "true", "yes", "on"}
_FALSY = {"0", "false", "no", "off", ""}


def _bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in _TRUTHY


def _int(name: str, default: int, lo: int | None = None, hi: int | None = None) -> int:
    raw = os.environ.get(name)
    try:
        val = int(raw) if raw is not None and raw.strip() != "" else default
    except ValueError:
        val = default
    if lo is not None:
        val = max(lo, val)
    if hi is not None:
        val = min(hi, val)
    return val


def _float(name: str, default: float) -> float:
    raw = os.environ.get(name)
    try:
        return float(raw) if raw is not None and raw.strip() != "" else default
    except ValueError:
        return default


def _str(name: str, default: str) -> str:
    raw = os.environ.get(name)
    return default if raw is None or raw.strip() == "" else raw.strip()


def _csv(name: str) -> tuple[str, ...]:
    raw = os.environ.get(name, "")
    return tuple(part.strip() for part in raw.split(",") if part.strip())


def _refine_rounds() -> int:
    # New counter flag wins. The legacy flag is honored by what users MEANT:
    # a numeric value is a round count (the original treated 2 as falsy and
    # silently disabled the round — spec §16), otherwise truthy→1 / falsy→0.
    if os.environ.get("SURVEY_REFINE_ROUNDS") is not None:
        return _int("SURVEY_REFINE_ROUNDS", 1, lo=0, hi=5)
    legacy = os.environ.get("SURVEY_REFINE_ROUND")
    if legacy is None:
        return 1
    legacy = legacy.strip().lower()
    if legacy.isdigit():
        return max(0, min(5, int(legacy)))
    return 1 if legacy in _TRUTHY else 0


@dataclass(frozen=True)
class Settings:
    # --- LLM / run ---
    llm_backend: str = "native"          # native | mock | api | auto
    bridge_dir: str = ".llm_bridge"
    bridge_timeout: float = 900.0
    bridge_poll: float = 1.5
    api_model: str = "claude-opus-5"
    api_max_retries: int = 3

    # --- search & retrieval ---
    max_queries: int = 14
    limit_per_source: int = 5
    enable_snowball: bool = True
    dedup_threshold: int = 92
    refine_rounds: int = 1               # counter; 0 disables (bug fix vs. original)
    sources_override: tuple[str, ...] = ()   # SURVEY_SOURCES: "all" or names
    domains_override: tuple[str, ...] = ()   # SURVEY_DOMAINS
    llm_domain: bool = True
    llm_query_expansion: bool = False
    parallel_search: int = 4             # worker threads for provider fan-out (improvement)

    # --- verification ---
    doi_backfill: bool = True
    doi_backfill_cap: int = 80
    verify_dois: bool = False
    verify_doi_cap: int = 20
    retraction_crossref: bool = True
    retraction_crossref_cap: int = 60
    enable_fulltext: bool = True
    fulltext_max_papers: int = 6

    # --- deep research ---
    deep_research: bool = True
    dr_rounds: int = 3                   # 1-6
    dr_max_findings: int = 24            # 4-60
    dr_verify: bool = True
    dr_verify_cap: int = 6               # 1-12
    dr_entities: str = "auto"            # auto | 1 | 0
    web_landscape: bool = False
    web_landscape_max: int = 8

    # --- writing & quality ---
    max_claims: int = 12
    max_fix_rounds: int = 2
    score_threshold: int = 60
    output_language: str = "he"          # improvement: configurable output language

    # --- gates (CLI behaviour; the web server supplies its own policy) ---
    gate_sources: str = "auto"           # auto | bridge
    gate_draft: str = "auto"             # auto | bridge

    # --- network ---
    contact_email: str = "literature-survey-system@users.noreply.github.com"
    http_cache: bool = True
    http_cache_dir: str = ".http_cache"
    http_cache_ttl: int = 604_800
    http_retries: int = 3
    http_timeout: float = 15.0

    # --- Part-E wave 1 (spec §22) ---
    formula_lint: bool = True        # mathtext parsing of [FORMULA] blocks
    plain_boxes: bool = True         # chapters open with a "בפשטות" box
    glossary: bool = True            # auto glossary + reader guide

    # --- Part-E wave 2 (spec §21, §24) — all default OFF (opt-in) ---
    reliability_signals: bool = False    # enrich cited papers with 9 trust signals
    signals_cap: int = 40                # max cited papers to enrich (cost bound)
    dr_depth: str = "standard"           # standard | deep (primary-source chase, per-SQ saturation)

    # --- Part-E wave 3 (spec §23, §24) — default OFF / standard ---
    source_scout: bool = False           # discover authoritative DBs on a real coverage gap
    depth: str = "standard"              # standard | practical ([EXAMPLE] worked examples)

    # --- optional subsystems ---
    semantic_retrieval: bool = False
    semantic_download: bool = False
    semantic_model: str = "all-MiniLM-L6-v2"
    low_reliability_web: bool = False

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            llm_backend=_str("SURVEY_LLM_BACKEND", "native").lower(),
            bridge_dir=_str("SURVEY_BRIDGE_DIR", ".llm_bridge"),
            bridge_timeout=_float("SURVEY_BRIDGE_TIMEOUT", 900.0),
            bridge_poll=_float("BRIDGE_POLL", 1.5),
            api_model=_str("SURVEY_API_MODEL", "claude-opus-5"),
            api_max_retries=_int("SURVEY_API_MAX_RETRIES", 3, lo=0, hi=10),
            max_queries=_int("SURVEY_MAX_QUERIES", 14, lo=1),
            limit_per_source=_int("SURVEY_LIMIT_PER_SOURCE", 5, lo=1),
            enable_snowball=_bool("SURVEY_ENABLE_SNOWBALL", True),
            dedup_threshold=_int("SURVEY_DEDUP_THRESHOLD", 92, lo=50, hi=100),
            refine_rounds=_refine_rounds(),
            sources_override=_csv("SURVEY_SOURCES"),
            domains_override=_csv("SURVEY_DOMAINS"),
            llm_domain=_bool("SURVEY_LLM_DOMAIN", True),
            llm_query_expansion=_bool("SURVEY_LLM_QUERY_EXPANSION", False),
            parallel_search=_int("SURVEY_PARALLEL_SEARCH", 4, lo=1, hi=16),
            doi_backfill=_bool("SURVEY_DOI_BACKFILL", True),
            doi_backfill_cap=_int("SURVEY_DOI_BACKFILL_CAP", 80, lo=0),
            verify_dois=_bool("SURVEY_VERIFY_DOIS", False),
            verify_doi_cap=_int("SURVEY_VERIFY_DOI_CAP", 20, lo=0),
            retraction_crossref=_bool("SURVEY_RETRACTION_CROSSREF", True),
            retraction_crossref_cap=_int("SURVEY_RETRACTION_CROSSREF_CAP", 60, lo=0),
            enable_fulltext=_bool("SURVEY_ENABLE_FULLTEXT", True),
            fulltext_max_papers=_int("SURVEY_FULLTEXT_MAX_PAPERS", 6, lo=0),
            deep_research=_bool("SURVEY_DEEP_RESEARCH", True),
            dr_rounds=_int("SURVEY_DR_ROUNDS", 3, lo=1, hi=6),
            dr_max_findings=_int("SURVEY_DR_MAX_FINDINGS", 24, lo=4, hi=60),
            dr_verify=_bool("SURVEY_DR_VERIFY", True),
            dr_verify_cap=_int("SURVEY_DR_VERIFY_CAP", 6, lo=1, hi=12),
            dr_entities=_str("SURVEY_DR_ENTITIES", "auto").lower(),
            web_landscape=_bool("SURVEY_WEB_LANDSCAPE", False),
            web_landscape_max=_int("SURVEY_WEB_LANDSCAPE_MAX", 8, lo=1),
            max_claims=_int("SURVEY_MAX_CLAIMS", 12, lo=1),
            max_fix_rounds=_int("SURVEY_MAX_FIX_ROUNDS", 2, lo=0),
            score_threshold=_int("SURVEY_SCORE_THRESHOLD", 60, lo=0, hi=100),
            output_language=_str("SURVEY_OUTPUT_LANG", "he").lower(),
            gate_sources=_str("SURVEY_GATE_SOURCES", "auto").lower(),
            gate_draft=_str("SURVEY_GATE_DRAFT", "auto").lower(),
            contact_email=_str(
                "SURVEY_CONTACT_EMAIL",
                "literature-survey-system@users.noreply.github.com",
            ),
            http_cache=_bool("SURVEY_HTTP_CACHE", True),
            http_cache_dir=_str("SURVEY_HTTP_CACHE_DIR", ".http_cache"),
            http_cache_ttl=_int("SURVEY_HTTP_CACHE_TTL", 604_800, lo=0),
            http_retries=_int("SURVEY_HTTP_RETRIES", 3, lo=0, hi=10),
            http_timeout=_float("SURVEY_HTTP_TIMEOUT", 15.0),
            formula_lint=_bool("SURVEY_FORMULA_LINT", True),
            plain_boxes=_bool("SURVEY_PLAIN_BOXES", True),
            glossary=_bool("SURVEY_GLOSSARY", True),
            reliability_signals=_bool("SURVEY_RELIABILITY_SIGNALS", False),
            signals_cap=_int("SURVEY_SIGNALS_CAP", 40, lo=0),
            dr_depth=_str("SURVEY_DR_DEPTH", "standard").lower(),
            source_scout=_bool("SURVEY_SOURCE_SCOUT", False),
            depth=_str("SURVEY_DEPTH", "standard").lower(),
            semantic_retrieval=_bool("ENABLE_SEMANTIC_RETRIEVAL", False),
            semantic_download=_bool("ENABLE_SEMANTIC_DOWNLOAD", False),
            semantic_model=_str("SEMANTIC_MODEL", "all-MiniLM-L6-v2"),
            low_reliability_web=_bool("ENABLE_LOW_RELIABILITY_WEB", False),
        )


_settings: Settings | None = None


def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = Settings.from_env()
    return _settings


def reset_settings() -> None:
    """Force re-reading the environment (tests, or per-run overrides)."""
    global _settings
    _settings = None

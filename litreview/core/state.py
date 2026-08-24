"""The shared data model — spec §8, plus the web-layer fields this project adds.

One ``SurveyState`` object travels through the whole pipeline. Agents read
from it and write to it; there is no messaging between agents. The full state
serializes to a single JSON document (``to_dict``/``from_dict``), which is
what checkpointing and the web server persist.

Identity note: papers assigned to a section (``SurveySection.papers``) are the
*same objects* as entries in ``SurveyState.papers`` — the citation manager
relies on that. Serialization stores full paper dicts in both places and
re-unifies identity by paper id on load.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any

CONFIDENCE_LEVELS = ("HIGH", "MODERATE", "LIMITED", "EMERGING")
CLAIM_STATUSES = ("supported", "uncertain", "unsupported")


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# ---------------------------------------------------------------------------
# Brief
# ---------------------------------------------------------------------------


@dataclass
class ResearchBrief:
    """What the user asked for — spec §8.1 (+ scope/outputs/output_language)."""

    topic: str = ""                 # display/writing topic (Hebrew by default)
    search_topic: str = ""          # English query topic for the databases
    goals: list[str] = field(default_factory=list)
    audience: str = ""
    year_from: int = 2015
    year_to: int = 2026
    subtopics: list[str] = field(default_factory=list)   # English
    languages: list[str] = field(default_factory=lambda: ["English", "Hebrew"])
    user_papers: list[str] = field(default_factory=list)  # DOIs / titles to include
    user_experts: list[str] = field(default_factory=list)
    confidentiality: str = ""
    author: str = ""
    # Additions over the original tool:
    output_language: str = "he"
    scope_preset: str = "full"      # summary (~10 pages) | full (30-40) | custom
    scope_target_pages: int | None = None
    output_slides: bool = False
    output_podcast: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ResearchBrief":
        known = {f.name for f in cls.__dataclass_fields__.values()}  # type: ignore[attr-defined]
        return cls(**{k: v for k, v in data.items() if k in known})


# ---------------------------------------------------------------------------
# Paper
# ---------------------------------------------------------------------------


@dataclass
class Paper:
    """An academic source — spec §8.2 (~20 fields)."""

    id: str = ""
    title: str = ""
    abstract: str = ""
    year: int | None = None
    authors: list[str] = field(default_factory=list)
    journal: str = ""
    citation_count: int = 0
    doi: str = ""
    apa: str = ""
    url: str = ""
    source: str = ""                # which database produced it
    # Reliability drivers:
    tier: str = ""                  # T1 / T2 / T3 (from registry.SOURCE_TIER)
    confidence: str = ""            # HIGH / MODERATE / LIMITED / EMERGING
    doi_verified: bool | None = None    # None = not checked (checked != valid!)
    is_retracted: bool = False
    retraction_note: str = ""
    has_fulltext: bool = False
    fulltext_excerpt: str = ""
    language: str = ""              # ISO code (from OpenAlex) — the honest signal
    found_via: str = "search"       # search / snowball / user / semantic
    source_type: str = ""           # journal-article / preprint / report / ...
    pdf_url: str = ""
    is_open_access: bool = False

    def key_fields_missing(self) -> list[str]:
        missing = []
        if not self.title:
            missing.append("title")
        if not self.authors:
            missing.append("authors")
        if not self.year:
            missing.append("year")
        if not self.doi and not self.url:
            missing.append("doi_or_url")
        if not self.source_type:
            missing.append("source_type")
        return missing

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Paper":
        known = {f.name for f in cls.__dataclass_fields__.values()}  # type: ignore[attr-defined]
        return cls(**{k: v for k, v in data.items() if k in known})


# ---------------------------------------------------------------------------
# TOC
# ---------------------------------------------------------------------------


@dataclass
class TocEntry:
    """One chapter in the table of contents.

    ``keywords_en`` is this project's fix for the pure-Hebrew-chapter-title
    trap (spec §16): source assignment falls back to these English keywords
    when the title yields no Latin tokens.
    """

    chapter: str = ""
    sections: list[str] = field(default_factory=list)
    keywords_en: list[str] = field(default_factory=list)
    description: str = ""           # Part-E: one plain-language line ("מה בפרק")
    depth: str = "standard"         # standard | practical (Part-E)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "TocEntry":
        known = {f.name for f in cls.__dataclass_fields__.values()}  # type: ignore[attr-defined]
        return cls(**{k: v for k, v in data.items() if k in known})


# ---------------------------------------------------------------------------
# Claim
# ---------------------------------------------------------------------------


@dataclass
class Claim:
    """The grounding unit — spec §8.4."""

    id: str = ""
    text: str = ""
    citations: list[int] = field(default_factory=list)   # local [n] numbers
    status: str = "uncertain"       # supported / uncertain / unsupported
    reason: str = ""
    rewrite: str = ""
    chapter: str = ""
    is_web: bool = False            # cites only [W#] — counted separately
    cross_corroborated: bool = False   # Part-E: ≥2 disjoint author groups support it
    status_override: dict[str, Any] | None = None   # {value, by, at, reason}

    def effective_status(self) -> str:
        if self.status_override and self.status_override.get("value"):
            return str(self.status_override["value"])
        return self.status

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Claim":
        known = {f.name for f in cls.__dataclass_fields__.values()}  # type: ignore[attr-defined]
        return cls(**{k: v for k, v in data.items() if k in known})


# ---------------------------------------------------------------------------
# Section
# ---------------------------------------------------------------------------


@dataclass
class SurveySection:
    """One written chapter — spec §8.3."""

    title: str = ""
    content: str = ""               # markdown + markers; source of truth for the draft editor
    confidence: str = ""
    citations: list[str] = field(default_factory=list)   # APA strings (synced at stage 12)
    diagrams: list[str] = field(default_factory=list)    # ready SVG
    issues: list[str] = field(default_factory=list)      # from the Critical Reviewer
    papers: list[Paper] = field(default_factory=list)    # local [n] = papers[n-1]
    claims: list[Claim] = field(default_factory=list)
    # Web-layer additions:
    user_edited: bool = False
    stale_grounding: bool = False
    confidence_override: dict[str, Any] | None = None    # {value, by, at, reason}

    def effective_confidence(self) -> str:
        if self.confidence_override and self.confidence_override.get("value"):
            return str(self.confidence_override["value"])
        return self.confidence

    def to_dict(self) -> dict[str, Any]:
        return {
            "title": self.title,
            "content": self.content,
            "confidence": self.confidence,
            "citations": list(self.citations),
            "diagrams": list(self.diagrams),
            "issues": list(self.issues),
            "papers": [p.to_dict() for p in self.papers],
            "claims": [c.to_dict() for c in self.claims],
            "user_edited": self.user_edited,
            "stale_grounding": self.stale_grounding,
            "confidence_override": self.confidence_override,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SurveySection":
        sec = cls(
            title=data.get("title", ""),
            content=data.get("content", ""),
            confidence=data.get("confidence", ""),
            citations=list(data.get("citations", [])),
            diagrams=list(data.get("diagrams", [])),
            issues=list(data.get("issues", [])),
            papers=[Paper.from_dict(p) for p in data.get("papers", [])],
            claims=[Claim.from_dict(c) for c in data.get("claims", [])],
            user_edited=bool(data.get("user_edited", False)),
            stale_grounding=bool(data.get("stale_grounding", False)),
            confidence_override=data.get("confidence_override"),
        )
        return sec


# ---------------------------------------------------------------------------
# SurveyState
# ---------------------------------------------------------------------------


@dataclass
class SurveyState:
    """The shared workspace every agent reads from and writes to — spec §8.5."""

    brief: ResearchBrief = field(default_factory=ResearchBrief)
    toc: list[TocEntry] = field(default_factory=list)
    papers: list[Paper] = field(default_factory=list)
    sections: list[SurveySection] = field(default_factory=list)
    executive_summary: str = ""
    kpi_data: list[dict[str, Any]] = field(default_factory=list)

    # Transparency blocks (spec §8.5):
    dedup_stats: dict[str, Any] = field(default_factory=dict)
    source_routing: dict[str, Any] = field(default_factory=dict)
    prisma: dict[str, Any] = field(default_factory=dict)
    audit_log: list[dict[str, Any]] = field(default_factory=list)
    retracted_papers: list[dict[str, Any]] = field(default_factory=list)
    grounding_report: dict[str, Any] = field(default_factory=dict)
    citation_report: dict[str, Any] = field(default_factory=dict)
    cited_papers: list[Paper] = field(default_factory=list)
    scorecard: dict[str, Any] = field(default_factory=dict)
    ideation: dict[str, Any] = field(default_factory=dict)
    deep_research: dict[str, Any] = field(default_factory=dict)
    timeline_years: list[int] = field(default_factory=list)
    glossary: list[dict[str, Any]] = field(default_factory=list)
    charts: list[dict[str, Any]] = field(default_factory=list)   # {title, svg, source_note}

    def log(self, stage: str, message: str, **data: Any) -> None:
        entry: dict[str, Any] = {"stage": stage, "message": message, "at": _utcnow()}
        if data:
            entry.update(data)
        self.audit_log.append(entry)

    # -- serialization ------------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": 1,
            "brief": self.brief.to_dict(),
            "toc": [t.to_dict() for t in self.toc],
            "papers": [p.to_dict() for p in self.papers],
            "sections": [s.to_dict() for s in self.sections],
            "executive_summary": self.executive_summary,
            "kpi_data": self.kpi_data,
            "dedup_stats": self.dedup_stats,
            "source_routing": self.source_routing,
            "prisma": self.prisma,
            "audit_log": self.audit_log,
            "retracted_papers": self.retracted_papers,
            "grounding_report": self.grounding_report,
            "citation_report": self.citation_report,
            "cited_papers": [p.to_dict() for p in self.cited_papers],
            "scorecard": self.scorecard,
            "ideation": self.ideation,
            "deep_research": self.deep_research,
            "timeline_years": self.timeline_years,
            "glossary": self.glossary,
            "charts": self.charts,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SurveyState":
        state = cls(
            brief=ResearchBrief.from_dict(data.get("brief", {})),
            toc=[TocEntry.from_dict(t) for t in data.get("toc", [])],
            papers=[Paper.from_dict(p) for p in data.get("papers", [])],
            sections=[SurveySection.from_dict(s) for s in data.get("sections", [])],
            executive_summary=data.get("executive_summary", ""),
            kpi_data=data.get("kpi_data", []),
            dedup_stats=data.get("dedup_stats", {}),
            source_routing=data.get("source_routing", {}),
            prisma=data.get("prisma", {}),
            audit_log=data.get("audit_log", []),
            retracted_papers=data.get("retracted_papers", []),
            grounding_report=data.get("grounding_report", {}),
            citation_report=data.get("citation_report", {}),
            cited_papers=[Paper.from_dict(p) for p in data.get("cited_papers", [])],
            scorecard=data.get("scorecard", {}),
            ideation=data.get("ideation", {}),
            deep_research=data.get("deep_research", {}),
            timeline_years=data.get("timeline_years", []),
            glossary=data.get("glossary", []),
            charts=data.get("charts", []),
        )
        state._unify_paper_identity()
        return state

    def _unify_paper_identity(self) -> None:
        """After deserialization, make section/cited paper entries reference the
        same objects as the main pool, matched by id (falling back to DOI)."""
        pool: dict[str, Paper] = {}
        for p in self.papers:
            if p.id:
                pool[f"id:{p.id}"] = p
            if p.doi:
                pool.setdefault(f"doi:{p.doi.lower()}", p)

        def resolve(p: Paper) -> Paper:
            found = None
            if p.id:
                found = pool.get(f"id:{p.id}")
            if found is None and p.doi:
                found = pool.get(f"doi:{p.doi.lower()}")
            if found is None:
                # Defensive: a paper referenced outside the pool joins it.
                self.papers.append(p)
                if p.id:
                    pool[f"id:{p.id}"] = p
                if p.doi:
                    pool.setdefault(f"doi:{p.doi.lower()}", p)
                return p
            return found

        for sec in self.sections:
            sec.papers = [resolve(p) for p in sec.papers]
        self.cited_papers = [resolve(p) for p in self.cited_papers]

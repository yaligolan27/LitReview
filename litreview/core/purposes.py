"""The purpose registry — the contract between the pipeline and the model.

Every LLM request carries a ``purpose`` string (spec §7.6). The purpose
determines what response shape is expected, whether real web access is
required (bridge: WebSearch/WebFetch; api backend: server-side web tools),
and sensible token/temperature defaults. Parameterized purposes
(``writer:ch{N}``, ``dr_round{N}``) resolve by prefix.
"""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class Purpose:
    name: str                 # canonical name, or prefix for parameterized purposes
    prefix: bool = False      # True → match "name*"
    json_response: bool = False
    requires_web: bool = False
    max_tokens: int = 1500
    temperature: float = 0.3
    description: str = ""


_REGISTRY: list[Purpose] = [
    # --- orchestration / gates ---
    Purpose("toc_review", max_tokens=800,
            description="Display TOC to the human and wait; reply 'approved' or replacement JSON"),
    Purpose("sources_review", max_tokens=800,
            description="CLI bridge gate for the sources list (this project's addition)"),
    Purpose("draft_review", max_tokens=800,
            description="CLI bridge gate for the draft (this project's addition)"),
    # --- source hunting ---
    Purpose("domain_classification", json_response=True, max_tokens=300,
            description='{"domains": [...]} up to 3 from the closed list'),
    Purpose("query_translate", json_response=True, max_tokens=800,
            description='{"translations": {language: query}}'),
    Purpose("query_expansion", json_response=True, max_tokens=1200,
            description='{"concept_blocks": [{concept, synonyms, technical_terms, abbreviations}]}'),
    Purpose("query_refine", json_response=True, max_tokens=600,
            description='{"queries": [...]} English queries for coverage gaps'),
    Purpose("toc_gaps", json_response=True, max_tokens=800,
            description='{"suggestions": [{kind, title, parent, reason}]} for the TOC screen'),
    # --- deep research ---
    Purpose("dr_plan", json_response=True, max_tokens=1200,
            description="{relevance, rationale, catalog_potential, entity_type, subquestions[]}"),
    Purpose("dr_round", prefix=True, json_response=True, requires_web=True, max_tokens=3500,
            description="Real web research round: {round_summary, queries_run, pages_read, findings[]}"),
    Purpose("dr_verify", json_response=True, requires_web=True, max_tokens=2000,
            description="Triangulation: {verdicts: [{id, verdict, second_url, second_source, note}]}"),
    Purpose("dr_contradictions", json_response=True, max_tokens=1500,
            description="{contradictions: [{topic, side_a, side_a_src, side_b, side_b_src, assessment}]}"),
    Purpose("dr_entities", json_response=True, max_tokens=2500,
            description="Normalized comparison table {entity_type, columns, rows[]}"),
    Purpose("dr_trace", prefix=True, json_response=True, requires_web=True, max_tokens=2500,
            description="Part-E: primary-source chase for W-T2/T3 findings"),
    Purpose("source_scout", json_response=True, requires_web=True, max_tokens=1500,
            description="Part-E: discover authoritative databases for an uncovered topic"),
    # --- writing & quality ---
    Purpose("writer:ch", prefix=True, max_tokens=4000, temperature=0.4,
            description="Full Hebrew chapter, markdown + markers, [n] citations only from the given list"),
    Purpose("grounder", json_response=True, max_tokens=2500,
            description="[{index, status, reason, rewrite}] per claim"),
    Purpose("executive", max_tokens=2000,
            description="Text with [KPI_DATA]/[CONCLUSION]/[ROI_CALC] blocks"),
    Purpose("hebrew_editor", max_tokens=4000,
            description="Edited text between ===TEXT=== / ===END==="),
    Purpose("evaluator", json_response=True, max_tokens=400,
            description="{hebrew_quality: 0-10, coherence: 0-10, notes}"),
    Purpose("ideation", json_response=True, max_tokens=2000,
            description="JSON with the 7 ideation categories"),
    Purpose("glossary", json_response=True, max_tokens=2000,
            description="Part-E: {terms: [{term, plain_definition}]}"),
    Purpose("web_landscape", json_response=True, max_tokens=2000,
            description="legacy: {summary, findings[]}"),
]

_EXACT = {p.name: p for p in _REGISTRY if not p.prefix}
_PREFIXES = [p for p in _REGISTRY if p.prefix]


class UnknownPurpose(ValueError):
    pass


def resolve(purpose: str) -> Purpose:
    if purpose in _EXACT:
        return _EXACT[purpose]
    for p in _PREFIXES:
        if purpose.startswith(p.name):
            return p
    raise UnknownPurpose(f"unknown purpose: {purpose!r}")


def slug(purpose: str) -> str:
    """Filesystem-safe purpose slug used in bridge file names (spec §7.4):
    ``dr_round2`` → ``dr-round2``, ``writer:ch3`` → ``writer-ch3``."""
    return re.sub(r"[^A-Za-z0-9-]", "-", purpose.replace("_", "-").replace(":", "-"))


def all_purposes() -> list[Purpose]:
    return list(_REGISTRY)

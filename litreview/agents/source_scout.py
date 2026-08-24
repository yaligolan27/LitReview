"""Source Scout — stage 3.3 (Part-E wave 3, spec §23), behind SURVEY_SOURCE_SCOUT.

The compass: the Scout NEVER lets the model inject a "fact" — it only proposes
*where to look*, and every source it opens still passes the full hunt →
dedup → audit → grounding pipeline. Guardrails, in order:

1. It runs only on a *real* coverage gap (a confident domain suppresses it —
   the routed databases are already right). Every trigger is logged to the
   audit trail.
2. A suggested database is auto-enabled ONLY if it is a built-in connector or
   an entry in ``data/approved_sources.json``. Anything else is returned as
   ``pending_approval`` and shown to the operator — never searched silently.
3. Any newly-registered source is capped at **T2** (never T1) by
   ``registry.register_provider``.
"""

from __future__ import annotations

import json
from pathlib import Path

from ..apis import oai_pmh, openalex, registry
from ..core.context import RunContext
from ..core.llm import extract_json
from ..core.state import SurveyState

COVERAGE_MIN_UNIQUE = 15
COVERAGE_MIN_QUERIES = 4
REFINE_MIN_ADDED = 3
MAX_SUGGESTIONS = 5


def load_allowlist(path: str | Path = "data/approved_sources.json") -> dict[str, dict]:
    """name(lower) → entry. Missing/broken file = empty allowlist (safe)."""
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    out: dict[str, dict] = {}
    for entry in data.get("sources", []):
        name = str(entry.get("name", "")).strip().lower()
        if name:
            out[name] = entry
    return out


def coverage_gap(routing, unique_count: int, executed_count: int,
                 refine_added: int) -> list[str]:
    """Return the trigger reasons, or [] when there is no genuine gap.

    A confident domain classification means the routed databases already fit
    the topic — the Scout stays silent (its purpose is off-catalog topics like
    law/education, not to second-guess a good route)."""
    if getattr(routing, "certain_domains", None):
        return []
    reasons: list[str] = []
    if executed_count >= COVERAGE_MIN_QUERIES and unique_count < COVERAGE_MIN_UNIQUE:
        reasons.append(f"מעט מקורות ({unique_count}<{COVERAGE_MIN_UNIQUE}) "
                       f"אחרי {executed_count} שאילתות")
    if refine_added < REFINE_MIN_ADDED:
        reasons.append(f"סבב ההעמקה הוסיף מעט מקורות ({refine_added}<{REFINE_MIN_ADDED})")
    return reasons


def _suggest(ctx: RunContext, state: SurveyState,
             searched: list[str]) -> list[dict]:
    brief = state.brief
    prompt = (
        f"נושא הסקר: {brief.topic} ({brief.search_topic}).\n"
        f"מאגרים שכבר נסרקו: {', '.join(searched) or '—'}.\n"
        "כיסוי המקורות דל. הצע עד 5 מאגרים אקדמיים סמכותיים ומוכרים "
        "שמתאימים במיוחד לנושא (למשל ERIC לחינוך, SSRN/HeinOnline למשפט, "
        "RePEc לכלכלה). לכל הצעה ציין אם קיים endpoint של OAI-PMH ידוע.\n"
        'החזר JSON: {"suggestions": [{"name": "...", "reason": "...", '
        '"oai_endpoint": "https://... או ריק", "openalex_source_id": "S... או ריק"}]}'
    )
    try:
        data = extract_json(ctx.llm.complete(prompt, purpose="source_scout"))
        suggestions = data.get("suggestions", []) if isinstance(data, dict) else []
    except ValueError:
        return []
    return [s for s in suggestions if isinstance(s, dict) and str(s.get("name", "")).strip()
            ][:MAX_SUGGESTIONS]


def _canonical_connector(key: str) -> str | None:
    return next((p for p in registry.PROVIDERS if p.lower() == key), None)


def _register(name: str, entry: dict, suggestion: dict, offline: bool) -> str | None:
    """Enable one allowlisted/connector suggestion → its registry name, or None
    if it cannot be executed. Network providers are not wired offline."""
    key = name.lower()
    connector = _canonical_connector(key)
    if connector:
        return connector                       # rung 1: built-in connector
    if offline:
        return None                            # never register a network source offline
    etype = str(entry.get("type", "")).lower()
    tier = str(entry.get("tier", "T2"))
    if etype == "oai_pmh" and entry.get("endpoint"):
        fn = oai_pmh.make_provider(key, entry["endpoint"],
                                   set_spec=str(entry.get("set", "")))
        return registry.register_provider(key, fn, tier=tier)
    if etype == "openalex_source":
        source_id = entry.get("source_id") or suggestion.get("openalex_source_id")
        if source_id:
            fn = openalex.make_source_provider(str(source_id), key)
            return registry.register_provider(key, fn, tier=tier)
    return None


def run_source_scout(ctx: RunContext, state: SurveyState, routing,
                     unique: list, executed: list, refine_added: int
                     ) -> tuple[list[str], dict]:
    """Return (enabled_source_names, report). Empty when the flag is off or
    there is no coverage gap."""
    if not ctx.settings.source_scout:
        return [], {}
    reasons = coverage_gap(routing, len(unique), len(executed), refine_added)
    if not reasons:
        return [], {}
    state.log("scout", "coverage gap detected — running Source Scout",
              reasons=reasons)   # audit trail

    allow = load_allowlist()
    suggestions = _suggest(ctx, state, list(routing.active))
    enabled: list[str] = []
    pending: list[dict] = []
    suggested_report: list[dict] = []
    for s in suggestions:
        name = str(s.get("name", "")).strip()
        key = name.lower()
        entry = allow.get(key, {})
        in_catalog = _canonical_connector(key) is not None
        registered = _register(name, entry, s, ctx.offline) if (entry or in_catalog) else None
        status = "enabled" if registered else "pending_approval"
        if registered:
            if registered not in enabled:
                enabled.append(registered)
        else:
            pending.append({"name": name, "reason": str(s.get("reason", "")),
                            "why": "לא בקטלוג/allowlist — דורש אישור מפעיל"})
        suggested_report.append({
            "name": name, "reason": str(s.get("reason", "")),
            "status": status,
            "tier": registry.tier_for(registered) if registered else "—"})

    if enabled:
        state.log("scout", "sources enabled by scout", enabled=enabled,
                  tiers=[registry.tier_for(n) for n in enabled])
    report = {
        "triggers": reasons,
        "suggested": suggested_report,
        "enabled": enabled,
        "pending_approval": pending,
    }
    return enabled, report

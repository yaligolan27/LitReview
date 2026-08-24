"""Stage 1 — Research Planner (spec §9.1).

Bug fix vs. the original (spec §16): never calls ``input()`` unless the CLI
explicitly runs with ``--interactive`` on a TTY. In every other mode the
brief is built from the config dict / API payload.
"""

from __future__ import annotations

import re
from typing import Any

from ..core.context import RunContext
from ..core.state import ResearchBrief, SurveyState

_LATIN = re.compile(r"[A-Za-z]")


def brief_from_config(config: dict[str, Any]) -> ResearchBrief:
    brief = ResearchBrief(
        topic=str(config.get("topic", "")).strip(),
        search_topic=str(config.get("search_topic", "")).strip(),
        goals=[str(g) for g in config.get("goals", [])],
        audience=str(config.get("audience", "")),
        year_from=int(config.get("year_from", 2015)),
        year_to=int(config.get("year_to", 2026)),
        subtopics=[str(s) for s in config.get("subtopics", [])],
        languages=[str(x) for x in config.get("languages", ["English", "Hebrew"])],
        user_papers=[str(p) for p in config.get("user_papers", [])],
        user_experts=[str(e) for e in config.get("user_experts", [])],
        confidentiality=str(config.get("confidentiality", "")),
        author=str(config.get("author", "")),
        output_language=str(config.get("output_language", "he")).lower(),
        scope_preset=str(config.get("scope", config.get("scope_preset", "full"))),
        scope_target_pages=config.get("target_pages"),
        output_slides=bool(config.get("outputs", {}).get("slides", False)),
        output_podcast=bool(config.get("outputs", {}).get("podcast", False)),
    )
    if not brief.topic:
        raise ValueError("config missing 'topic'")
    if not brief.search_topic:
        # The Hebrew display topic pollutes English academic search (spec §8.1);
        # only reuse it when it actually contains Latin text.
        if _LATIN.search(brief.topic):
            brief.search_topic = brief.topic
        else:
            raise ValueError(
                "config missing 'search_topic' (English query topic) and 'topic' "
                "is not Latin-script — academic databases need an English query"
            )
    return brief


def run_research_planner(ctx: RunContext, state: SurveyState,
                         config: dict[str, Any]) -> SurveyState:
    state.brief = brief_from_config(config)
    state.log("plan", "brief built from config",
              topic=state.brief.topic, search_topic=state.brief.search_topic,
              languages=state.brief.languages, scope=state.brief.scope_preset)
    return state


def interactive_interview() -> dict[str, Any]:  # pragma: no cover - TTY only
    """The 10-question interview (spec §9.1) — CLI --interactive only."""
    import sys

    if not sys.stdin.isatty():
        raise RuntimeError("interactive interview requires a TTY; pass --config instead")
    questions = [
        ("topic", "נושא הסקר (עברית): "),
        ("search_topic", "נושא לחיפוש (English): "),
        ("goals", "מטרות (מופרדות בפסיק): "),
        ("audience", "קהל יעד: "),
        ("year_from", "משנה: "),
        ("year_to", "עד שנה: "),
        ("subtopics", "תתי-נושאים באנגלית (מופרדים בפסיק): "),
        ("languages", "שפות חיפוש (מופרדות בפסיק): "),
        ("user_papers", "מאמרים ידועים DOI/כותרת (מופרדים בפסיק): "),
        ("author", "שם מחבר: "),
    ]
    answers: dict[str, Any] = {}
    for key, prompt in questions:
        raw = input(prompt).strip()
        if key in ("goals", "subtopics", "languages", "user_papers"):
            answers[key] = [part.strip() for part in raw.split(",") if part.strip()]
        elif key in ("year_from", "year_to"):
            try:
                answers[key] = int(raw)
            except ValueError:
                pass
        elif raw:
            answers[key] = raw
    return answers

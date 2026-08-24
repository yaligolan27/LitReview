"""Stage 16 — HTML Generator entry point (spec §9.16, M1 subset)."""

from __future__ import annotations

import re
from datetime import date
from pathlib import Path

from ...core.context import RunContext
from ...core.state import SurveyState
from . import builders, template


def _slug(text: str, fallback: str = "survey") -> str:
    slug = re.sub(r"[^A-Za-z0-9]+", "-", text).strip("-").lower()
    return slug[:60] or fallback


def render_document(state: SurveyState) -> str:
    body = "\n".join([
        builders.build_cover(state),
        '<div class="body">',
        builders.build_reliability_notice(state),
        builders.build_executive(state),
        builders.build_scorecard(state),
        builders.build_toc(state),
        builders.build_sections(state),
        builders.build_charts(state),
        builders.build_web_sources(state),
        builders.build_ideation(state),
        builders.build_transparency(state),
        builders.build_bibliography(state),
        "</div>",
    ])
    return template.page(title=state.brief.topic or "סקר ספרות", body=body,
                         lang=state.brief.output_language or "he")


def run_html_generator(ctx: RunContext, state: SurveyState) -> str:
    document = render_document(state)
    out_dir = ctx.workdir / "outputs"
    out_dir.mkdir(parents=True, exist_ok=True)
    name = f"survey_{_slug(state.brief.search_topic or state.brief.topic)}_{date.today():%Y%m%d}.html"
    out_path = out_dir / name
    out_path.write_text(document, encoding="utf-8")
    state.log("html", "document rendered", path=str(out_path), bytes=len(document))
    return str(out_path)

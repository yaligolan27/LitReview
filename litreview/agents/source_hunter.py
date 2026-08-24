"""Stage 3 — Source Hunter (spec §9.3).

M1 scope: heuristic query building, parallel provider fan-out, the
saturation loop, and user-supplied DOIs. Multilingual/concept-block queries,
domain routing, the refine round and snowballing land in M2 — the transparency
blocks they fill are already written here.
"""

from __future__ import annotations

import re
from concurrent.futures import ThreadPoolExecutor, as_completed

from ..apis import crossref, registry
from ..core.context import RunContext
from ..core.dedup import dedupe
from ..core.state import Paper, SurveyState

_SATURATION_MIN_QUERY = 4   # start counting no-growth from the 5th query (index 4)
_SATURATION_ROUNDS = 2


def _latin_tokens(text: str) -> list[str]:
    return [t for t in re.findall(r"[A-Za-z][A-Za-z0-9\-]{2,}", text)]


def build_queries(ctx: RunContext, state: SurveyState) -> list[str]:
    brief = state.brief
    queries: list[str] = []

    def add(q: str) -> None:
        q = " ".join(q.split()).strip()
        if q and q.lower() not in {x.lower() for x in queries}:
            queries.append(q)

    add(brief.search_topic)
    for sub in brief.subtopics:
        add(f"{brief.search_topic} {sub}")
    for entry in state.toc:
        # Only chapter titles containing Latin script join queries directly —
        # a pure-Hebrew title pollutes English academic search (spec §9.3a).
        title_tokens = _latin_tokens(entry.chapter)
        if title_tokens:
            add(f"{brief.search_topic} {' '.join(title_tokens[:4])}")
        elif entry.keywords_en:
            extra = [k for k in entry.keywords_en if _latin_tokens(k)]
            if extra:
                add(f"{brief.search_topic} {extra[0]}")

    return queries[:ctx.settings.max_queries]


def _search_provider(name: str, query: str, limit: int,
                     year_from: int, year_to: int) -> list[Paper]:
    search = registry.get_search(name)
    results = search(query, limit=limit, year_from=year_from, year_to=year_to)
    for paper in results:
        if not paper.tier:
            paper.tier = registry.tier_for(paper.source or name)
        if not paper.source:
            paper.source = name
    return results


def _fan_out(ctx: RunContext, sources: list[str], query: str,
             year_from: int, year_to: int) -> list[Paper]:
    limit = ctx.settings.limit_per_source
    results: list[Paper] = []
    with ThreadPoolExecutor(max_workers=ctx.settings.parallel_search) as pool:
        futures = {}
        for name in sources:
            per_source = limit * 2 if name in registry.UNIVERSAL_CORE or name == "mockdb" else limit
            futures[pool.submit(_search_provider, name, query, per_source,
                                year_from, year_to)] = name
        for future in as_completed(futures):
            name = futures[future]
            try:
                results.extend(future.result())
            except Exception as exc:  # noqa: BLE001 — one provider failing is not fatal
                ctx.log_line("hunt", f"provider {name} failed on {query!r}: {exc}", level="warn")
    return results


def _fetch_user_papers(ctx: RunContext, state: SurveyState) -> list[Paper]:
    papers: list[Paper] = []
    for ref in state.brief.user_papers:
        ref = ref.strip()
        if not ref:
            continue
        if ctx.offline:
            ctx.log_line("hunt", f"offline mode: user paper {ref!r} recorded but not fetched",
                         level="warn")
            continue
        if ref.lower().startswith("10.") or "doi.org" in ref.lower():
            doi = ref.split("doi.org/")[-1]
            paper = crossref.fetch_by_doi(doi)
            if paper:
                paper.found_via = "user"
                paper.tier = registry.tier_for("crossref")
                papers.append(paper)
                continue
        state.log("hunt", f"user paper not resolved yet (title lookup lands in M2): {ref}")
    return papers


def run_source_hunter(ctx: RunContext, state: SurveyState) -> SurveyState:
    brief = state.brief
    sources = registry.active_sources(ctx.settings, offline=ctx.offline)
    queries = build_queries(ctx, state)

    raw_all: list[Paper] = list(_fetch_user_papers(ctx, state))
    unique: list[Paper] = []
    stats: dict = {}
    previous_count = 0
    no_growth = 0
    queries_run = 0

    for qi, query in enumerate(queries):
        found = _fan_out(ctx, sources, query, brief.year_from, brief.year_to)
        queries_run += 1
        raw_all.extend(found)
        unique, stats = dedupe(raw_all, threshold=ctx.settings.dedup_threshold)
        growth = len(unique) - previous_count
        previous_count = len(unique)
        ctx.emitter.emit("progress", stage="hunt",
                         detail=f"query {qi + 1}/{len(queries)}: +{growth} → {len(unique)} unique")
        if qi >= _SATURATION_MIN_QUERY and growth == 0:
            no_growth += 1
            if no_growth >= _SATURATION_ROUNDS:
                state.log("hunt", "saturation reached — stopping query loop",
                          after_queries=queries_run)
                break
        else:
            no_growth = 0

    for paper in unique:
        if not paper.tier:
            paper.tier = registry.tier_for(paper.source)

    state.papers = unique
    state.dedup_stats = stats
    state.timeline_years = sorted(p.year for p in unique if p.year)
    state.prisma = {
        "identified": stats.get("found", len(raw_all)),
        "duplicates_removed": stats.get("removed", 0),
        "after_dedup": stats.get("kept", len(unique)),
        "queries": queries_run,
    }
    state.source_routing = {
        "active_sources": sources,
        "domains": [],                      # M2: domain routing
        "dropped_sources": [],
        "languages_requested": list(brief.languages),
        "languages_searched": ["English"],  # M2: multilingual queries
        "refine_rounds": 0,
        "refine_added": 0,
    }
    state.log("hunt", "source hunt complete", unique=len(unique),
              queries=queries_run, sources=sources)
    return state

"""Stage 3 — Source Hunter, full version (spec §9.3).

Five sub-stages:
a. Query building — multilingual queries FIRST (guaranteed, never capped by
   MAX_QUERIES), then heuristics, then optional LLM concept blocks.
b. Domain routing (apis/registry.route) with dual keyword+LLM classification.
c. Saturation search loop with parallel provider fan-out.
d. Self-refinement round(s): the LLM sees found titles + run queries and
   proposes queries for coverage gaps. It is a query generator ONLY —
   nothing it says enters the bibliography. Counter semantics (bug fix):
   SURVEY_REFINE_ROUNDS=2 runs two rounds; 0 disables.
e. Snowballing: Semantic Scholar references/citations of the 3 most-cited
   papers (cap 40) + OpenCitations DOIs of the top 2 (cap 16, via Crossref).
"""

from __future__ import annotations

import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass

from ..apis import crossref, opencitations, registry, semantic_scholar
from ..core.context import RunContext
from ..core.dedup import dedupe, similarity
from ..core.llm import extract_json
from ..core.state import Paper, SurveyState
from . import source_scout

_SATURATION_MIN_QUERY = 4
_SATURATION_ROUNDS = 2
SNOWBALL_S2_CAP = 40
SNOWBALL_OC_CAP = 16


@dataclass
class Query:
    text: str
    language: str = "English"
    origin: str = "heuristic"    # multilang / heuristic / concept / refine


def _latin_tokens(text: str) -> list[str]:
    return re.findall(r"[A-Za-z][A-Za-z0-9\-]{2,}", text)


# --- a. queries ------------------------------------------------------------


def _multilang_queries(ctx: RunContext, state: SurveyState) -> list[Query]:
    """Guaranteed multilingual queries (spec §9.3a): Hebrew uses the display
    topic directly; other non-English languages get one bridge translation
    call; a failed translation silently skips that language."""
    brief = state.brief
    queries: list[Query] = []
    others = [lang for lang in brief.languages
              if lang.strip().lower() not in ("english", "en")]
    for lang in others:
        if lang.strip().lower() in ("hebrew", "he", "עברית"):
            if brief.topic.strip():
                queries.append(Query(brief.topic.strip(), language="Hebrew",
                                     origin="multilang"))
            continue
    to_translate = [lang for lang in others
                    if lang.strip().lower() not in ("hebrew", "he", "עברית")]
    if to_translate:
        prompt = (
            "תרגם את שאילתת החיפוש האקדמית הבאה לכל אחת מהשפות, תוך שמירה על "
            "המונחים הטכניים המקובלים בכל שפה. החזר JSON בפורמט "
            '{"translations": {"שפה": "שאילתה"}}.\n'
            f"שאילתה: {brief.search_topic}\n"
            f"שפות: {', '.join(to_translate)}"
        )
        try:
            data = extract_json(ctx.llm.complete(prompt, purpose="query_translate"))
            translations = data.get("translations", {}) if isinstance(data, dict) else {}
        except Exception:  # noqa: BLE001 — translation failure skips silently
            translations = {}
        for lang in to_translate:
            translated = str(translations.get(lang, "")).strip()
            if translated:
                queries.append(Query(translated, language=lang, origin="multilang"))
    return queries


def _heuristic_queries(state: SurveyState) -> list[Query]:
    brief = state.brief
    queries: list[Query] = [Query(brief.search_topic)]
    for sub in brief.subtopics:
        queries.append(Query(f"{brief.search_topic} {sub}"))
    for entry in state.toc:
        title_tokens = _latin_tokens(entry.chapter)
        if title_tokens:
            queries.append(Query(f"{brief.search_topic} {' '.join(title_tokens[:4])}"))
        else:
            latin_kw = next((k for k in entry.keywords_en if _latin_tokens(k)), "")
            if latin_kw:
                queries.append(Query(f"{brief.search_topic} {latin_kw}"))
    return queries


def _concept_queries(ctx: RunContext, state: SurveyState) -> list[Query]:
    """LLM concept blocks (spec §9.3a) — active in mock/api backends, or in
    native with SURVEY_LLM_QUERY_EXPANSION=1 (extra bridge waits are opt-in)."""
    settings = ctx.settings
    if not (settings.llm_query_expansion or settings.llm_backend in ("mock", "api")):
        return []
    prompt = (
        "פרק את הנושא האקדמי הבא לבלוקי מושגים. החזר JSON בפורמט "
        '{"concept_blocks": [{"concept": "...", "synonyms": [...], '
        '"technical_terms": [...], "abbreviations": [...]}]}.\n'
        f"נושא: {state.brief.search_topic}"
    )
    try:
        data = extract_json(ctx.llm.complete(prompt, purpose="query_expansion"))
        blocks = data.get("concept_blocks", []) if isinstance(data, dict) else []
    except Exception:  # noqa: BLE001
        return []
    terms_per_block: list[list[str]] = []
    for block in blocks[:3]:
        terms = [t for key in ("technical_terms", "synonyms", "abbreviations")
                 for t in (block.get(key) or []) if isinstance(t, str) and t.strip()]
        if terms:
            terms_per_block.append(terms[:3])
    queries: list[Query] = []
    if len(terms_per_block) >= 2:
        for a in terms_per_block[0][:2]:
            for b in terms_per_block[1][:2]:
                queries.append(Query(f"{a} {b}", origin="concept"))
    elif terms_per_block:
        for term in terms_per_block[0][:2]:
            queries.append(Query(f"{state.brief.search_topic} {term}", origin="concept"))
    return queries[:4]


def build_queries(ctx: RunContext, state: SurveyState) -> list[Query]:
    multilang = _multilang_queries(ctx, state)
    rest = _heuristic_queries(state) + _concept_queries(ctx, state)
    seen: set[str] = set()
    unique_rest: list[Query] = []
    for q in rest:
        text = " ".join(q.text.split())
        if text and text.lower() not in seen:
            seen.add(text.lower())
            unique_rest.append(Query(text, q.language, q.origin))
    # Multilingual queries enter first and are NOT capped (spec §9.3a).
    return multilang + unique_rest[:ctx.settings.max_queries]


# --- b. routing ------------------------------------------------------------


def _llm_domains(ctx: RunContext, state: SurveyState) -> list[str]:
    if not ctx.settings.llm_domain:
        return []
    closed_list = ", ".join(registry.DOMAIN_PROFILES)
    prompt = (
        f"סווג את נושא המחקר לתחום אחד עד שלושה מהרשימה הסגורה: {closed_list}. "
        'החזר JSON: {"domains": ["..."]}.\n'
        f"נושא: {state.brief.search_topic}\n"
        f"תתי-נושאים: {', '.join(state.brief.subtopics)}"
    )
    try:
        data = extract_json(ctx.llm.complete(prompt, purpose="domain_classification"))
        domains = data.get("domains", []) if isinstance(data, dict) else []
        return [d for d in domains if d in registry.DOMAIN_PROFILES][:3]
    except Exception:  # noqa: BLE001
        return []


# --- c. search loop --------------------------------------------------------


def _search_provider(name: str, query: str, limit: int,
                     year_from: int, year_to: int) -> list[Paper]:
    results = registry.get_search(name)(query, limit=limit,
                                        year_from=year_from, year_to=year_to)
    for paper in results:
        if not paper.source:
            paper.source = name
        if not paper.tier:
            paper.tier = registry.tier_for(paper.source)
    return results


def _fan_out(ctx: RunContext, sources: list[str], query: str,
             year_from: int, year_to: int) -> list[Paper]:
    limit = ctx.settings.limit_per_source
    results: list[Paper] = []
    with ThreadPoolExecutor(max_workers=ctx.settings.parallel_search) as pool:
        futures = {}
        for name in sources:
            per_source = limit * 2 if name in registry.UNIVERSAL_CORE or name == "mockdb" \
                else limit
            futures[pool.submit(_search_provider, name, query, per_source,
                                year_from, year_to)] = name
        for future in as_completed(futures):
            name = futures[future]
            try:
                results.extend(future.result())
            except Exception as exc:  # noqa: BLE001
                ctx.log_line("hunt", f"provider {name} failed on {query!r}: {exc}",
                             level="warn")
    return results


# --- d. refinement ---------------------------------------------------------


def _refine_queries(ctx: RunContext, state: SurveyState,
                    unique: list[Paper], run_queries: list[str]) -> list[Query]:
    titles = [p.title for p in
              sorted(unique, key=lambda p: p.citation_count, reverse=True)[:40]]
    prompt = (
        "אלה כותרות המאמרים שנמצאו עד כה ורשימת השאילתות שהורצו. זהה עד 5 "
        "פערים — תת-נושאים, שיטות, יישומים או זוויות מרכזיות שאינם מכוסים דיים "
        "על ידי המאמרים למעלה. לכל פער נסח שאילתה אקדמית באנגלית (2-5 מילים). "
        'החזר JSON: {"queries": ["..."]}.\n\n'
        "כותרות שנמצאו:\n" + "\n".join(f"- {t}" for t in titles) +
        "\n\nשאילתות שהורצו:\n" + "\n".join(f"- {q}" for q in run_queries)
    )
    try:
        data = extract_json(ctx.llm.complete(prompt, purpose="query_refine"))
        queries = data.get("queries", []) if isinstance(data, dict) else []
        return [Query(str(q).strip(), origin="refine")
                for q in queries[:5] if str(q).strip()]
    except Exception:  # noqa: BLE001
        return []


# --- e. snowballing --------------------------------------------------------


def _snowball(ctx: RunContext, unique: list[Paper]) -> list[Paper]:
    if not ctx.settings.enable_snowball or ctx.offline:
        return []
    found: list[Paper] = []
    top = sorted(unique, key=lambda p: p.citation_count, reverse=True)
    for paper in top[:3]:
        if len(found) >= SNOWBALL_S2_CAP:
            break
        budget = SNOWBALL_S2_CAP - len(found)
        for related in (semantic_scholar.references(paper, limit=budget // 2 or 1) +
                        semantic_scholar.citations(paper, limit=budget // 2 or 1)):
            related.found_via = "snowball"
            found.append(related)
            if len(found) >= SNOWBALL_S2_CAP:
                break
    oc_seed = [p.doi for p in top[:2] if p.doi]
    if oc_seed:
        found.extend(opencitations.snowball(oc_seed, cap=SNOWBALL_OC_CAP))
    return found


# --- user papers -----------------------------------------------------------


def _fetch_user_papers(ctx: RunContext, state: SurveyState) -> list[Paper]:
    papers: list[Paper] = []
    for ref in state.brief.user_papers:
        ref = ref.strip().strip('"')
        if not ref:
            continue
        if ctx.offline:
            ctx.log_line("hunt", f"offline mode: user paper {ref!r} not fetched",
                         level="warn")
            continue
        paper = None
        if ref.lower().startswith("10.") or "doi.org" in ref.lower():
            paper = crossref.fetch_by_doi(ref.split("doi.org/")[-1])
        else:
            for candidate in crossref.search(ref, limit=3):
                if similarity(candidate.title.lower(), ref.lower()) >= 88:
                    paper = candidate
                    break
        if paper is not None:
            paper.found_via = "user"
            paper.tier = registry.tier_for("crossref")
            papers.append(paper)
        else:
            state.log("hunt", f"user paper could not be resolved: {ref}")
    return papers


# --- main ------------------------------------------------------------------


def run_source_hunter(ctx: RunContext, state: SurveyState) -> SurveyState:
    brief = state.brief

    llm_domains = _llm_domains(ctx, state)
    routing_text = " ".join([brief.search_topic, *brief.subtopics, *brief.goals,
                             *(kw for t in state.toc for kw in t.keywords_en)])
    routing = registry.route(ctx.settings, routing_text,
                             llm_domains=llm_domains, offline=ctx.offline)
    sources = routing.active

    queries = build_queries(ctx, state)
    raw_all: list[Paper] = list(_fetch_user_papers(ctx, state))
    unique: list[Paper] = []
    stats: dict = {}
    previous_count = 0
    no_growth = 0
    executed: list[str] = []
    languages_searched: set[str] = set()

    def run_query_list(query_list: list[Query], saturating: bool) -> bool:
        nonlocal unique, stats, previous_count, no_growth
        for qi, query in enumerate(query_list):
            found = _fan_out(ctx, sources, query.text, brief.year_from, brief.year_to)
            executed.append(query.text)
            if found:
                languages_searched.add(query.language)
            raw_all.extend(found)
            unique, stats = dedupe(raw_all, threshold=ctx.settings.dedup_threshold)
            growth = len(unique) - previous_count
            previous_count = len(unique)
            ctx.emitter.emit("progress", stage="hunt",
                             detail=f"[{query.origin}] {query.text[:60]!r}: "
                                    f"+{growth} → {len(unique)} unique")
            if saturating and qi >= _SATURATION_MIN_QUERY and growth == 0:
                no_growth += 1
                if no_growth >= _SATURATION_ROUNDS:
                    state.log("hunt", "saturation reached — stopping query loop",
                              after_queries=len(executed))
                    return True
            elif saturating:
                no_growth = 0
        return False

    run_query_list(queries, saturating=True)

    refine_added = 0
    refine_rounds_run = 0
    for _ in range(ctx.settings.refine_rounds):
        if not unique:
            break
        new_queries = _refine_queries(ctx, state, unique, executed)
        if not new_queries:
            break
        refine_rounds_run += 1
        before = len(unique)
        run_query_list(new_queries, saturating=False)
        refine_added += len(unique) - before

    # Source Scout (stage 3.3, Part-E wave 3): only on a real coverage gap,
    # and only databases from the catalog/allowlist are searched automatically.
    scout_enabled, scout_report = source_scout.run_source_scout(
        ctx, state, routing, unique, executed, refine_added)
    if scout_enabled:
        for query in queries[:_SATURATION_MIN_QUERY]:
            found = _fan_out(ctx, scout_enabled, query.text,
                             brief.year_from, brief.year_to)
            for paper in found:
                paper.found_via = "scout"
            raw_all.extend(found)
        unique, stats = dedupe(raw_all, threshold=ctx.settings.dedup_threshold)
        sources = sources + [s for s in scout_enabled if s not in sources]

    snowballed = _snowball(ctx, unique)
    if snowballed:
        raw_all.extend(snowballed)
        unique, stats = dedupe(raw_all, threshold=ctx.settings.dedup_threshold)

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
        "queries": len(executed),
    }
    state.source_routing = {
        "active_sources": sources,
        "domains": routing.domains,
        "llm_domains": routing.llm_domains,
        "certain_domains": routing.certain_domains,
        "core_sources_added": routing.core_added,
        "dropped_sources": routing.dropped,
        "safety_net_triggered": routing.safety_net_triggered,
        "override": routing.override,
        "refine_rounds": refine_rounds_run,
        "refine_added": refine_added,
        "snowball_added": len(snowballed),
        "languages_requested": list(brief.languages),
        "languages_searched": sorted(languages_searched) or ["English"],
    }
    if scout_report:
        state.source_routing["source_scout"] = scout_report
    state.log("hunt", "source hunt complete", unique=len(unique),
              queries=len(executed), sources=sources,
              refine_added=refine_added, snowball=len(snowballed))
    return state

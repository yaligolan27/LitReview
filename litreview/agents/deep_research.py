"""Stage 5.7 — Deep Research Engine (spec §9.5.7).

The academic survey says what the research claims; this engine reports what
is happening in the field — vendors, regulation, programs, the last year —
and verifies it. Runs before the Writer so findings are citable as [W#].

Structure:
  A. dr_plan     — relevance gate (high/medium/low → round budget),
                   subquestions, catalog potential
  B. dr_round{N} — iterative research with a coverage map; requires REAL
                   web search (bridge: WebSearch/WebFetch; api backend:
                   server-side web tools); saturation stop on 0 new findings
  C. verification — _clean_finding (no real URL → discarded), URL dedup,
                   deterministic domain tiering, triangulation on numeric /
                   regulation findings (different-domain second source),
                   academic cross-check
  D. dr_contradictions — up to 5 real tensions
  E. dr_entities — normalized comparison table (rows without a source URL
                   are discarded)

The iron rule: web findings are cited ONLY as [W#], never enter the academic
bibliography, and never ground a scientific claim.
"""

from __future__ import annotations

import re
from urllib.parse import urlparse

from ..core.context import RunContext
from ..core.dedup import similarity
from ..core.llm import extract_json
from ..core.state import SurveyState

_ROUND_SYSTEM = (
    "אתה סוכן deep-research. חובה: בצע חיפושי web אמיתיים (WebSearch) ופתח "
    "וקרא דפים מלאים (WebFetch) לפני מענה — אל תענה מהזיכרון. כל URL חייב "
    "להיות קישור שנצפה בפועל, וכל quote חייב להיות ציטוט מילולי מהדף שנקרא. "
    "העדף מקורות ראשוניים. החזר JSON בלבד."
)

W_T1_SUFFIXES = (".gov", ".mil", ".edu", ".int", ".gov.uk", ".ac.uk",
                 ".ac.il", ".gov.il")
W_T1_DOMAINS = {
    "nasa.gov", "esa.int", "iso.org", "itu.int", "ieee.org", "who.int",
    "nist.gov", "europa.eu", "oecd.org", "worldbank.org", "nature.com",
    "science.org", "arxiv.org", "acm.org", "un.org", "imf.org", "wto.org",
}
W_T2_DOMAINS = {
    "reuters.com", "apnews.com", "bloomberg.com", "ft.com", "wsj.com",
    "economist.com", "bbc.com", "bbc.co.uk", "nytimes.com", "theguardian.com",
    "cnbc.com", "axios.com", "politico.com", "politico.eu", "spacenews.com",
    "defensenews.com", "janes.com", "aviationweek.com", "breakingdefense.com",
    "techcrunch.com", "wired.com", "arstechnica.com", "theverge.com",
    "statista.com", "mckinsey.com", "gartner.com", "deloitte.com",
    "globes.co.il", "calcalist.co.il", "themarker.com", "timesofisrael.com",
}
W_T3_MARKERS = ("blogspot.", "wordpress.", "medium.com", "substack.com",
                "reddit.com", "quora.com", "facebook.com", "twitter.com",
                "x.com", "linkedin.com", "youtube.com", "fandom.com",
                "wikipedia.org")


# Two-part public suffixes where the registrable domain is the last THREE
# labels (so foo.gov.uk and bar.gov.uk are distinct organizations, but
# a.example.co.uk and b.example.co.uk are NOT).
_MULTI_SUFFIXES = ("gov.uk", "ac.uk", "co.uk", "org.uk", "gov.il", "ac.il",
                   "co.il", "org.il", "com.au", "gov.au", "edu.au", "co.jp",
                   "go.jp", "ac.jp", "com.br", "gov.br", "co.in", "gov.in")


def _host(url: str) -> str:
    try:
        host = urlparse(url).netloc.lower()
    except ValueError:
        return ""
    host = host.split(":", 1)[0]
    return host[4:] if host.startswith("www.") else host


def _domain(url: str) -> str:
    """Registrable domain (eTLD+1), so subdomains of one site are NOT treated
    as independent sources during triangulation (e.g. www.nasa.gov and
    science.nasa.gov both -> nasa.gov)."""
    host = _host(url)
    if not host:
        return ""
    labels = host.split(".")
    for suffix in _MULTI_SUFFIXES:
        if host == suffix or host.endswith("." + suffix):
            n = suffix.count(".") + 2
            return ".".join(labels[-n:])
    return ".".join(labels[-2:]) if len(labels) >= 2 else host


def classify_tier(url: str) -> str:
    """Deterministic domain tiering — hard code, no LLM (mechanism #9).
    T1 (authoritative suffix/domain) is checked before the T3 marker
    substrings, so a legitimate .gov/.edu host is never demoted by a marker
    that merely appears as a substring of its name."""
    host = _host(url)
    if not host:
        return "W-T3"
    if host in W_T1_DOMAINS or any(host.endswith(sfx) for sfx in W_T1_SUFFIXES):
        return "W-T1"
    if any(marker in host for marker in W_T3_MARKERS):
        return "W-T3"
    if host in W_T2_DOMAINS or any(host.endswith("." + d) for d in W_T2_DOMAINS):
        return "W-T2"
    return "W-T3"


def _normalize_url(url: str) -> str:
    url = url.strip()
    url = re.sub(r"#.*$", "", url)
    url = re.sub(r"[?&]utm_[^=]+=[^&]*", "", url)
    url = re.sub(r"\?$", "", url)
    url = url.replace("://www.", "://")
    return url.rstrip("/").lower()


def clean_finding(raw: dict) -> dict | None:
    """The central anti-hallucination gate: a finding without a real URL,
    heading and insight simply does not exist (spec §9.5.7 C1)."""
    if not isinstance(raw, dict):
        return None
    url = str(raw.get("url", "")).strip()
    heading = str(raw.get("heading", "")).strip()
    insight = str(raw.get("insight", "")).strip()
    if not url.startswith("http") or not heading or not insight:
        return None
    return {
        "id": str(raw.get("id", "")).strip(),
        "type": str(raw.get("type", "market")).strip().lower(),
        "heading": heading,
        "insight": insight,
        "url": url,
        "source_name": str(raw.get("source_name", "")).strip() or _domain(url),
        "date": str(raw.get("date", "")).strip(),
        "quote": str(raw.get("quote", "")).strip(),
        "sq": str(raw.get("sq", "")).strip(),
        "tier": classify_tier(url),
        "verdict": "",
    }


# --- A: plan ---------------------------------------------------------------


def _plan(ctx: RunContext, state: SurveyState) -> dict:
    brief = state.brief
    prompt = (
        f"נושא הסקר: {brief.topic} ({brief.search_topic})\n"
        f"מטרות: {', '.join(brief.goals)}\n"
        f"תתי-נושאים: {', '.join(brief.subtopics)}\n\n"
        "תכנן מחקר web משלים לסקר האקדמי. החזר JSON:\n"
        '{"relevance": "high"|"medium"|"low", "rationale": "...", '
        '"catalog_potential": true|false, "entity_type": "...", '
        '"subquestions": [{"id": "SQ1", "q": "...", "angle": "...", '
        '"target_sources": ["..."]}]} — 4-7 תתי-שאלות.'
    )
    try:
        plan = extract_json(ctx.llm.complete(prompt, purpose="dr_plan"))
        assert isinstance(plan, dict) and plan.get("subquestions")
    except (ValueError, AssertionError):
        plan = {"relevance": "low", "rationale": "planning failed — minimal round",
                "catalog_potential": False, "entity_type": "",
                "subquestions": [{"id": "SQ1", "q": f"מה חדש בתחום {brief.topic}?",
                                  "angle": "market", "target_sources": []}]}
    for i, sq in enumerate(plan.get("subquestions", []), start=1):
        sq.setdefault("id", f"SQ{i}")
    return plan


def _rounds_for(relevance: str, configured: int) -> int:
    if relevance == "high":
        return configured
    if relevance == "medium":
        return max(1, configured - 1)
    return 1


# --- B: rounds -------------------------------------------------------------


def _coverage_map(plan: dict, findings: list[dict]) -> str:
    lines = []
    for sq in plan.get("subquestions", []):
        matched = [f for f in findings if f.get("sq") == sq["id"]]
        domains = {_domain(f["url"]) for f in matched}
        if len(matched) >= 2 and len(domains) >= 2:
            icon, label = "✅", "מכוסה"
        elif matched:
            icon, label = "🟡", "חלקי"
        else:
            icon, label = "🔴", "פתוח"
        lines.append(f"- {sq['id']} [{icon} {label}, {len(matched)} ממצאים]: {sq['q']}")
    return "\n".join(lines)


def _round_prompt(state: SurveyState, plan: dict, findings: list[dict],
                  round_no: int) -> str:
    seen_urls = "\n".join(f"- {f['url']}" for f in findings[-30:])
    depth = ""
    if round_no >= 2:
        depth = ("\nזהו סבב העמקה: התמקד בתתי-השאלות הפתוחות/חלקיות בלבד. רד "
                 "לעומק — עקוב אחרי קישורים מהדפים שקראת, חפש מסמכי מקור "
                 "(דוחות, מפרטים, הודעות רשמיות), וגוון דומיינים (אל תחזור "
                 "לאתרים שכבר מוצו).")
    return (
        f"נושא: {state.brief.topic} ({state.brief.search_topic})\n"
        f"מפת כיסוי נוכחית:\n{_coverage_map(plan, findings)}\n\n"
        f"URLs שכבר נאספו (אל תחזיר אותם שוב):\n{seen_urls or '- (אין)'}\n"
        f"{depth}\n\n"
        'החזר JSON: {"round_summary": "...", "queries_run": n, "pages_read": n, '
        '"findings": [{"id": "F#", "sq": "SQ#", "type": '
        '"market"|"regulation"|"stat"|"program"|"product", "heading": "...", '
        '"insight": "תובנה בעברית", "url": "https://...", "source_name": "...", '
        '"date": "YYYY-MM", "quote": "ציטוט מילולי מהדף"}]}'
    )


# --- C: verification -------------------------------------------------------


def _verify(ctx: RunContext, findings: list[dict]) -> int:
    settings = ctx.settings
    if not settings.dr_verify:
        return 0
    candidates = [f for f in findings
                  if f["type"] in ("stat", "regulation")
                  or re.search(r"\d", f["insight"])][:settings.dr_verify_cap]
    if not candidates:
        return 0
    listing = "\n".join(
        f"- {f['id']}: {f['insight']} (מקור: {f['url']})" for f in candidates)
    prompt = (
        "אמת את הממצאים הבאים בחיפוש web אמיתי אחר מקור שני בלתי-תלוי "
        "(דומיין שונה לגמרי מהמקור המקורי). אל תמציא.\n"
        f"{listing}\n\n"
        'החזר JSON: {"verdicts": [{"id": "F#", "verdict": '
        '"corroborated"|"disputed"|"unverified", "second_url": "https://...", '
        '"second_source": "...", "note": "..."}]}'
    )
    try:
        data = extract_json(ctx.llm.complete(prompt, purpose="dr_verify"))
        verdicts = data.get("verdicts", []) if isinstance(data, dict) else []
    except ValueError:
        verdicts = []
    by_id = {f["id"]: f for f in findings}
    corroborated = 0
    for verdict in verdicts:
        finding = by_id.get(str(verdict.get("id", "")).strip())
        if finding is None:
            continue
        kind = str(verdict.get("verdict", "")).lower()
        second_url = str(verdict.get("second_url", "")).strip()
        if kind == "corroborated":
            # Acceptance condition (spec): real second URL from a DIFFERENT domain.
            if second_url.startswith("http") and \
                    _domain(second_url) and _domain(second_url) != _domain(finding["url"]):
                finding["verdict"] = "corroborated"
                finding["second_url"] = second_url
                finding["second_source"] = str(verdict.get("second_source", ""))
                corroborated += 1
            else:
                finding["verdict"] = "unverified"
        elif kind == "disputed":
            finding["verdict"] = "disputed"
            finding["verify_note"] = str(verdict.get("note", ""))
        else:
            finding["verdict"] = "unverified"
    return corroborated


def _cross_check_academic(state: SurveyState, findings: list[dict]) -> int:
    overlaps = 0
    titles = [(p.title or "").lower() for p in state.papers]
    for finding in findings:
        probe = f"{finding['heading']} {finding['insight']}".lower()
        for title in titles:
            if title and similarity(probe, title) >= 72:
                finding["academic_overlap"] = True
                overlaps += 1
                break
    return overlaps


# --- D: contradictions -----------------------------------------------------


def _contradictions(ctx: RunContext, state: SurveyState,
                    findings: list[dict]) -> list[dict]:
    if not findings:
        return []
    listing = "\n".join(f"- [{f['id']}] {f['insight']} ({f['source_name']})"
                        for f in findings)
    academic = "\n".join(f"- {p.title}" for p in state.papers[:15])
    prompt = (
        f"ממצאי ה-web:\n{listing}\n\nכותרות אקדמיות:\n{academic}\n\n"
        "זהה עד 5 מתחים ממשיים — בין ממצאי web לעצמם, או בין ממצא web לספרות "
        "האקדמית. רק מתחים שברורים מהמידע שסופק — אל תמציא.\n"
        'החזר JSON: {"contradictions": [{"topic": "...", "side_a": "...", '
        '"side_a_src": "...", "side_b": "...", "side_b_src": "...", '
        '"assessment": "הערכה מאוזנת"}]}'
    )
    try:
        data = extract_json(ctx.llm.complete(prompt, purpose="dr_contradictions"))
        rows = data.get("contradictions", []) if isinstance(data, dict) else []
    except ValueError:
        rows = []
    return [r for r in rows if isinstance(r, dict) and r.get("side_a")][:5]


# --- E: entities -----------------------------------------------------------


def _entities(ctx: RunContext, state: SurveyState, plan: dict,
              findings: list[dict]) -> dict:
    mode = ctx.settings.dr_entities
    wanted = mode == "1" or (mode == "auto" and plan.get("catalog_potential"))
    if not wanted or not findings:
        return {}
    listing = "\n".join(f"- {f['heading']}: {f['insight']} ({f['url']})"
                        for f in findings)
    prompt = (
        f"סוג הישויות: {plan.get('entity_type') or 'שחקנים בתחום'}\n"
        f"ממצאים:\n{listing}\n\n"
        "בנה טבלת השוואה מנורמלת (4-8 עמודות, עד 20 שורות). תא לא ידוע = "
        '"—", לעולם לא ניחוש. כל שורה חייבת source_url אמיתי.\n'
        'החזר JSON: {"entity_type": "...", "columns": [...], "rows": '
        '[{"cells": [...], "source_url": "https://...", "source_name": "..."}]}'
    )
    try:
        data = extract_json(ctx.llm.complete(prompt, purpose="dr_entities"))
        assert isinstance(data, dict)
    except (ValueError, AssertionError):
        return {}
    columns = [str(c) for c in data.get("columns", [])]
    rows = []
    for row in data.get("rows", [])[:20]:
        url = str(row.get("source_url", "")).strip()
        if not url.startswith("http"):
            continue   # a row without a real source is discarded (spec E)
        cells = [str(c) for c in row.get("cells", [])]
        if columns and len(cells) != len(columns):
            cells = (cells + ["—"] * len(columns))[:len(columns)]
        rows.append({"cells": cells, "source_url": url,
                     "source_name": str(row.get("source_name", "")) or _domain(url)})
    if not rows:
        return {}
    return {"entity_type": data.get("entity_type", ""), "columns": columns,
            "rows": rows}


# --- main ------------------------------------------------------------------


def run_deep_research(ctx: RunContext, state: SurveyState) -> SurveyState:
    settings = ctx.settings
    if not settings.deep_research:
        state.log("deep_research", "disabled by flag")
        state.deep_research = {}
        return state

    plan = _plan(ctx, state)
    max_rounds = _rounds_for(str(plan.get("relevance", "low")).lower(),
                             settings.dr_rounds)

    findings: list[dict] = []
    seen_urls: set[str] = set()
    rounds_meta: list[dict] = []
    total_queries = total_pages = 0

    for round_no in range(1, max_rounds + 1):
        try:
            data = extract_json(ctx.llm.complete(
                _round_prompt(state, plan, findings, round_no),
                purpose=f"dr_round{round_no}", system=_ROUND_SYSTEM))
        except ValueError:
            ctx.log_line("deep_research", f"round {round_no}: unparseable reply",
                         level="warn")
            break
        raw_findings = data.get("findings", []) if isinstance(data, dict) else []
        new_count = 0
        for raw in raw_findings:
            finding = clean_finding(raw)
            if finding is None:
                continue
            normalized = _normalize_url(finding["url"])
            if normalized in seen_urls:
                continue
            if any(similarity(finding["heading"].lower(), f["heading"].lower()) >= 88
                   for f in findings):
                continue
            seen_urls.add(normalized)
            finding["id"] = finding["id"] or f"F{len(findings) + 1}"
            findings.append(finding)
            new_count += 1
            if len(findings) >= settings.dr_max_findings:
                break
        total_queries += int(data.get("queries_run") or 0)
        total_pages += int(data.get("pages_read") or 0)
        rounds_meta.append({"round": round_no,
                            "summary": str(data.get("round_summary", "")),
                            "new_findings": new_count})
        ctx.emitter.emit("progress", stage="deep_research",
                         detail=f"round {round_no}: +{new_count} findings "
                                f"({len(findings)} total)")
        if new_count == 0:
            state.log("deep_research", f"saturation at round {round_no}")
            break
        if len(findings) >= settings.dr_max_findings:
            break

    corroborated = _verify(ctx, findings)
    overlaps = _cross_check_academic(state, findings)
    contradictions = _contradictions(ctx, state, findings) if findings else []
    entities = _entities(ctx, state, plan, findings)

    # [W#] numbering: corroborated findings first, then by tier.
    ordered = sorted(findings, key=lambda f: (f.get("verdict") != "corroborated",
                                              f.get("tier", "W-T3")))
    for i, finding in enumerate(ordered, start=1):
        finding["w_id"] = f"W{i}"

    state.deep_research = {
        "plan": plan,
        "rounds": rounds_meta,
        "findings": ordered,
        "contradictions": contradictions,
        "entities": entities,
        "stats": {
            "rounds": len(rounds_meta),
            "queries": total_queries,
            "pages": total_pages,
            "corroborated": corroborated,
            "academic_overlap": overlaps,
            "tier_counts": {
                tier: sum(1 for f in findings if f["tier"] == tier)
                for tier in ("W-T1", "W-T2", "W-T3")
            },
        },
    }
    state.log("deep_research", "deep research complete",
              findings=len(findings), corroborated=corroborated,
              relevance=plan.get("relevance"), rounds=len(rounds_meta))
    return state

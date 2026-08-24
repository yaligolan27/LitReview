"""Stage 15 — Evaluator (spec §9.15).

Nine weighted metrics → a 0-100 scorecard. Two important decisions from the
spec: measurement is over ``cited_papers`` (the curated selection), not the
raw pool — a focused survey that scans 400 papers and cites the best 30 is
not punished; and EMERGING is worth 0.15, not 0 — an arXiv preprint is a
real but low-tier source.

Below ``SURVEY_SCORE_THRESHOLD`` a visible warning enters the document — but
the document is still produced.
"""

from __future__ import annotations

from ..core.context import RunContext
from ..core.llm import extract_json
from ..core.state import SurveyState

WEIGHTS = {
    "supported_claims": 0.20,
    "source_quality": 0.14,
    "citation_integrity": 0.14,
    "low_unsupported": 0.12,
    "hebrew_quality": 0.09,
    "source_diversity": 0.08,
    "toc_match": 0.08,
    "chart_reliability": 0.08,
    "coherence": 0.07,
}

METRIC_TITLES = {
    "supported_claims": "טענות נתמכות",
    "source_quality": "איכות מקורות",
    "citation_integrity": "תקינות ציטוטים",
    "low_unsupported": "מיעוט לא-נתמכות",
    "hebrew_quality": "איכות עברית",
    "source_diversity": "גיוון מקורות",
    "toc_match": "התאמה לתוכן העניינים",
    "chart_reliability": "אמינות גרפים",
    "coherence": "קוהרנטיות",
}

_CONF_VALUE = {"HIGH": 1.0, "MODERATE": 0.6, "LIMITED": 0.3, "EMERGING": 0.15}


def _clamp(value: float) -> float:
    return max(0.0, min(10.0, value))


def _llm_metrics(ctx: RunContext, state: SurveyState) -> tuple[float, float, str]:
    digest = "\n\n".join(f"## {s.title}\n{s.content[:800]}" for s in state.sections[:8])
    prompt = (
        "דרג את הטקסט הבא (סקירת ספרות בעברית) בשני מדדים 0-10 והחזר JSON "
        '{"hebrew_quality": n, "coherence": n, "notes": "..."}.\n\n' + digest
    )
    try:
        data = extract_json(ctx.llm.complete(prompt, purpose="evaluator"))
        return (float(data.get("hebrew_quality", 5)),
                float(data.get("coherence", 5)),
                str(data.get("notes", "")))
    except (ValueError, TypeError):
        return 5.0, 5.0, "LLM metrics unavailable"


def run_evaluator(ctx: RunContext, state: SurveyState) -> SurveyState:
    g = state.grounding_report
    c = state.citation_report
    pool = state.cited_papers or state.papers   # fallback per spec
    metrics: dict[str, float] = {}

    metrics["supported_claims"] = _clamp(g.get("supported_pct", 0) / 10)

    if pool:
        quality = 10 * sum(_CONF_VALUE.get(p.confidence, 0.15) for p in pool) / len(pool)
        if len(pool) < 5:
            quality *= 0.85
        metrics["source_quality"] = _clamp(quality)
    else:
        metrics["source_quality"] = 0.0

    penalty = (min(4, c.get("dead_citations", 0)) * 0.5
               + min(3, len(c.get("missing_fields", []))) * 0.4
               + min(3, len(c.get("doi_mismatch", []))) * 0.6)
    metrics["citation_integrity"] = _clamp(10 - penalty)

    metrics["low_unsupported"] = _clamp(10 - g.get("unsupported_pct", 0) / 10)

    hebrew, coherence, notes = _llm_metrics(ctx, state)
    metrics["hebrew_quality"] = _clamp(hebrew)
    metrics["coherence"] = _clamp(coherence)

    sources = {p.source for p in pool}
    types = {p.source_type for p in pool if p.source_type}
    metrics["source_diversity"] = _clamp(min(5, len(sources)) + min(3, len(types))
                                         + min(2, len(pool) / 20))

    planned = len(state.toc) or 1
    metrics["toc_match"] = _clamp(10 * len(state.sections) / planned)

    n_charts = len(state.charts)
    if n_charts == 0 and not state.prisma.get("svg"):
        metrics["chart_reliability"] = 3.0
    else:
        metrics["chart_reliability"] = _clamp(7 + min(3, n_charts))

    score = round(sum(WEIGHTS[k] * metrics[k] * 10 for k in WEIGHTS))
    threshold = ctx.settings.score_threshold
    state.scorecard = {
        "score": score,
        "threshold": threshold,
        "below_threshold": score < threshold,
        "metrics": {k: round(v, 1) for k, v in metrics.items()},
        "weights": WEIGHTS,
        "titles": METRIC_TITLES,
        "notes": notes,
    }
    state.log("evaluate", "scorecard computed", score=score,
              below_threshold=score < threshold)
    return state

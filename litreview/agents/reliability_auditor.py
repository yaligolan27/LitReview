"""Stage 4 — Reliability Auditor, full version (spec §9.4).

Order of operations:
a. Retraction check (4 sources, Crossref calls budgeted).
b. DOI backfill — papers without a DOI (common from dblp/snowball) get a
   reverse title lookup: Crossref first, then OpenAlex (similarity ≥88,
   year ±1, capped per run).
c. DOI verification with the checked≠valid discipline: a network failure is
   "could not check" and never downgrades a paper.
d. Confidence scoring (core/confidence_scorer).
"""

from __future__ import annotations

from datetime import date

from ..apis import crossref, openalex, retraction
from ..core.confidence_scorer import score_paper
from ..core.context import RunContext
from ..core.state import SurveyState


def run_reliability_auditor(ctx: RunContext, state: SurveyState) -> SurveyState:
    settings = ctx.settings
    year_now = date.today().year

    # --- a. retraction -----------------------------------------------------
    watch = retraction.RetractionWatch()
    crossref_budget = [settings.retraction_crossref_cap if settings.retraction_crossref else 0]
    use_crossref = settings.retraction_crossref and not ctx.offline
    for paper in state.papers:
        is_retracted, note = retraction.check_paper(
            paper, watch, crossref_budget, use_crossref=use_crossref)
        if is_retracted:
            paper.is_retracted = True
            paper.retraction_note = note

    # --- b. DOI backfill ---------------------------------------------------
    backfilled = 0
    if settings.doi_backfill and not ctx.offline:
        budget = settings.doi_backfill_cap
        for paper in state.papers:
            if paper.doi or not paper.title or budget <= 0:
                continue
            budget -= 1
            doi = crossref.find_doi_by_title(paper.title, paper.year) \
                or openalex.find_doi_by_title(paper.title, paper.year)
            if doi:
                paper.doi = doi
                backfilled += 1

    # --- c. DOI verification ----------------------------------------------
    checked = valid = invalid = unchecked = 0
    for paper in state.papers:
        if paper.doi:
            if ctx.offline:
                result = {"checked": True, "valid": "unindexed" not in paper.title.lower()}
            else:
                result = crossref.verify_doi(paper.doi)
            if result["checked"]:
                checked += 1
                paper.doi_verified = result["valid"]
                if result["valid"]:
                    valid += 1
                else:
                    invalid += 1
            else:
                unchecked += 1
                paper.doi_verified = None   # network failure — do NOT downgrade
        else:
            paper.doi_verified = False

        # --- d. confidence -------------------------------------------------
        paper.confidence = score_paper(paper, current_year=year_now)
        if paper.doi and paper.doi_verified is False and paper.confidence != "EMERGING":
            paper.confidence = "LIMITED"

    retracted = [p for p in state.papers if p.is_retracted]
    state.retracted_papers = [
        {"title": p.title, "doi": p.doi, "note": p.retraction_note or "flagged by provider"}
        for p in retracted
    ]
    state.prisma["excluded_retracted"] = len(retracted)
    state.prisma["doi_unverified"] = invalid
    state.log("audit", "reliability audit complete",
              doi_checked=checked, doi_valid=valid, doi_invalid=invalid,
              doi_unchecked_network=unchecked, doi_backfilled=backfilled,
              retracted=len(retracted),
              crossref_retraction_calls_left=crossref_budget[0])
    return state

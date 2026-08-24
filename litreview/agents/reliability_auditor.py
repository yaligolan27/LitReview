"""Stage 4 — Reliability Auditor (spec §9.4).

M1 scope: DOI verification with the checked≠valid discipline, and confidence
scoring. Retraction checks (4 sources) and DOI backfill land in M2 — papers
already flagged retracted by their provider (OpenAlex) are honored now.
"""

from __future__ import annotations

from datetime import date

from ..apis import crossref
from ..core.confidence_scorer import score_paper
from ..core.context import RunContext
from ..core.state import SurveyState


def run_reliability_auditor(ctx: RunContext, state: SurveyState) -> SurveyState:
    year_now = date.today().year
    checked = valid = invalid = unchecked = 0

    for paper in state.papers:
        if paper.doi:
            if ctx.offline:
                # Mock mode: deterministic, no network (spec §7.5).
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

        paper.confidence = score_paper(paper, current_year=year_now)
        # A DOI that was checked and NOT found demotes the paper (spec §9.4c).
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
              doi_unchecked_network=unchecked, retracted=len(retracted))
    return state

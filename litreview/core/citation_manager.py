"""Global citation numbering — spec §9.12 (core/citation_manager.py).

The Writer works with per-chapter local numbers ([1]..[8] restarting every
chapter). This module makes the numbering global and honest in three passes:

* Pass 1 — global registry with provisional numbers, merging duplicates
  (key: normalized DOI, else normalized title, else object id).
* Pass 2 — per section, map local [n] → provisional; a number with no
  mapping is a dead citation: the marker is removed and reported.
* Pass 3 — final numbering 1..M over provisional numbers that were actually
  cited (registration order); the bibliography contains only cited papers;
  papers assigned to chapters but never cited are dropped and counted.

Web citations [W#] belong to the deep-research layer and are never touched.
"""

from __future__ import annotations

import re
from typing import Any

from .citation_formatter import format_apa
from .dedup import normalize_doi, normalize_title
from .state import Paper, SurveyState

# Academic cite token: digits with commas/ranges only — never [W3], never [CALLOUT].
_CITE_TOKEN = re.compile(r"\[(\d+(?:\s*[-–,]\s*\d+)*)\]")
_PLACEHOLDER = "\x00CITE{}\x00"


def _key(paper: Paper) -> str:
    doi = normalize_doi(paper.doi)
    if doi:
        return f"doi:{doi}"
    title = normalize_title(paper.title)
    if title:
        return f"title:{title}"
    return f"id:{id(paper)}"


def _parse_numbers(token: str) -> list[int]:
    numbers: list[int] = []
    for part in token.split(","):
        part = part.strip().replace("–", "-")
        if "-" in part:
            try:
                lo, hi = (int(x) for x in part.split("-", 1))
            except ValueError:
                continue
            if hi >= lo and hi - lo <= 50:
                numbers.extend(range(lo, hi + 1))
        else:
            try:
                numbers.append(int(part))
            except ValueError:
                continue
    return numbers


def _compress(numbers: list[int]) -> str:
    """[1,2,3,5] → "1-3,5" (runs of ≥3 become ranges)."""
    if not numbers:
        return ""
    out: list[str] = []
    run_start = prev = numbers[0]
    for n in numbers[1:] + [None]:  # type: ignore[list-item]
        if n is not None and n == prev + 1:
            prev = n
            continue
        if prev - run_start >= 2:
            out.append(f"{run_start}-{prev}")
        elif prev != run_start:
            out.extend([str(run_start), str(prev)])
        else:
            out.append(str(run_start))
        if n is not None:
            run_start = prev = n
    return ",".join(out)


def run_citation_manager(ctx: Any, state: SurveyState) -> SurveyState:
    report: dict[str, Any] = {
        "entries": 0,
        "dead_citations": 0,
        "uncited_dropped": 0,
        "duplicate_sources_merged": 0,
        "missing_fields": [],
        "doi_mismatch": [],
    }

    # --- Pass 1: global provisional registry -------------------------------
    registry: dict[str, dict[str, Any]] = {}
    next_prov = 1
    for sec in state.sections:
        for paper in sec.papers:
            key = _key(paper)
            if key in registry:
                if registry[key]["paper"] is not paper:
                    report["duplicate_sources_merged"] += 1
                continue
            registry[key] = {"prov": next_prov, "paper": paper}
            next_prov += 1

    # --- Pass 2: rewrite local numbers to provisional placeholders ---------
    cited_provs: set[int] = set()
    section_provs: list[set[int]] = []
    for sec in state.sections:
        mapping = {i + 1: registry[_key(p)]["prov"] for i, p in enumerate(sec.papers)}
        used: set[int] = set()

        def rewrite(match: re.Match) -> str:
            local_numbers = _parse_numbers(match.group(1))
            provs = []
            for n in local_numbers:
                prov = mapping.get(n)
                if prov is None:
                    report["dead_citations"] += 1
                else:
                    provs.append(prov)
            if not provs:
                return ""  # dead citation: marker removed entirely
            used.update(provs)
            return _PLACEHOLDER.format(",".join(str(p) for p in sorted(set(provs))))

        sec.content = _CITE_TOKEN.sub(rewrite, sec.content)
        cited_provs.update(used)
        section_provs.append(used)

    # --- Pass 3: final numbering over cited provisionals -------------------
    final_map = {prov: i + 1 for i, prov in enumerate(sorted(cited_provs))}
    prov_to_paper = {entry["prov"]: entry["paper"] for entry in registry.values()}

    placeholder_re = re.compile("\x00CITE([0-9,]+)\x00")
    for sec in state.sections:
        def finalize(match: re.Match) -> str:
            provs = [int(x) for x in match.group(1).split(",")]
            finals = sorted(final_map[p] for p in provs if p in final_map)
            return f"[{_compress(finals)}]" if finals else ""

        sec.content = placeholder_re.sub(finalize, sec.content)

    state.executive_summary = _strip_out_of_range(
        state.executive_summary, max_n=len(final_map))

    # Bibliography = cited papers only, in final order.
    bibliography: list[Paper] = []
    for prov in sorted(cited_provs):
        paper = prov_to_paper[prov]
        if not paper.apa:
            paper.apa = format_apa(paper)
        bibliography.append(paper)
    state.cited_papers = bibliography
    report["entries"] = len(bibliography)
    report["uncited_dropped"] = len(registry) - len(bibliography)

    for paper in bibliography:
        missing = paper.key_fields_missing()
        if missing:
            report["missing_fields"].append({"title": paper.title[:80], "missing": missing})

    # Sync per-section APA lists to the final numbering (used by DOCX).
    for sec, used in zip(state.sections, section_provs):
        finals = sorted(final_map[p] for p in used if p in final_map)
        by_final = {final_map[prov]: prov_to_paper[prov] for prov in used if prov in final_map}
        sec.citations = [f"[{n}] {format_apa(by_final[n])}" for n in finals]

    state.citation_report = report
    state.log("citations", "global renumbering complete",
              entries=report["entries"], dead=report["dead_citations"],
              uncited_dropped=report["uncited_dropped"])
    return state


def _strip_out_of_range(text: str, max_n: int) -> str:
    if not text:
        return text

    def check(match: re.Match) -> str:
        numbers = [n for n in _parse_numbers(match.group(1)) if 1 <= n <= max_n]
        return f"[{_compress(sorted(set(numbers)))}]" if numbers else ""

    return _CITE_TOKEN.sub(check, text)

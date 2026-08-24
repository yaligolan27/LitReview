"""APA 7 formatting — spec §10 (core/citation_formatter.py)."""

from __future__ import annotations

import re

from .state import Paper


def _to_family_initials(name: str) -> str:
    """Normalize an author display name to APA "Family, I." form.

    Accepts "Family, Given", "Given Family", or "Family, G." already.
    Hebrew (or other non-Latin) names are returned as-is minus extra spaces.
    """
    name = re.sub(r"\s+", " ", (name or "").strip())
    if not name:
        return ""
    if not re.search(r"[A-Za-z]", name):
        return name  # e.g. Hebrew names — leave untouched
    if "," in name:
        family, _, rest = name.partition(",")
        given = rest.strip()
    else:
        parts = name.split(" ")
        if len(parts) == 1:
            return parts[0]
        family, given = parts[-1], " ".join(parts[:-1])
    initials = " ".join(
        f"{token[0].upper()}." for token in re.split(r"[\s\-]+", given)
        if token and token[0].isalpha()
    )
    family = family.strip()
    return f"{family}, {initials}" if initials else family


def _family_only(name: str) -> str:
    formatted = _to_family_initials(name)
    return formatted.split(",")[0].strip()


def format_authors(authors: list[str]) -> str:
    formatted = [_to_family_initials(a) for a in authors if a and a.strip()]
    formatted = [f for f in formatted if f]
    if not formatted:
        return ""
    if len(formatted) == 1:
        return formatted[0]
    if len(formatted) <= 20:
        return ", ".join(formatted[:-1]) + ", & " + formatted[-1]
    return ", ".join(formatted[:19]) + ", ... " + formatted[-1]


def format_apa(paper: Paper) -> str:
    authors = format_authors(paper.authors)
    year = f"({paper.year})" if paper.year else "(n.d.)"
    title = (paper.title or "").rstrip(".")
    parts = []
    if authors:
        parts.append(f"{authors} {year}.")
    else:
        parts.append(f"{title}. {year}.")
    if authors:
        parts.append(f"{title}.")
    if paper.journal:
        parts.append(f"*{paper.journal}*.")
    if paper.doi:
        doi = paper.doi if paper.doi.startswith("http") else f"https://doi.org/{paper.doi}"
        parts.append(doi)
    elif paper.url:
        parts.append(paper.url)
    return " ".join(parts).strip()


def format_inline(paper: Paper) -> str:
    year = paper.year or "n.d."
    families = [_family_only(a) for a in paper.authors if a and a.strip()]
    families = [f for f in families if f]
    if not families:
        return f"({year})"
    if len(families) == 1:
        return f"({families[0]}, {year})"
    if len(families) == 2:
        return f"({families[0]} & {families[1]}, {year})"
    return f"({families[0]} et al., {year})"

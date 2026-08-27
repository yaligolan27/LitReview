"""Offline provider used when the mock LLM backend is active.

Spec §7.5: "כל הצינור רץ בלי רשת" — so search itself must also be network-free
in mock mode. Papers are deterministic per query, include the query terms in
titles/abstracts (so keyword-based chapter assignment finds them), and cover
the interesting cases: high/low citations, a preprint, a Hebrew-language
paper, a paper with no DOI, and a retracted paper (used from M2 on).
"""

from __future__ import annotations

import hashlib

from ..core.state import Paper


def _h(query: str, i: int) -> int:
    return int(hashlib.sha1(f"{query}|{i}".encode()).hexdigest()[:6], 16)


_TEMPLATES = [
    # (title suffix, source_type, journal, base citations, language, has_doi)
    ("A Systematic Review", "journal-article", "Journal of Systematic Studies", 240, "en", True),
    ("Methods and Evaluation Frameworks", "journal-article", "Methods Quarterly", 96, "en", True),
    ("An Empirical Study", "journal-article", "Empirical Research Letters", 41, "en", True),
    ("Recent Advances and Open Problems", "review", "Annual Reviews", 310, "en", True),
    ("A Comparative Analysis", "proceedings-article", "Proc. Intl. Conference", 18, "en", True),
    ("Emerging Directions", "preprint", "arXiv", 4, "en", True),
    ("סקירה יישומית בעברית", "journal-article", "כתב עת ישראלי למחקר", 7, "he", True),
    ("Industrial Perspectives", "report", "Institute Report", 12, "en", True),
    ("Early Results (unindexed)", "journal-article", "Regional Bulletin", 2, "en", False),
    ("Foundations and Theory", "journal-article", "Theoretical Foundations", 155, "en", True),
    ("Case Studies from Practice", "journal-article", "Practice & Policy", 28, "en", True),
    ("A Retracted Claim Revisited", "journal-article", "Journal of Corrections", 63, "en", True),
]


def search(query: str, limit: int = 5,
           year_from: int | None = None, year_to: int | None = None) -> list[Paper]:
    year_from = year_from or 2016
    year_to = year_to or 2026
    span = max(1, year_to - year_from)
    papers: list[Paper] = []
    base = query.strip().rstrip(".")
    for i, (suffix, source_type, journal, cites, lang, has_doi) in enumerate(_TEMPLATES):
        seed = _h(base, i)
        year = year_from + (seed % (span + 1))
        title = f"{base}: {suffix}" if lang != "he" else f"{suffix}: {base}"
        doi = f"10.1000/mock.{seed % 100000}" if has_doi else ""
        papers.append(Paper(
            id=f"mock:{seed}",
            title=title,
            abstract=(f"This study examines {base} in depth, reporting methods, "
                      f"results and limitations relevant to {base}."),
            year=year,
            authors=[f"Author{(seed + j) % 50}, A." for j in range(1 + seed % 3)],
            journal=journal,
            citation_count=cites + seed % 9,
            doi=doi,
            url=f"https://example.org/paper/{seed}",
            source="mockdb",
            tier="T3" if source_type == "preprint" else "T1",
            language=lang,
            source_type=source_type,
            is_retracted=(suffix == "A Retracted Claim Revisited"),
            retraction_note="Retracted 2024 (data error)" if suffix == "A Retracted Claim Revisited" else "",
            is_open_access=bool(seed % 2),
        ))
    return papers[:max(1, limit * 2)]

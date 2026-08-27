"""BibTeX / RIS export of the cited bibliography (project addition)."""

from __future__ import annotations

import re

from ..core.state import Paper

_TYPE_TO_BIBTEX = {
    "journal-article": "article", "review": "article", "review-article": "article",
    "proceedings-article": "inproceedings", "conference": "inproceedings",
    "book-chapter": "incollection", "preprint": "misc", "report": "techreport",
    "dataset": "misc",
}
_TYPE_TO_RIS = {
    "journal-article": "JOUR", "review": "JOUR", "review-article": "JOUR",
    "proceedings-article": "CPAPER", "conference": "CPAPER",
    "book-chapter": "CHAP", "preprint": "UNPB", "report": "RPRT",
    "dataset": "DATA",
}


def _bib_key(paper: Paper, index: int) -> str:
    family = ""
    if paper.authors:
        family = re.sub(r"[^A-Za-z]", "", paper.authors[0].split(",")[0])
    return f"{family or 'ref'}{paper.year or ''}_{index}"


def _bib_escape(text: str) -> str:
    return text.replace("{", "\\{").replace("}", "\\}").replace("&", "\\&")


def to_bibtex(papers: list[Paper]) -> str:
    entries = []
    for i, p in enumerate(papers, start=1):
        entry_type = _TYPE_TO_BIBTEX.get(p.source_type, "misc")
        fields = {
            "title": _bib_escape(p.title),
            "author": " and ".join(p.authors) if p.authors else "",
            "year": str(p.year or ""),
            "journal": _bib_escape(p.journal) if entry_type == "article" else "",
            "booktitle": _bib_escape(p.journal) if entry_type == "inproceedings" else "",
            "doi": p.doi,
            "url": p.url if not p.doi else "",
        }
        body = ",\n".join(f"  {k} = {{{v}}}" for k, v in fields.items() if v)
        entries.append(f"@{entry_type}{{{_bib_key(p, i)},\n{body}\n}}")
    return "\n\n".join(entries) + "\n"


def to_ris(papers: list[Paper]) -> str:
    entries = []
    for p in papers:
        lines = [f"TY  - {_TYPE_TO_RIS.get(p.source_type, 'GEN')}",
                 f"TI  - {p.title}"]
        lines.extend(f"AU  - {a}" for a in p.authors)
        if p.year:
            lines.append(f"PY  - {p.year}")
        if p.journal:
            lines.append(f"JO  - {p.journal}")
        if p.doi:
            lines.append(f"DO  - {p.doi}")
        if p.url:
            lines.append(f"UR  - {p.url}")
        lines.append("ER  - ")
        entries.append("\n".join(lines))
    return "\n".join(entries) + "\n"

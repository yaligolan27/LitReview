"""Stage 5 — Full-text retrieval (spec §9.5, core/fulltext.py).

Chain: Europe PMC JATS full text → Unpaywall / provider PDF → text
extraction (PyMuPDF or pypdf — optional installs) → chunking (1200 chars,
150 overlap) → top-4 chunks by topic-term relevance.

Always returns a dict (never raises to the orchestrator); papers gain
``has_fulltext`` + ``fulltext_excerpt``, which switch the Writer's
evidence-base instruction (strong claims vs. cautious wording).
"""

from __future__ import annotations

import re

from ..apis import _http, europepmc, unpaywall
from .context import RunContext
from .state import Paper, SurveyState

CHUNK_SIZE = 1200
CHUNK_OVERLAP = 150
TOP_CHUNKS = 4
MIN_JATS_CHARS = 800


def _clean_jats(xml_text: str) -> str:
    for tag in ("table-wrap", "ref-list", "fig", "front", "back"):
        xml_text = re.sub(rf"<{tag}\b.*?</{tag}>", " ", xml_text, flags=re.DOTALL)
    text = re.sub(r"<[^>]+>", " ", xml_text)
    return re.sub(r"\s+", " ", text).strip()


def _extract_pdf_text(data: bytes) -> str:
    try:
        import pymupdf
        with pymupdf.open(stream=data, filetype="pdf") as doc:
            return " ".join(page.get_text("text") for page in doc)
    except ImportError:
        pass
    except Exception:  # noqa: BLE001 - malformed PDF
        return ""
    try:
        import io

        import pypdf
        reader = pypdf.PdfReader(io.BytesIO(data))
        return " ".join((page.extract_text() or "") for page in reader.pages)
    except ImportError:
        return ""
    except Exception:  # noqa: BLE001
        return ""


def chunk_text(text: str, size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> list[str]:
    chunks: list[str] = []
    step = max(1, size - overlap)
    for start in range(0, len(text), step):
        chunk = text[start:start + size]
        if len(chunk) < 200 and chunks:
            break
        chunks.append(chunk)
    return chunks


def select_chunks(chunks: list[str], topic_terms: list[str],
                  top_n: int = TOP_CHUNKS) -> list[str]:
    terms = [t.lower() for t in topic_terms if len(t) >= 3]
    scored = []
    for i, chunk in enumerate(chunks):
        lowered = chunk.lower()
        score = sum(lowered.count(term) for term in terms)
        scored.append((score, -i, chunk))
    scored.sort(reverse=True)
    winners = [chunk for score, _, chunk in scored[:top_n] if score > 0]
    return winners or chunks[:top_n]


def _topic_terms(state: SurveyState) -> list[str]:
    terms = re.findall(r"[A-Za-z]{3,}", state.brief.search_topic)
    for sub in state.brief.subtopics:
        terms.extend(re.findall(r"[A-Za-z]{3,}", sub))
    return terms


def _fetch_fulltext(paper: Paper) -> str:
    jats = europepmc.find_fulltext_xml(doi=paper.doi, title=paper.title)
    if jats:
        text = _clean_jats(jats)
        if len(text) > MIN_JATS_CHARS:
            return text
    pdf_url = paper.pdf_url or (unpaywall.best_pdf_url(paper.doi) if paper.doi else "")
    if pdf_url:
        try:
            data = _http.get_bytes(pdf_url)
        except (_http.NetworkError, _http.NotFoundError):
            return ""
        return _extract_pdf_text(data)
    return ""


def run_fulltext(ctx: RunContext, state: SurveyState) -> dict:
    settings = ctx.settings
    result = {"attempted": 0, "with_fulltext": 0}
    if not settings.enable_fulltext or settings.fulltext_max_papers <= 0:
        state.log("fulltext", "full-text retrieval disabled")
        return result

    # Priority: open-access papers with a DOI first (spec §9.5).
    candidates = sorted(
        [p for p in state.papers if not p.is_retracted],
        key=lambda p: (p.is_open_access and bool(p.doi), bool(p.doi),
                       p.citation_count),
        reverse=True,
    )[:settings.fulltext_max_papers]
    terms = _topic_terms(state)

    for paper in candidates:
        result["attempted"] += 1
        if ctx.offline:
            # Mock mode: deterministic offline excerpts for the two strongest
            # candidates, so the Writer's full-text path is exercised.
            if result["with_fulltext"] < 2:
                paper.has_fulltext = True
                paper.fulltext_excerpt = (
                    f"Methods: the study examined {state.brief.search_topic} using a "
                    f"controlled design. Results: consistent improvements were observed "
                    f"across settings. Limitations: sample size and external validity.")
                result["with_fulltext"] += 1
            continue
        text = _fetch_fulltext(paper)
        if not text:
            continue
        chunks = select_chunks(chunk_text(text), terms)
        if chunks:
            paper.has_fulltext = True
            paper.fulltext_excerpt = "\n---\n".join(chunks)[:6000]
            result["with_fulltext"] += 1

    state.log("fulltext", "full-text retrieval complete", **result)
    return result

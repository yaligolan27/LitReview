from litreview import config
from litreview.core.context import RunContext
from litreview.core.events import NullEmitter
from litreview.core.fulltext import (
    _clean_jats,
    chunk_text,
    run_fulltext,
    select_chunks,
)
from litreview.core.llm import LLM
from litreview.core.state import Paper, ResearchBrief, SurveyState


def test_clean_jats_strips_tables_refs_figures():
    xml = ("<article><front>meta</front><body><p>Real content here.</p>"
           "<table-wrap><td>numbers</td></table-wrap>"
           "<fig>figure caption</fig></body>"
           "<back><ref-list><ref>Smith 2020</ref></ref-list></back></article>")
    text = _clean_jats(xml)
    assert "Real content here." in text
    assert "numbers" not in text and "figure caption" not in text
    assert "Smith 2020" not in text


def test_chunking_size_and_overlap():
    text = "abcdefghij" * 300   # 3000 chars
    chunks = chunk_text(text, size=1200, overlap=150)
    assert all(len(c) <= 1200 for c in chunks)
    assert chunks[0][-150:] == chunks[1][:150]   # overlap preserved


def test_select_chunks_prefers_topic_terms():
    chunks = ["nothing relevant at all", "solid rocket motor propulsion data",
              "more filler text"]
    winners = select_chunks(chunks, ["rocket", "propulsion"], top_n=1)
    assert winners == ["solid rocket motor propulsion data"]


def test_offline_run_marks_papers(tmp_path):
    settings = config.get_settings()
    ctx = RunContext(settings=settings, llm=LLM(settings, bridge_dir=tmp_path),
                     workdir=tmp_path, emitter=NullEmitter())
    state = SurveyState(brief=ResearchBrief(topic="ט", search_topic="rocket motors"))
    state.papers = [Paper(id=f"p{i}", title=f"Paper {i}", doi=f"10.1/{i}",
                          is_open_access=True, citation_count=i) for i in range(5)]
    result = run_fulltext(ctx, state)
    assert result["with_fulltext"] == 2
    marked = [p for p in state.papers if p.has_fulltext]
    assert len(marked) == 2 and all(p.fulltext_excerpt for p in marked)

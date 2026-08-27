from litreview import config
from litreview.agents.executive_translator import parse_kpi_data
from litreview.agents.visualizer import run_visualizer
from litreview.core.context import RunContext
from litreview.core.events import NullEmitter
from litreview.core.llm import LLM
from litreview.core.state import Paper, SurveySection, SurveyState


def test_parse_kpi_data():
    text = ("[KPI_DATA]NUM: 47|LABEL: מקורות|DESC: שנותחו|CITE: [1][/KPI_DATA]"
            "[KPI_DATA]NUM: 68%|LABEL: עדכניות|DESC: תיאור|CITE: [2,3][/KPI_DATA]"
            "[KPI_DATA]LABEL: חסר NUM|DESC: לא ייכלל[/KPI_DATA]")
    boxes = parse_kpi_data(text)
    assert len(boxes) == 2
    assert boxes[0] == {"num": "47", "label": "מקורות", "desc": "שנותחו", "cite": "[1]"}
    assert boxes[1]["cite"] == "[2,3]"


def test_visualizer_builds_five_charts(tmp_path):
    settings = config.get_settings()
    ctx = RunContext(settings=settings, llm=LLM(settings, bridge_dir=tmp_path),
                     workdir=tmp_path, emitter=NullEmitter())
    state = SurveyState()
    state.cited_papers = [
        Paper(id=f"p{i}", title=f"t{i}", year=2019 + i % 5,
              confidence=["HIGH", "MODERATE", "LIMITED", "EMERGING"][i % 4],
              source_type=["journal-article", "preprint", "report"][i % 3])
        for i in range(12)]
    state.sections = [SurveySection(title="פרק א", papers=state.cited_papers[:5]),
                      SurveySection(title="פרק ב", papers=state.cited_papers[5:])]
    state.prisma = {"identified": 100, "duplicates_removed": 40, "after_dedup": 60,
                    "excluded_retracted": 1, "doi_unverified": 2}
    run_visualizer(ctx, state)

    titles = [c["title"] for c in state.charts]
    assert titles == ["פרסומים לפי שנה", "התפלגות סוגי מקורות",
                      "רמות אמינות המקורות", "מקורות לפי פרק", "PRISMA"]
    for chart in state.charts:
        assert chart["svg"].startswith("<svg")
    assert state.prisma["svg"].startswith("<svg")


def test_visualizer_empty_pool_safe(tmp_path):
    settings = config.get_settings()
    ctx = RunContext(settings=settings, llm=LLM(settings, bridge_dir=tmp_path),
                     workdir=tmp_path, emitter=NullEmitter())
    state = SurveyState()
    run_visualizer(ctx, state)   # must not raise
    assert any(c["title"] == "PRISMA" for c in state.charts)

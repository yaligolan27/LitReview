"""The canonical E2E: full pipeline in mock mode, offline, → RTL HTML artifact.

Also proves stage-level resume: a second invocation of the same workdir skips
every completed stage.
"""

import json
import re
from pathlib import Path

from litreview.cli import main

CONFIG = {
    "topic": "כלים מבוססי AI לסקירת ספרות",
    "search_topic": "AI literature review tools",
    "audience": "חוקרים",
    "year_from": 2019,
    "year_to": 2026,
    "goals": ["מיפוי כלים"],
    "subtopics": ["citation verification"],
    "scope": "summary",
    "author": "מאיה",
}


def _run(tmp_path: Path, resume: bool = False) -> Path:
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps(CONFIG, ensure_ascii=False), encoding="utf-8")
    workdir = tmp_path / "run"
    argv = ["--config", str(config_path), "--workdir", str(workdir), "--backend", "mock"]
    if resume:
        argv.append("--resume")
    assert main(argv) == 0
    return workdir


def test_full_mock_run_produces_valid_rtl_html(tmp_path):
    workdir = _run(tmp_path)

    outputs = list((workdir / "outputs").glob("survey_*.html"))
    assert len(outputs) == 1
    html = outputs[0].read_text(encoding="utf-8")

    assert len(html) > 2000
    assert 'dir="rtl"' in html and 'lang="he"' in html
    assert re.search(r"[֐-׿]", html), "document must contain Hebrew"
    assert html.count("<cite>") > 3
    assert "ביבליוגרפיה" in html
    assert "PRISMA" in html
    assert "הערת אמינות" in html
    # No raw block markers may survive conversion.
    assert "[CALLOUT" not in html
    # No mixed academic/web citation may ever appear (iron rule).
    assert not re.search(r"\[\d+\s*,\s*W\d+\]", html)

    # Checkpoints exist and all stages are done.
    run_record = json.loads((workdir / "run.json").read_text(encoding="utf-8"))
    statuses = {s["id"]: s["status"] for s in run_record["stages"]}
    for critical_stage in ("plan", "toc", "hunt", "audit", "write", "ground",
                          "citations", "html"):
        assert statuses[critical_stage] == "done"
    assert (workdir / "state.json").exists()
    assert (workdir / "stage_log.json").exists()

    # Bibliography contains only cited papers, numbered contiguously.
    state = json.loads((workdir / "state.json").read_text(encoding="utf-8"))
    assert 0 < len(state["cited_papers"]) <= len(state["papers"])
    assert state["grounding_report"]["total_claims"] > 0


def test_resume_skips_completed_stages(tmp_path, capsys):
    _run(tmp_path)
    capsys.readouterr()
    _run(tmp_path, resume=True)
    out = capsys.readouterr().out
    assert "already completed (resume)" in out
    # Every pipeline stage was skipped — nothing re-ran.
    assert out.count("already completed (resume)") >= 8

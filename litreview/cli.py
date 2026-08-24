"""CLI entry point: ``python run_pipeline.py --config my_survey.json``."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

from . import config as config_module
from .core import orchestrator
from .core.checkpoints import Checkpointer, RunRecord
from .core.context import RunContext
from .core.events import StdoutEmitter
from .core.llm import LLM
from .core.state import SurveyState


def _slug(text: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9]+", "-", text).strip("-").lower()
    return slug[:48] or "survey"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="litreview",
        description="Generate an academic literature survey (real sources, verified claims).")
    parser.add_argument("--config", help="JSON config file (spec §15.2)")
    parser.add_argument("--topic", help="Quick start: display topic (Hebrew)")
    parser.add_argument("--search-topic", help="Quick start: English query topic")
    parser.add_argument("--workdir", help="Working directory (checkpoints, bridge, outputs)")
    parser.add_argument("--backend", choices=["native", "mock", "api", "auto"],
                        help="Override SURVEY_LLM_BACKEND")
    parser.add_argument("--until", choices=["toc", "sources", "draft"],
                        help="Stop at this gate instead of approving it")
    parser.add_argument("--resume", action="store_true",
                        help="Continue from the checkpoints in --workdir")
    parser.add_argument("--interactive", action="store_true",
                        help="Run the planner interview on a TTY")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    if args.backend:
        os.environ["SURVEY_LLM_BACKEND"] = args.backend
        config_module.reset_settings()
    settings = config_module.get_settings()

    if args.config:
        cfg = json.loads(Path(args.config).read_text(encoding="utf-8"))
    elif args.interactive:
        from .agents.research_planner import interactive_interview
        cfg = interactive_interview()
    elif args.topic:
        cfg = {"topic": args.topic, "search_topic": args.search_topic or args.topic}
    else:
        print("error: pass --config, --topic or --interactive", file=sys.stderr)
        return 2

    workdir = Path(args.workdir) if args.workdir else \
        Path("var/runs") / _slug(cfg.get("search_topic") or cfg.get("topic", "survey"))
    workdir.mkdir(parents=True, exist_ok=True)

    # A unique bridge dir per run unless the operator pinned one explicitly
    # (fixes the parallel-runs trap from spec §16).
    bridge_dir = os.environ.get("SURVEY_BRIDGE_DIR") or str(workdir / "bridge")

    checkpointer = Checkpointer(workdir)
    state = run_record = None
    if args.resume:
        state = checkpointer.load_state()
        run_record = checkpointer.load_run()
        if state is None:
            print(f"nothing to resume in {workdir} — starting fresh")
    state = state or SurveyState()
    run_record = run_record or RunRecord(run_id=_slug(str(workdir.name)),
                                         backend=settings.llm_backend,
                                         bridge_dir=bridge_dir)

    ctx = RunContext(settings=settings,
                     llm=LLM(settings, bridge_dir=bridge_dir),
                     workdir=workdir,
                     emitter=StdoutEmitter())

    if settings.llm_backend == "mock":
        gate_policy: orchestrator.GatePolicy = orchestrator.AutoApprovePolicy()
    else:
        gate_policy = orchestrator.BridgeGatePolicy()

    stages = orchestrator.build_stages(cfg)
    print(f"litreview · backend={settings.llm_backend} · workdir={workdir}")
    try:
        outcome = orchestrator.run(ctx, state, run_record, checkpointer,
                                   gate_policy, stages, until=args.until)
    except orchestrator.GateReached as gate:  # pragma: no cover - defensive
        outcome = f"paused:{gate.gate}"
    except Exception as exc:  # noqa: BLE001
        print(f"\n✗ run failed: {exc}", file=sys.stderr)
        print(f"  checkpoints kept in {workdir} — rerun with --resume", file=sys.stderr)
        return 1

    if outcome == "done":
        outputs = sorted((workdir / "outputs").glob("*")) if (workdir / "outputs").exists() else []
        print("\n✅ הסקר הושלם")
        for path in outputs:
            print(f"   → {path}")
    else:
        print(f"\n⏸ {outcome} — continue with --resume after approval")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

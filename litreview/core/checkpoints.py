"""Stage-level checkpointing (improvement over the original tool).

The original resumed runs only through the bridge's response cache. Here the
full ``SurveyState`` plus a run record are written atomically after every
stage, so a crash, a server restart, or a human gate can all resume from the
last completed stage. This is also what the web server persists.
"""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .state import SurveyState

STATE_FILE = "state.json"
RUN_FILE = "run.json"


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=path.name + ".", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, ensure_ascii=False, indent=1)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def read_json(path: Path) -> dict[str, Any] | None:
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except FileNotFoundError:
        return None
    except json.JSONDecodeError:
        return None


@dataclass
class RunRecord:
    """Progress of one pipeline run over its stages and gates."""

    run_id: str = ""
    backend: str = ""
    bridge_dir: str = ""
    stages: list[dict[str, Any]] = field(default_factory=list)
    # gate name -> {"status": "pending"|"approved", "decided_by": str, "at": str, "notes": str}
    gates: dict[str, dict[str, Any]] = field(default_factory=dict)
    updated_at: str = ""

    def stage(self, stage_id: str) -> dict[str, Any]:
        for entry in self.stages:
            if entry["id"] == stage_id:
                return entry
        entry = {"id": stage_id, "status": "pending", "started": "", "ended": "", "error": ""}
        self.stages.append(entry)
        return entry

    def mark(self, stage_id: str, status: str, error: str = "") -> None:
        entry = self.stage(stage_id)
        entry["status"] = status
        if status == "running":
            entry["started"] = _utcnow()
        elif status in ("done", "failed", "skipped"):
            entry["ended"] = _utcnow()
        if error:
            entry["error"] = error
        self.updated_at = _utcnow()

    def is_done(self, stage_id: str) -> bool:
        return self.stage(stage_id)["status"] == "done"

    def invalidate(self, stage_ids: list[str]) -> None:
        for sid in stage_ids:
            entry = self.stage(sid)
            if entry["status"] == "done":
                entry["status"] = "stale"
        self.updated_at = _utcnow()

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "backend": self.backend,
            "bridge_dir": self.bridge_dir,
            "stages": self.stages,
            "gates": self.gates,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "RunRecord":
        return cls(
            run_id=data.get("run_id", ""),
            backend=data.get("backend", ""),
            bridge_dir=data.get("bridge_dir", ""),
            stages=list(data.get("stages", [])),
            gates=dict(data.get("gates", {})),
            updated_at=data.get("updated_at", ""),
        )


class Checkpointer:
    """Persists SurveyState + RunRecord into a working directory."""

    def __init__(self, workdir: str | Path):
        self.workdir = Path(workdir)

    @property
    def state_path(self) -> Path:
        return self.workdir / STATE_FILE

    @property
    def run_path(self) -> Path:
        return self.workdir / RUN_FILE

    def save(self, state: SurveyState, run: RunRecord) -> None:
        atomic_write_json(self.state_path, state.to_dict())
        atomic_write_json(self.run_path, run.to_dict())

    def load_state(self) -> SurveyState | None:
        data = read_json(self.state_path)
        return SurveyState.from_dict(data) if data is not None else None

    def load_run(self) -> RunRecord | None:
        data = read_json(self.run_path)
        return RunRecord.from_dict(data) if data is not None else None

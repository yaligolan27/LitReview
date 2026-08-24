"""Survey storage — JSON-per-survey on disk (plan §4.4).

Layout:
    var/surveys/<sid>/manifest.json
    var/surveys/<sid>/v<N>/{brief.json, state.json, run.json, overlay.json}
    var/surveys/<sid>/v<N>/{bridge/, logs/, outputs/}
    var/operators.json · var/gold.json

``store.py`` is the only module that touches these paths. Atomic writes via
core.checkpoints.atomic_write_json; single-writer-per-survey is enforced by
the job runner, so no DB-grade locking is needed.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ..core.checkpoints import Checkpointer, RunRecord, atomic_write_json, read_json
from ..core.state import SurveyState

STATUSES = ("brief", "toc_pending", "collecting", "sources_pending", "writing",
            "draft_pending", "finalizing", "done", "failed", "archived")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class NotFound(KeyError):
    pass


class SurveyStore:
    def __init__(self, root: str | Path = "var"):
        self.root = Path(root)
        self.surveys_dir = self.root / "surveys"
        self.surveys_dir.mkdir(parents=True, exist_ok=True)

    # --- manifests ---------------------------------------------------------

    def _manifest_path(self, sid: str) -> Path:
        return self.surveys_dir / sid / "manifest.json"

    def get(self, sid: str) -> dict[str, Any]:
        data = read_json(self._manifest_path(sid))
        if data is None:
            raise NotFound(sid)
        return data

    def save_manifest(self, manifest: dict[str, Any]) -> None:
        manifest["updated_at"] = _now()
        atomic_write_json(self._manifest_path(manifest["id"]), manifest)

    def list(self, include_archived: bool = False) -> list[dict[str, Any]]:
        manifests = []
        for path in sorted(self.surveys_dir.glob("*/manifest.json")):
            data = read_json(path)
            if data and (include_archived or not data.get("archived")):
                manifests.append(data)
        manifests.sort(key=lambda m: m.get("updated_at", ""), reverse=True)
        return manifests

    def create(self, topic: str = "", operator: str = "") -> dict[str, Any]:
        sid = uuid.uuid4().hex[:10]
        manifest = {
            "id": sid,
            "topic": topic,
            "operator": operator,
            "created_at": _now(),
            "updated_at": _now(),
            "archived": False,
            "current_version": 1,
            "versions": [{"v": 1, "status": "brief", "created_at": _now()}],
        }
        self.vdir(sid, 1).mkdir(parents=True, exist_ok=True)
        self.save_manifest(manifest)
        return manifest

    def archive(self, sid: str) -> None:
        manifest = self.get(sid)
        manifest["archived"] = True
        self.save_manifest(manifest)

    def new_version(self, sid: str, carry: list[str] | None = None) -> dict[str, Any]:
        manifest = self.get(sid)
        old_v = manifest["current_version"]
        new_v = max(entry["v"] for entry in manifest["versions"]) + 1
        self.vdir(sid, new_v).mkdir(parents=True, exist_ok=True)
        carry = carry or ["brief"]
        if "brief" in carry:
            brief = self.load_brief(sid, old_v)
            if brief:
                self.save_brief(sid, brief, new_v)
        if "toc" in carry or "sources" in carry:
            state = self.load_state(sid, old_v)
            if state is not None:
                fresh = SurveyState(brief=state.brief)
                if "toc" in carry:
                    fresh.toc = state.toc
                if "sources" in carry:
                    fresh.papers = state.papers
                    fresh.dedup_stats = state.dedup_stats
                    fresh.prisma = state.prisma
                    fresh.source_routing = state.source_routing
                    fresh.timeline_years = state.timeline_years
                self.save_state(sid, fresh, new_v)
        manifest["versions"].append({"v": new_v, "status": "brief", "created_at": _now()})
        manifest["current_version"] = new_v
        self.save_manifest(manifest)
        return manifest

    # --- status ------------------------------------------------------------

    def set_status(self, sid: str, status: str) -> None:
        manifest = self.get(sid)
        current = manifest["current_version"]
        for entry in manifest["versions"]:
            if entry["v"] == current:
                entry["status"] = status
        self.save_manifest(manifest)

    def status(self, sid: str) -> str:
        manifest = self.get(sid)
        current = manifest["current_version"]
        for entry in manifest["versions"]:
            if entry["v"] == current:
                return entry.get("status", "brief")
        return "brief"

    # --- paths & documents -------------------------------------------------

    def vdir(self, sid: str, v: int | None = None) -> Path:
        if v is None:
            v = self.get(sid)["current_version"]
        return self.surveys_dir / sid / f"v{v}"

    def checkpointer(self, sid: str, v: int | None = None) -> Checkpointer:
        return Checkpointer(self.vdir(sid, v))

    def load_brief(self, sid: str, v: int | None = None) -> dict[str, Any] | None:
        return read_json(self.vdir(sid, v) / "brief.json")

    def save_brief(self, sid: str, brief: dict[str, Any], v: int | None = None) -> None:
        atomic_write_json(self.vdir(sid, v) / "brief.json", brief)
        manifest = self.get(sid)
        if brief.get("topic"):
            manifest["topic"] = brief["topic"]
            self.save_manifest(manifest)

    def load_state(self, sid: str, v: int | None = None) -> SurveyState | None:
        return self.checkpointer(sid, v).load_state()

    def save_state(self, sid: str, state: SurveyState, v: int | None = None) -> None:
        run = self.load_run(sid, v) or RunRecord()
        self.checkpointer(sid, v).save(state, run)

    def load_run(self, sid: str, v: int | None = None) -> RunRecord | None:
        return self.checkpointer(sid, v).load_run()

    def save_run(self, sid: str, run: RunRecord, v: int | None = None) -> None:
        atomic_write_json(self.vdir(sid, v) / "run.json", run.to_dict())

    def load_overlay(self, sid: str, v: int | None = None) -> dict[str, Any]:
        return read_json(self.vdir(sid, v) / "overlay.json") or \
            {"source_decisions": {}, "pins": {}, "edit_log": []}

    def save_overlay(self, sid: str, overlay: dict[str, Any],
                     v: int | None = None) -> None:
        atomic_write_json(self.vdir(sid, v) / "overlay.json", overlay)

    def outputs_dir(self, sid: str, v: int | None = None) -> Path:
        path = self.vdir(sid, v) / "outputs"
        path.mkdir(parents=True, exist_ok=True)
        return path

    # --- gold & operators --------------------------------------------------

    def gold(self) -> str:
        return (read_json(self.root / "gold.json") or {}).get("survey_id", "")

    def set_gold(self, sid: str) -> None:
        self.get(sid)   # must exist
        atomic_write_json(self.root / "gold.json", {"survey_id": sid})

    def operators(self) -> list[str]:
        return (read_json(self.root / "operators.json") or {}).get("names", [])

    def add_operator(self, name: str) -> list[str]:
        names = self.operators()
        if name and name not in names:
            names.append(name)
            atomic_write_json(self.root / "operators.json", {"names": names})
        return names

    # --- dashboard card ----------------------------------------------------

    def card(self, manifest: dict[str, Any]) -> dict[str, Any]:
        sid = manifest["id"]
        current = manifest["current_version"]
        status = next((e.get("status", "brief") for e in manifest["versions"]
                       if e["v"] == current), "brief")
        run = self.load_run(sid, current)
        state = None
        sources_count = chapters_done = chapters_total = 0
        progress = 0
        if run is not None and run.stages:
            done = sum(1 for s in run.stages if s["status"] == "done")
            progress = round(100 * done / max(1, len(_ALL_STAGES)))
        state = self.load_state(sid, current)
        if state is not None:
            sources_count = len(state.papers)
            chapters_done = len(state.sections)
            chapters_total = len(state.toc)
        if status == "done":
            progress = 100
        return {
            "id": sid,
            "topic": manifest.get("topic") or "סקר ללא שם",
            "status": status,
            "progress_pct": progress,
            "sources_count": sources_count,
            "chapters_done": chapters_done,
            "chapters_total": chapters_total,
            "operator": manifest.get("operator", ""),
            "updated_at": manifest.get("updated_at", ""),
            "gold": self.gold() == sid,
            "current_version": current,
            "versions": [{"v": e["v"], "status": e.get("status", ""),
                          "created_at": e.get("created_at", "")}
                         for e in manifest["versions"]],
        }


from ..core.orchestrator import ALL_STAGE_IDS as _ALL_STAGES  # noqa: E402

"""RunContext — everything an agent needs besides the state itself."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from ..config import Settings
from .events import NullEmitter, ProgressEmitter
from .llm import LLM


@dataclass
class RunContext:
    settings: Settings
    llm: LLM
    workdir: Path
    emitter: ProgressEmitter = field(default_factory=NullEmitter)

    @property
    def offline(self) -> bool:
        """Mock mode runs the entire pipeline with no network (spec §7.5)."""
        return self.settings.llm_backend == "mock"

    def log_line(self, stage: str, message: str, level: str = "info") -> None:
        self.emitter.emit("log", stage=stage, level=level, message=message)

"""The single LLM gateway (spec §6, design decision #3).

Every agent calls ``LLM.complete(prompt, purpose=...)``. No agent imports a
vendor SDK — that is what lets the backend be swapped (native file bridge /
mock / api / auto) without touching any agent.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from ..config import Settings
from . import llm_mock, purposes
from .llm_api import ApiBackend
from .llm_bridge import Bridge, BridgeTimeout, LLMUnavailable

__all__ = ["LLM", "LLMUnavailable", "extract_json"]


class LLM:
    def __init__(self, settings: Settings, bridge_dir: str | Path | None = None):
        self.settings = settings
        self.backend = settings.llm_backend
        self._bridge = Bridge(
            bridge_dir or settings.bridge_dir,
            poll=settings.bridge_poll,
            timeout=settings.bridge_timeout,
        )
        self._api = ApiBackend(settings.api_model, max_retries=settings.api_max_retries)
        self.calls: list[dict] = []   # lightweight telemetry for logs/tests

    @property
    def bridge_dir(self) -> Path:
        return self._bridge.dir

    def complete(self, prompt: str, purpose: str, system: str = "",
                 max_tokens: int | None = None, temperature: float | None = None) -> str:
        spec = purposes.resolve(purpose)
        max_tokens = max_tokens if max_tokens is not None else spec.max_tokens
        temperature = temperature if temperature is not None else spec.temperature

        backend = self.backend
        if backend == "auto":
            import os
            backend = "api" if os.environ.get("ANTHROPIC_API_KEY") else "native"

        if backend == "mock":
            text = llm_mock.complete(prompt, purpose, system)
        elif backend == "api":
            text = self._api.complete(prompt, purpose, system, max_tokens,
                                      temperature, requires_web=spec.requires_web)
        elif backend == "native":
            try:
                text = self._bridge.complete(prompt, purpose, system, max_tokens, temperature)
            except BridgeTimeout:
                # Spec §7.4: timeout falls back to api when a key exists.
                import os
                if os.environ.get("ANTHROPIC_API_KEY"):
                    text = self._api.complete(prompt, purpose, system, max_tokens,
                                              temperature, requires_web=spec.requires_web)
                else:
                    raise
        else:
            raise LLMUnavailable(f"unknown SURVEY_LLM_BACKEND: {backend!r}")

        self.calls.append({"purpose": purpose, "backend": backend, "chars": len(text)})
        return text

    def complete_json(self, prompt: str, purpose: str, system: str = "",
                      max_tokens: int | None = None, temperature: float | None = None):
        """complete() + tolerant JSON extraction (```json fences allowed)."""
        text = self.complete(prompt, purpose, system, max_tokens, temperature)
        return extract_json(text)


def extract_json(text: str):
    """Parse a JSON value out of a model response.

    Accepts clean JSON, ```json fenced blocks, or JSON embedded in prose
    (first balanced object/array). Raises ValueError when nothing parses.
    """
    text = text.strip()
    fence = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL)
    if fence:
        text = fence.group(1).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    # First balanced JSON object or array inside the text.
    for opener, closer in (("{", "}"), ("[", "]")):
        start = text.find(opener)
        while start != -1:
            depth = 0
            in_str = False
            escape = False
            for i in range(start, len(text)):
                ch = text[i]
                if in_str:
                    if escape:
                        escape = False
                    elif ch == "\\":
                        escape = True
                    elif ch == '"':
                        in_str = False
                    continue
                if ch == '"':
                    in_str = True
                elif ch == opener:
                    depth += 1
                elif ch == closer:
                    depth -= 1
                    if depth == 0:
                        try:
                            return json.loads(text[start:i + 1])
                        except json.JSONDecodeError:
                            break
            start = text.find(opener, start + 1)
    raise ValueError(f"no JSON value found in response ({text[:120]!r}...)")

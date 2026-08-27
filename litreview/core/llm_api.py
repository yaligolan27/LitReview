"""The "api" backend — Anthropic SDK.

M1 scope: plain Messages calls. Purposes flagged ``requires_web`` get
Anthropic's server-side web_search/web_fetch tools attached (wired fully in
M5), so deep research works without the file bridge — an improvement over the
original tool, which assumed only the bridge could do real web research.
"""

from __future__ import annotations

import os

from .llm_bridge import LLMUnavailable

# Server-tool type identifiers (see claude-api skill, Server Tools QR).
WEB_SEARCH_TOOL = {"type": "web_search_20260209", "name": "web_search"}
WEB_FETCH_TOOL = {"type": "web_fetch_20260209", "name": "web_fetch"}


class ApiBackend:
    def __init__(self, model: str, max_retries: int = 3):
        self.model = model
        self._client = None
        self._max_retries = max_retries

    def _client_or_raise(self):
        if self._client is None:
            if not os.environ.get("ANTHROPIC_API_KEY") and not os.environ.get("ANTHROPIC_AUTH_TOKEN"):
                raise LLMUnavailable("api backend requested but no Anthropic credentials are set")
            try:
                import anthropic
            except ImportError as exc:
                raise LLMUnavailable(
                    "api backend requested but the 'anthropic' package is not installed "
                    "(pip install 'litreview[api]')"
                ) from exc
            self._client = anthropic.Anthropic(max_retries=self._max_retries)
        return self._client

    def complete(self, prompt: str, purpose: str, system: str = "",
                 max_tokens: int = 1500, temperature: float = 0.3,
                 requires_web: bool = False) -> str:
        client = self._client_or_raise()
        kwargs: dict = {
            "model": self.model,
            "max_tokens": max_tokens,
            "messages": [{"role": "user", "content": prompt}],
        }
        if system:
            kwargs["system"] = system
        if requires_web:
            kwargs["tools"] = [WEB_SEARCH_TOOL, WEB_FETCH_TOOL]

        response = client.messages.create(**kwargs)
        parts = [block.text for block in response.content
                 if getattr(block, "type", "") == "text"]
        return "\n".join(parts).strip()

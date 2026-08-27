"""The file bridge — the "native" backend (spec §7).

The pipeline writes a request file into the bridge directory; the Claude Code
session that runs the skill polls the directory, performs the task (including
real WebSearch/WebFetch for ``dr_*`` purposes), writes ``resp_<id>.txt`` and
an empty ``resp_<id>.done``. Protocol details follow spec §7.4 exactly:

* request id: ``{seq:03d}_{purpose_slug}_{sha1(purpose+prompt)[:10]}``
* poll every ``BRIDGE_POLL`` seconds (default 1.5)
* ready: (``.txt`` and ``.done`` exist) or (``.txt`` exists and the request
  file was deleted); an empty ``.txt`` deletes the ``.done`` and keeps
  waiting (race guard)
* an existing response for the same purpose+prompt hash is returned
  immediately — this is what makes crashed runs resumable. Cache lookup
  matches on the slug+hash suffix (not the sequence number), so stage-level
  resume — where earlier stages are skipped and sequence numbers shift —
  still hits the cache.
* timeout → fall back to the api backend when a key is configured, else
  raise ``LLMUnavailable``.
"""

from __future__ import annotations

import hashlib
import json
import os
import time
from pathlib import Path

from . import purposes


class LLMUnavailable(RuntimeError):
    pass


class BridgeTimeout(LLMUnavailable):
    pass


def request_hash(purpose: str, prompt: str) -> str:
    return hashlib.sha1((purpose + prompt).encode("utf-8")).hexdigest()[:10]


class Bridge:
    def __init__(self, bridge_dir: str | Path, poll: float = 1.5, timeout: float = 900.0):
        self.dir = Path(bridge_dir)
        self.poll = max(0.01, float(poll))
        self.timeout = float(timeout)
        self._seq = 0

    def _next_seq(self) -> int:
        self._seq += 1
        return self._seq

    def _find_cached(self, suffix: str) -> Path | None:
        if not self.dir.is_dir():
            return None
        for path in sorted(self.dir.glob(f"resp_*_{suffix}.txt")):
            try:
                if path.stat().st_size > 0:
                    return path
            except OSError:
                continue
        return None

    def complete(self, prompt: str, purpose: str, system: str = "",
                 max_tokens: int = 1500, temperature: float = 0.3) -> str:
        self.dir.mkdir(parents=True, exist_ok=True)
        p_slug = purposes.slug(purpose)
        h = request_hash(purpose, prompt)
        suffix = f"{p_slug}_{h}"

        cached = self._find_cached(suffix)
        if cached is not None:
            return cached.read_text(encoding="utf-8")

        req_id = f"{self._next_seq():03d}_{suffix}"
        req_path = self.dir / f"req_{req_id}.json"
        resp_path = self.dir / f"resp_{req_id}.txt"
        done_path = self.dir / f"resp_{req_id}.done"

        payload = {
            "id": req_id,
            "purpose": purpose,
            "system": system,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "prompt": prompt,
            "response_file": str(resp_path.resolve()),
        }
        tmp = req_path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
        os.replace(tmp, req_path)

        deadline = time.monotonic() + self.timeout
        while time.monotonic() < deadline:
            if resp_path.exists():
                ready = done_path.exists() or not req_path.exists()
                if ready:
                    text = resp_path.read_text(encoding="utf-8")
                    if text.strip() == "":
                        # Race guard: responder created files but content not
                        # flushed yet — drop the .done and keep waiting.
                        try:
                            done_path.unlink()
                        except FileNotFoundError:
                            pass
                    else:
                        return text
            time.sleep(self.poll)

        raise BridgeTimeout(
            f"bridge request {req_id} timed out after {self.timeout:.0f}s "
            f"(purpose={purpose}); is a Claude Code session serving {self.dir}?"
        )

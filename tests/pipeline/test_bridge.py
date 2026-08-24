"""Bridge protocol tests (spec §7.4): naming, ready condition, race guard,
cache-based resume, and timeout."""

import json
import threading
import time
from pathlib import Path

import pytest

from litreview.core.llm_bridge import Bridge, BridgeTimeout


def _responder(bridge_dir: Path, reply: str, delay: float = 0.05,
               empty_first: bool = False):
    def run():
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            reqs = [p for p in bridge_dir.glob("req_*.json")
                    if not (bridge_dir / f"resp_{p.stem[4:]}.done").exists()]
            for req in reqs:
                req_id = req.stem[4:]
                resp = bridge_dir / f"resp_{req_id}.txt"
                done = bridge_dir / f"resp_{req_id}.done"
                if empty_first and not resp.exists():
                    resp.write_text("", encoding="utf-8")
                    done.write_text("", encoding="utf-8")
                    time.sleep(delay)
                    continue
                resp.write_text(reply, encoding="utf-8")
                done.write_text("", encoding="utf-8")
                return
            time.sleep(0.01)
    thread = threading.Thread(target=run, daemon=True)
    thread.start()
    return thread


def test_request_file_shape_and_response(tmp_path):
    bridge = Bridge(tmp_path, poll=0.02, timeout=5)
    _responder(tmp_path, "תשובה")
    result = bridge.complete("שאלה כלשהי", purpose="dr_round2", system="sys",
                             max_tokens=100, temperature=0.1)
    assert result == "תשובה"
    reqs = list(tmp_path.glob("req_*.json"))
    assert len(reqs) == 1
    payload = json.loads(reqs[0].read_text(encoding="utf-8"))
    assert payload["purpose"] == "dr_round2"
    assert payload["max_tokens"] == 100
    assert "dr-round2" in reqs[0].name          # slugged purpose in file name
    assert payload["response_file"].endswith(".txt")


def test_cache_returns_immediately_without_new_request(tmp_path):
    bridge = Bridge(tmp_path, poll=0.02, timeout=5)
    _responder(tmp_path, "first")
    assert bridge.complete("same prompt", purpose="grounder") == "first"
    n_reqs = len(list(tmp_path.glob("req_*.json")))
    # Second call, same purpose+prompt — must be served from cache.
    assert bridge.complete("same prompt", purpose="grounder") == "first"
    assert len(list(tmp_path.glob("req_*.json"))) == n_reqs


def test_cache_survives_new_bridge_instance_with_different_seq(tmp_path):
    bridge1 = Bridge(tmp_path, poll=0.02, timeout=5)
    _responder(tmp_path, "cached answer")
    bridge1.complete("prompt A", purpose="evaluator")
    # New instance (fresh seq counter) — stage-level resume scenario.
    bridge2 = Bridge(tmp_path, poll=0.02, timeout=0.3)
    assert bridge2.complete("prompt A", purpose="evaluator") == "cached answer"


def test_empty_response_race_guard(tmp_path):
    bridge = Bridge(tmp_path, poll=0.02, timeout=5)
    _responder(tmp_path, "real content", empty_first=True)
    assert bridge.complete("racy", purpose="grounder") == "real content"


def test_timeout_raises(tmp_path):
    bridge = Bridge(tmp_path, poll=0.02, timeout=0.15)
    with pytest.raises(BridgeTimeout):
        bridge.complete("no one answers", purpose="grounder")

"""Global test setup: offline by default.

Every test runs with the mock LLM backend, and any HTTP request that is not
served from a recorded fixture fails the test — the pipeline suites must be
runnable with no network at all (spec §15.4).
"""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("SURVEY_LLM_BACKEND", "mock")
os.environ.setdefault("SURVEY_HTTP_CACHE", "0")


@pytest.fixture(autouse=True)
def _fresh_settings(tmp_path, monkeypatch):
    """Reset cached settings and isolate runtime dirs per test."""
    from litreview import config

    monkeypatch.setenv("SURVEY_LLM_BACKEND", os.environ.get("SURVEY_LLM_BACKEND", "mock"))
    monkeypatch.setenv("SURVEY_BRIDGE_DIR", str(tmp_path / "bridge"))
    monkeypatch.setenv("SURVEY_HTTP_CACHE_DIR", str(tmp_path / "http_cache"))
    config.reset_settings()
    yield
    config.reset_settings()


@pytest.fixture(autouse=True)
def _no_network(request, monkeypatch):
    """Fail any test that tries to hit the real network.

    Tests that legitimately exercise HTTP against fixtures use the
    ``allow_network`` marker together with a patched transport.
    """
    if request.node.get_closest_marker("allow_network"):
        yield
        return

    import socket

    real_connect = socket.socket.connect

    def guarded(self, address, *args, **kwargs):  # noqa: ANN001
        host = address[0] if isinstance(address, tuple) else str(address)
        if host in ("127.0.0.1", "::1", "localhost"):
            return real_connect(self, address, *args, **kwargs)
        raise AssertionError(f"Test attempted real network access to {address!r}")

    monkeypatch.setattr(socket.socket, "connect", guarded)
    yield


def pytest_configure(config):
    config.addinivalue_line("markers", "allow_network: allow socket use in this test")

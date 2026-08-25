"""M7 — shared-access-code auth layer.

The invariant: an empty SURVEY_ACCESS_CODE (the default everywhere else in
the suite) disables the layer entirely, so every pre-M7 behavior is
untouched. These tests turn it on explicitly.
"""

import pytest
from fastapi.testclient import TestClient

from litreview import config
from litreview.server import auth
from litreview.server.app import create_app

CODE = "sesame-1234"


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("SURVEY_ACCESS_CODE", CODE)
    config.reset_settings()
    auth.reset_lockouts()
    app = create_app(data_dir=tmp_path / "var")
    with TestClient(app, follow_redirects=False) as c:
        yield c
    auth.reset_lockouts()


@pytest.fixture()
def open_client(tmp_path):
    # No code set (conftest default) — auth disabled.
    auth.reset_lockouts()
    app = create_app(data_dir=tmp_path / "var")
    with TestClient(app, follow_redirects=False) as c:
        yield c


def _login(client, code=CODE):
    return client.post("/api/auth/login", json={"code": code})


# --- disabled by default -----------------------------------------------------

def test_disabled_when_no_code(open_client):
    assert open_client.get("/api/surveys").status_code == 200
    status = open_client.get("/api/auth/status").json()
    assert status == {"enabled": False, "authenticated": True}
    # Login is meaningless without a configured code.
    assert open_client.post("/api/auth/login", json={"code": "x"}).status_code == 400


# --- guard -------------------------------------------------------------------

def test_api_blocked_without_session(client):
    res = client.get("/api/surveys")
    assert res.status_code == 401


def test_pages_redirect_to_login(client):
    res = client.get("/")
    assert res.status_code == 302
    assert res.headers["location"] == "/login.html"


def test_open_paths_reachable_without_session(client):
    assert client.get("/login.html").status_code == 200
    assert client.get("/api/health").status_code == 200
    assert client.get("/api/auth/status").json() == {
        "enabled": True, "authenticated": False}


# --- login / logout ----------------------------------------------------------

def test_wrong_code_rejected(client):
    assert _login(client, "wrong").status_code == 401
    assert client.get("/api/surveys").status_code == 401


def test_login_sets_session_and_unlocks_everything(client):
    res = _login(client)
    assert res.status_code == 204
    assert auth.COOKIE_NAME in res.cookies
    assert client.get("/api/surveys").status_code == 200
    assert client.get("/").status_code == 200          # the app page itself
    assert client.get("/api/auth/status").json()["authenticated"] is True


def test_logout_clears_session(client):
    _login(client)
    assert client.post("/api/auth/logout").status_code == 204
    assert client.get("/api/surveys").status_code == 401


def test_tampered_cookie_rejected(client):
    _login(client)
    good = client.cookies.get(auth.COOKIE_NAME)
    exp, _, sig = good.partition(".")
    client.cookies.set(auth.COOKIE_NAME, f"{exp}.{'0' * len(sig)}")
    assert client.get("/api/surveys").status_code == 401


def test_rotating_the_code_invalidates_sessions(client, monkeypatch):
    _login(client)
    assert client.get("/api/surveys").status_code == 200
    monkeypatch.setenv("SURVEY_ACCESS_CODE", "a-brand-new-code")
    config.reset_settings()
    assert client.get("/api/surveys").status_code == 401


# --- brute-force lockout -----------------------------------------------------

def test_lockout_after_repeated_failures(client):
    for _ in range(auth.MAX_FAILURES):
        assert _login(client, "wrong").status_code == 401
    assert _login(client, "wrong").status_code == 429
    # Even the RIGHT code is refused during the lockout window.
    assert _login(client, CODE).status_code == 429


# --- token unit checks -------------------------------------------------------

def test_token_expiry(monkeypatch):
    monkeypatch.setenv("SURVEY_ACCESS_CODE", CODE)
    config.reset_settings()
    token = auth.issue_token(now=1000.0)
    assert auth.token_valid(token, now=1000.0 + auth.SESSION_TTL_SECONDS - 1)
    assert not auth.token_valid(token, now=1000.0 + auth.SESSION_TTL_SECONDS + 1)
    assert not auth.token_valid("garbage")
    assert not auth.token_valid("")

"""Full REST journey through all three gates on the mock backend."""

import time

import pytest
from fastapi.testclient import TestClient

from litreview.server.app import create_app

BRIEF = {
    "topic": "כלים מבוססי AI לסקירת ספרות",
    "search_topic": "AI literature review tools",
    "audience": "חוקרים",
    "year_from": 2019, "year_to": 2026,
    "goals": ["מיפוי כלים"],
    "subtopics": ["citation verification"],
    "languages": ["English", "Hebrew"],
    "scope_preset": "summary",
    "author": "מאיה",
    "output_slides": True,
}


@pytest.fixture()
def client(tmp_path):
    app = create_app(data_dir=tmp_path / "var")
    with TestClient(app) as c:
        from urllib.parse import quote
        c.headers["X-Operator"] = quote("נועה")
        yield c


def _wait_idle(client, sid, timeout=60):
    deadline = time.time() + timeout
    while time.time() < deadline:
        run = client.get(f"/api/surveys/{sid}/run").json()
        if not run["running"]:
            return run
        time.sleep(0.1)
    raise AssertionError("job did not finish in time")


def test_full_journey(client):
    # Create + brief
    card = client.post("/api/surveys", json={"operator": "נועה"}).json()
    sid = card["id"]
    assert client.put(f"/api/surveys/{sid}/brief", json=BRIEF).status_code == 200

    # TOC build + edit (add a chapter — the spec §16 bug fix) + approve
    toc = client.post(f"/api/surveys/{sid}/toc/build").json()
    assert toc["meter"]["count"] >= 3
    chapters = toc["chapters"]
    chapters.append({"chapter": "שיקולים אתיים ורגולציה", "sections": ["רגולציה"]})
    toc = client.put(f"/api/surveys/{sid}/toc", json={"chapters": chapters}).json()
    added = next(c for c in toc["chapters"] if c["chapter"] == "שיקולים אתיים ורגולציה")
    assert added["keywords_en"], "added chapter must get keywords_en backfilled"
    assert client.post(f"/api/surveys/{sid}/toc/approve").status_code == 200
    assert client.get(f"/api/surveys/{sid}").json()["status"] == "toc_pending"

    # Sources: search (S2 job) → exclude one → approve
    assert client.post(f"/api/surveys/{sid}/sources/search").json()["job"] == "started"
    run = _wait_idle(client, sid)
    assert run["gates"]["sources"]["status"] == "pending"
    sources = client.get(f"/api/surveys/{sid}/sources").json()
    assert len(sources["papers"]) > 5
    victim = sources["papers"][0]["paper_id"]
    client.patch(f"/api/surveys/{sid}/sources", json={"exclude": [victim]})
    approve = client.post(f"/api/surveys/{sid}/sources/approve").json()
    assert approve["excluded"] >= 1

    # Writing segment (S3) → pauses at the draft gate
    assert client.post(f"/api/surveys/{sid}/run/start").status_code == 200
    run = _wait_idle(client, sid)
    assert run["gates"]["draft"]["status"] == "pending"
    assert client.get(f"/api/surveys/{sid}").json()["status"] == "draft_pending"

    # Draft: read, edit, override, pin
    draft = client.get(f"/api/surveys/{sid}/draft").json()
    assert draft["chapters"] and draft["grounding_report"]["total_claims"] > 0
    chapter = client.get(f"/api/surveys/{sid}/draft/chapters/1").json()
    assert chapter["content"] and chapter["claims"]

    patched = client.patch(f"/api/surveys/{sid}/draft/chapters/1",
                           json={"content": chapter["content"] + "\n\nהערה אנושית."})
    assert patched.status_code == 200

    conf = client.put(f"/api/surveys/{sid}/draft/chapters/1/confidence",
                      json={"value": "LIMITED", "reason": "בדיקה"}).json()
    assert conf["effective"] == "LIMITED"

    claim_id = chapter["claims"][0]["id"]
    over = client.put(f"/api/surveys/{sid}/draft/claims/{claim_id}",
                      json={"status": "supported", "reason": "בדקתי במקור"}).json()
    assert over["effective"] == "supported"

    pin = client.post(f"/api/surveys/{sid}/draft/chapters/1/pins",
                      json={"text": "הוסף טבלת השוואה"}).json()
    assert pin["status"] == "open"

    # Approve blocked by the open pin (409), rewrite resolves it
    blocked = client.post(f"/api/surveys/{sid}/draft/approve")
    assert blocked.status_code == 409
    assert blocked.json()["detail"]["open_pins"]

    assert client.post(f"/api/surveys/{sid}/draft/rewrite",
                       json={"chapters": [1]}).status_code == 200
    _wait_idle(client, sid)
    chapter = client.get(f"/api/surveys/{sid}/draft/chapters/1").json()
    assert all(p["status"] != "open" for p in chapter["pins"])

    assert client.post(f"/api/surveys/{sid}/draft/approve").status_code == 200

    # Finalize (S4) → done, exports ready
    client.post(f"/api/surveys/{sid}/run/start")
    _wait_idle(client, sid)
    assert client.get(f"/api/surveys/{sid}").json()["status"] == "done"

    exports = client.get(f"/api/surveys/{sid}/exports").json()["formats"]
    by_fmt = {f["format"]: f for f in exports}
    assert by_fmt["html"]["status"] == "ready"
    assert by_fmt["docx"]["status"] == "ready"
    assert by_fmt["slides"]["status"] == "ready"   # output_slides in brief

    download = client.get(f"/api/surveys/{sid}/exports/html/download?inline=1")
    assert download.status_code == 200
    assert 'dir="rtl"' in download.text

    # Dashboard card reflects completion; operator override in audit log
    dashboard = client.get("/api/surveys").json()
    card = next(c for c in dashboard["surveys"] if c["id"] == sid)
    assert card["status"] == "done" and card["progress_pct"] == 100


def test_gates_enforced_in_order(client):
    sid = client.post("/api/surveys", json={}).json()["id"]
    client.put(f"/api/surveys/{sid}/brief", json=BRIEF)
    # sources/search before TOC approval → 409
    client.post(f"/api/surveys/{sid}/toc/build")
    assert client.post(f"/api/surveys/{sid}/sources/search").status_code == 409
    # empty TOC cannot be approved
    client.put(f"/api/surveys/{sid}/toc", json={"chapters": []})
    assert client.post(f"/api/surveys/{sid}/toc/approve").status_code == 409


def test_versions_and_gold(client):
    sid = client.post("/api/surveys", json={"topic": "נושא"}).json()["id"]
    client.put(f"/api/surveys/{sid}/brief", json=BRIEF)
    card = client.post(f"/api/surveys/{sid}/versions", json={"carry": ["brief"]}).json()
    assert card["current_version"] == 2
    assert len(card["versions"]) == 2
    assert client.get(f"/api/surveys/{sid}/brief").json()["topic"] == BRIEF["topic"]

    assert client.put("/api/gold-standard", json={"survey_id": sid}).status_code == 200
    assert client.get(f"/api/surveys/{sid}").json()["gold"] is True


def test_operators_and_meta(client):
    client.post("/api/operators", json={"name": "אבי"})
    ops = client.get("/api/operators").json()["operators"]
    assert "אבי" in ops
    meta = client.get("/api/meta").json()
    assert meta["backend"] == "mock"

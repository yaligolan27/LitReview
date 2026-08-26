"""M8 — the deep-interview stage: chat endpoints, charter distillation, and
the merge into the brief. Mock backend → deterministic interviewer."""

import time

import pytest
from fastapi.testclient import TestClient

from litreview.agents.interviewer import apply_charter, charter_prompt_block
from litreview.core.state import ResearchBrief, SurveyState
from litreview.server.app import create_app

BRIEF = {
    "topic": "כלי AI לסקירת ספרות",
    "search_topic": "AI literature review",
    "goals": ["מיפוי"],
    "subtopics": ["verification"],
    "languages": ["English"],
}


@pytest.fixture()
def client(tmp_path):
    app = create_app(data_dir=tmp_path / "var")
    with TestClient(app) as c:
        yield c


def _wait_idle(client, sid, timeout=30):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if not client.get(f"/api/surveys/{sid}/interview").json()["busy"]:
            return client.get(f"/api/surveys/{sid}/interview").json()
        time.sleep(0.05)
    raise AssertionError("interview job did not finish")


def _new_survey(client):
    sid = client.post("/api/surveys", json={"operator": "מאיה"}).json()["id"]
    client.put(f"/api/surveys/{sid}/brief", json=BRIEF)
    return sid


def test_full_interview_flow(client):
    sid = _new_survey(client)

    # Start → opening interviewer turn appears; status flips to interviewing.
    assert client.post(f"/api/surveys/{sid}/interview/start").json()["job"] == "started"
    doc = _wait_idle(client, sid)
    assert doc["messages"] and doc["messages"][0]["role"] == "assistant"
    assert "?" in doc["messages"][0]["text"]
    assert client.get(f"/api/surveys/{sid}").json()["status"] == "interviewing"

    # Start again is idempotent — no duplicate opening.
    client.post(f"/api/surveys/{sid}/interview/start")
    assert len(_wait_idle(client, sid)["messages"]) == 1

    # Two user turns → user+assistant appended each time.
    for text in ("הסקר נועד לתמוך בהחלטת רכש.", "הקהל הוא מהנדסים ותיקים."):
        client.post(f"/api/surveys/{sid}/interview/message", json={"text": text})
        doc = _wait_idle(client, sid)
    assert [m["role"] for m in doc["messages"]] == [
        "assistant", "user", "assistant", "user", "assistant"]

    # Finish → charter distilled, merged into the brief, status back to brief.
    client.post(f"/api/surveys/{sid}/interview/finish")
    doc = _wait_idle(client, sid)
    assert doc["status"] == "done"
    assert doc["charter"]["charter"].startswith("##")
    brief = client.get(f"/api/surveys/{sid}/brief").json()
    assert brief["charter"]                             # injected downstream
    assert "מטרה שחודדה בראיון" in brief["goals"]
    assert "interview refined subtopic" in brief["subtopics"]
    assert brief["audience"] == "קהל מקצועי (מהראיון)"
    assert "charter" in doc["applied_fields"]
    assert client.get(f"/api/surveys/{sid}").json()["status"] == "brief"


def test_empty_message_rejected_and_finish_needs_transcript(client):
    sid = _new_survey(client)
    assert client.post(f"/api/surveys/{sid}/interview/message",
                       json={"text": "  "}).status_code == 422
    assert client.post(f"/api/surveys/{sid}/interview/finish").status_code == 409


def test_interview_blocked_after_sources_approved(client):
    sid = _new_survey(client)
    # Force a post-gate status directly through the store.
    client.app.state.store.set_status(sid, "writing")
    assert client.post(f"/api/surveys/{sid}/interview/start").status_code == 409


# --- survey-style turns (v2) ------------------------------------------------

def test_turns_carry_clickable_options(client):
    sid = _new_survey(client)
    client.post(f"/api/surveys/{sid}/interview/start")
    doc = _wait_idle(client, sid)
    turn = doc["messages"][0]["turn"]
    assert turn["questions"], "opening turn must carry prepared questions"
    first = turn["questions"][0]
    assert len(first["options"]) >= 3          # ready-made clickable options
    assert first["allow_other"] is True        # free-text detail stays possible
    # The plain-text form lists the options too (transcript context).
    assert "אפשרויות:" in doc["messages"][0]["text"]


def test_normalize_turn_falls_back_to_plain_text():
    from litreview.agents.interviewer import normalize_turn
    # A serving session answering free-form still works (no options, intro only).
    turn = normalize_turn("שאלה חופשית: מה חשוב לך בסקר?")
    assert turn["questions"] == []
    assert "מה חשוב לך" in turn["intro"]
    # Malformed question entries are dropped; valid ones normalized.
    turn = normalize_turn('{"intro": "היי", "questions": [{"text": "שאלה?", '
                          '"options": ["א", "ב", ""], "multi": true}, {"oops": 1}], '
                          '"done_hint": true}')
    assert len(turn["questions"]) == 1
    assert turn["questions"][0]["options"] == ["א", "ב"]
    assert turn["questions"][0]["multi"] is True
    assert turn["done_hint"] is True


# --- unit: charter merge + prompt injection ---------------------------------

def test_apply_charter_merges_non_destructively():
    brief_doc = {"goals": ["קיים"], "subtopics": ["old"], "audience": "",
                 "year_from": 2015, "year_to": 2026}
    changed = apply_charter(brief_doc, {
        "charter": "אמנה", "goals": ["קיים", "חדש"], "subtopics_en": ["new-sub"],
        "audience": "קהל", "year_from": 2019, "year_to": None,
        "languages": ["German"], "must_include_papers": ["10.1/x"],
        "scope_preset": "full", "search_topic": None,
    })
    assert brief_doc["goals"] == ["קיים", "חדש"]          # dedup, order kept
    assert brief_doc["subtopics"] == ["old", "new-sub"]
    assert brief_doc["year_from"] == 2019 and brief_doc["year_to"] == 2026
    assert brief_doc["user_papers"] == ["10.1/x"]
    assert brief_doc["charter"] == "אמנה"
    assert "goals" in changed and "year_to" not in changed


def test_charter_block_injected_into_writer_prompt():
    from litreview.agents.writer import build_chapter_prompt
    from litreview.core.state import TocEntry

    state = SurveyState(brief=ResearchBrief(topic="נושא", charter="דגש חשוב מהראיון"))
    prompt = build_chapter_prompt(state, TocEntry(chapter="פרק"), 1, [])
    assert "אמנת המחקר" in prompt and "דגש חשוב מהראיון" in prompt
    # No charter → no block (pre-M8 prompt unchanged).
    state.brief.charter = ""
    assert "אמנת המחקר" not in build_chapter_prompt(
        state, TocEntry(chapter="פרק"), 1, [])


def test_charter_prompt_block_caps_length():
    brief = ResearchBrief(charter="א" * 10_000)
    block = charter_prompt_block(brief)
    assert len(block) < 5_000

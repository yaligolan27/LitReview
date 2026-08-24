"""The safety guard — an unsafe edit must be provably rejected (spec §9.11)."""

from litreview.agents.hebrew_editor import safe_to_apply

ORIGINAL = ("המחקר מצא שיפור של 73% במדדים [1,2]. "
            "[CALLOUT:blue]נקודה: חשוב לזכור.[/CALLOUT] "
            "ממצא נוסף מופיע בספרות [W3].")


def test_identity_edit_is_safe():
    ok, reason = safe_to_apply(ORIGINAL, ORIGINAL)
    assert ok, reason


def test_wording_change_without_facts_is_safe():
    edited = ORIGINAL.replace("חשוב לזכור", "ראוי להדגיש")
    ok, reason = safe_to_apply(ORIGINAL, edited)
    assert ok, reason


def test_changed_number_rejected():
    ok, reason = safe_to_apply(ORIGINAL, ORIGINAL.replace("73%", "74%"))
    assert not ok and "numbers" in reason


def test_removed_citation_rejected():
    ok, reason = safe_to_apply(ORIGINAL, ORIGINAL.replace(" [W3]", ""))
    assert not ok and "citation" in reason


def test_changed_marker_census_rejected():
    edited = ORIGINAL.replace("[CALLOUT:blue]", "").replace("[/CALLOUT]", "")
    ok, reason = safe_to_apply(ORIGINAL, edited)
    assert not ok and "marker" in reason


def test_empty_and_length_ratio_rejected():
    ok, reason = safe_to_apply(ORIGINAL, "   ")
    assert not ok and "empty" in reason
    ok, reason = safe_to_apply(ORIGINAL, ORIGINAL + ORIGINAL + ORIGINAL)
    assert not ok and "length" in reason


def test_edit_introducing_lint_error_rejected():
    edited = ORIGINAL.replace("[/CALLOUT]", "[/CALLOUT][TABLE]broken")
    ok, reason = safe_to_apply(ORIGINAL, edited)
    assert not ok

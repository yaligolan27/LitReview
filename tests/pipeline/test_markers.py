from litreview.core import markers


def test_clean_text_has_no_issues():
    text = "פסקה רגילה [1].\n[CALLOUT:blue]כותרת: תוכן[/CALLOUT]\n[TRL:7]"
    assert markers.lint(text) == []
    assert not markers.has_errors(text)


def test_unbalanced_tag_is_error():
    issues = markers.lint("[CALLOUT:blue]ללא סגירה")
    assert any(i.level == "error" and "CALLOUT" in i.message for i in issues)
    assert markers.has_errors("[TABLE]a|b")


def test_invalid_color_and_trl_are_warnings_and_autofixed():
    text = "[CALLOUT:pink]x[/CALLOUT] [TRL:12]"
    issues = markers.lint(text)
    levels = {i.level for i in issues}
    assert levels == {"warning"}
    fixed = markers.autofix(text)
    assert "[CALLOUT:blue]" in fixed
    assert "[TRL:9]" in fixed
    assert markers.lint(fixed) == []


def test_autofix_never_closes_tags():
    text = "[FORMULA]x^2"
    assert markers.autofix(text) == text  # unbalanced left alone (dangerous to guess)
    assert markers.has_errors(text)


def test_marker_census_counts():
    text = "[KPI]a|b|c|d[/KPI] [CALLOUT:red]x[/CALLOUT] [TRL:3] **בולט**"
    census = markers.marker_census(text)
    assert census["KPI"] == 1 and census["/KPI"] == 1
    assert census["CALLOUT"] == 1 and census["TRL"] == 1
    assert census["TABLE"] == 0

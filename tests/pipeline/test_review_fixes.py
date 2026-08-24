"""Regression tests for the adversarial-review findings (M5 hardening).

Each test is named for the defect it locks down.
"""

import pytest

from litreview.agents import deep_research as dr
from litreview.agents.claim_grounder import _locate_and_soften, strip_for_claims
from litreview.agents.critical_reviewer import _numbers_without_source
from litreview.agents.hebrew_editor import safe_to_apply
from litreview.agents.html_generator.builders import esc, safe_href
from litreview.core.marker_render import latex_to_unicode
from litreview.core.state import Claim, SurveySection


# --- Hebrew-editor safety guard (the flagship invariant) -------------------

def test_sign_flip_is_rejected():
    ok, reason = safe_to_apply("המתאם היה -0.8 לפי הנתונים",
                               "המתאם היה 0.8 לפי הנתונים")
    assert not ok and "numbers" in reason


def test_number_reordering_is_rejected():
    ok, reason = safe_to_apply("המדגם גדל מ-100 ל-250",
                               "המדגם גדל מ-250 ל-100")
    assert not ok and "numbers" in reason


def test_callout_color_change_is_rejected():
    ok, reason = safe_to_apply("[CALLOUT:red]אזהרה: סכנה[/CALLOUT]",
                               "[CALLOUT:green]אזהרה: סכנה[/CALLOUT]")
    assert not ok and "callout color" in reason


def test_year_range_not_treated_as_negative():
    # "2020-2026" must stay two unsigned tokens; a pure wording change passes.
    ok, _ = safe_to_apply("המחקר נערך בין 2020-2026 בתחום",
                          "המחקר בוצע בין 2020-2026 בתחום")
    assert ok


def test_genuine_wording_edit_still_accepted():
    ok, _ = safe_to_apply("החוקרים מצאו שיפור של 34% [1]",
                          "החוקרים דיווחו על שיפור של 34% [1]")
    assert ok


# --- Deep research domain logic --------------------------------------------

def test_registrable_domain_collapses_subdomains():
    assert dr._domain("https://www.nasa.gov/a") == "nasa.gov"
    assert dr._domain("https://science.nasa.gov/b") == "nasa.gov"
    # Same org -> NOT independent corroboration.
    assert dr._domain("https://www.nasa.gov/a") == dr._domain("https://science.nasa.gov/b")


def test_registrable_domain_multi_part_suffix():
    assert dr._domain("https://foo.ac.il/x") == "foo.ac.il"
    assert dr._domain("https://a.foo.ac.il/x") == "foo.ac.il"
    assert dr._domain("https://bar.gov.uk/x") == "bar.gov.uk"


def test_classify_tier_t1_before_t3_markers():
    assert dr.classify_tier("https://www.nasa.gov/report") == "W-T1"
    assert dr.classify_tier("https://x.ac.il/paper") == "W-T1"
    # Real T3 markers still demote.
    assert dr.classify_tier("https://en.wikipedia.org/wiki/X") == "W-T3"
    assert dr.classify_tier("https://foo.medium.com/post") == "W-T3"


# --- Claim grounder ---------------------------------------------------------

def test_callout_content_not_extracted_as_claim():
    content = "[CALLOUT:blue]בפשטות: הסבר פשוט לפרק[/CALLOUT]\n\nטענה אמיתית [1]."
    stripped = strip_for_claims(content)
    assert "בפשטות" not in stripped
    assert "טענה אמיתית" in stripped


def test_softened_rewrite_applies_through_bold_markup():
    sec = SurveySection(content="הממצא **חד-משמעי** ומוכח מעל לכל ספק [3].")
    # claim.text is the stripped form (bold removed) — must still be located.
    claim_text = "הממצא חד-משמעי ומוכח מעל לכל ספק [3]."
    rewrite = "ייתכן שהממצא נתמך בחלק מההקשרים [3]."
    assert _locate_and_soften(sec, claim_text, rewrite)
    assert rewrite in sec.content
    assert "**חד-משמעי**" not in sec.content


# --- marker_render ----------------------------------------------------------

def test_latex_empty_brace_superscript_does_not_crash():
    assert latex_to_unicode(r"x^{}") == "x"          # no AttributeError
    assert latex_to_unicode(r"y_{}") == "y"
    assert latex_to_unicode(r"x^2 + y_{i}") == "x² + y_(i)"


# --- Critical reviewer ------------------------------------------------------

def test_cited_number_at_sentence_end_not_flagged():
    text = ("המערכת השיגה שיפור של 34% בדיוק המשימה בתנאים מבוקרים "
            "לאורך תקופת הבדיקה המלאה [12].")
    assert _numbers_without_source(text) == []


def test_uncited_number_still_flagged():
    text = "המערכת השיגה שיפור של 73% בביצועים. משפט המשך ללא מקור כלל."
    assert "73%" in _numbers_without_source(text)


# --- HTML escaping / XSS ----------------------------------------------------

def test_esc_escapes_double_quotes():
    assert '"' not in esc('x" onmouseover="alert(1)')


def test_safe_href_blocks_non_http_schemes():
    assert safe_href("javascript:alert(1)") == "#"
    assert safe_href("data:text/html,x") == "#"
    assert safe_href("https://doi.org/10.1/x") == "https://doi.org/10.1/x"
    # A quote in the URL is escaped, not passed through.
    assert '"' not in safe_href('https://x/a"onload="y')

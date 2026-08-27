"""HTML/Word marker conversions incl. the formula-placeholder regression."""

from litreview.agents.html_generator.convert import convert_markers
from litreview.core.marker_render import latex_to_unicode, to_plain_text


def test_latex_to_unicode_core_conversions():
    assert latex_to_unicode(r"\eta = P_{out}/P_{in}") == "η = P_(out)/P_(in)"
    assert latex_to_unicode(r"x^2 + y^{10}") == "x² + y¹⁰"
    assert latex_to_unicode(r"\frac{a}{b}") == "(a)/(b)"
    assert latex_to_unicode(r"\sqrt{x} \leq \infty") == "√(x) ≤ ∞"
    assert latex_to_unicode(r"\alpha \times \beta") == "α × β"
    assert latex_to_unicode(r"\operatorname{max}(x)") == "max(x)"


def test_nested_frac():
    assert latex_to_unicode(r"\frac{\frac{a}{b}}{c}") == "((a)/(b))/(c)"


def test_convert_formula_placeholder_no_nesting():
    text = "פסקה.\n\n[FORMULA]\\eta = x[/FORMULA]\n\nעוד פסקה."
    html = convert_markers(text)
    assert html.count('<div class="formula">') == 1
    assert "\\[\\eta = x\\]" in html
    assert "\x00" not in html                     # placeholders all restored
    assert "[FORMULA]" not in html


def test_convert_table_with_best_bad():
    text = "[TABLE]| a | b |\n| --- | --- |\n| x [BEST] | y [BAD] |[/TABLE]"
    html = convert_markers(text)
    assert '<table class="tbl">' in html
    assert '<td class="best">x</td>' in html
    assert '<td class="bad">y</td>' in html
    assert "[BEST]" not in html


def test_convert_case_kpi_trl_wcite():
    text = ("[CASE]שם|תג1, תג2|תוכן המקרה[/CASE]\n\n"
            "[KPI]73%|תיאור|[1]|הקשר[/KPI]\n\nרמה [TRL:7] וממצא [W2] וציטוט [3].")
    html = convert_markers(text)
    assert "מקרה בוחן: שם" in html and "תג1" in html
    assert "[KPI]" not in html and "73%" not in html    # KPI dropped from chapters
    assert '<span class="trl">TRL 7</span>' in html
    assert 'href="#wsrc-2"' in html
    assert "<cite>[3]</cite>" in html


def test_to_plain_text_strips_everything():
    text = ("### כותרת\n[CALLOUT:red]אזהרה: תוכן[/CALLOUT] "
            "[FORMULA]x^2[/FORMULA] **מודגש** [TABLE]|a|[/TABLE][TRL:5]")
    plain = to_plain_text(text)
    assert "[" not in plain.replace("(TRL 5)", "")
    assert "אזהרה: תוכן" in plain
    assert "x²" in plain
    assert "מודגש" in plain and "**" not in plain

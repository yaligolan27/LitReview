"""Part-E wave 1 (spec §22): formula lint, symbol legend, plain boxes,
glossary, cross-consensus."""

from litreview import config
from litreview.agents.claim_grounder import _mark_cross_corroborated
from litreview.agents.critical_reviewer import review_section
from litreview.core import markers
from litreview.core.state import Claim, Paper, SurveySection

PLAIN = "[CALLOUT:blue]בפשטות: הסבר פשוט לפרק.[/CALLOUT]\n\n"


def test_formula_lint_catches_broken_latex():
    bad = r"[FORMULA]\frac{a}{[/FORMULA]"
    issues = markers.lint_formulas(bad)
    assert issues and issues[0].level == "error"

    hebrew = r"[FORMULA]\eta = יעילות[/FORMULA]"
    issues = markers.lint_formulas(hebrew)
    assert any("עבריים" in i.message for i in issues)

    ok = r"[FORMULA]\eta = P_{out} / P_{in}[/FORMULA]"
    assert markers.lint_formulas(ok) == []


def test_reviewer_requires_legend_and_plain_box():
    settings = config.get_settings()
    content = PLAIN + ("טענה מבוססת [1]. " * 30) + \
        "\n\n[FORMULA]x^2[/FORMULA]\n\nממשיכים בלי מקרא לטקסט הבא."
    sec = SurveySection(title="פרק", content=content, confidence="HIGH",
                        papers=[Paper(title="t")])
    issues = review_section(sec, settings=settings)
    assert any("מקרא" in i for i in issues)

    no_plain = content.replace(PLAIN, "")
    sec2 = SurveySection(title="פרק", content=no_plain, confidence="HIGH")
    issues2 = review_section(sec2, settings=settings)
    assert any("בפשטות" in i for i in issues2)


def test_cross_corroboration_disjoint_authors_only():
    papers = [Paper(title="a", authors=["Smith, J.", "Levi, D."]),
              Paper(title="b", authors=["Chen, L."]),
              Paper(title="c", authors=["Smith, J."])]
    sec = SurveySection(title="x", papers=papers)
    disjoint = Claim(text="t", citations=[1, 2], status="supported")
    overlapping = Claim(text="t", citations=[1, 3], status="supported")
    single = Claim(text="t", citations=[1], status="supported")
    unsupported = Claim(text="t", citations=[1, 2], status="unsupported")
    _mark_cross_corroborated(sec, [disjoint, overlapping, single, unsupported])
    assert disjoint.cross_corroborated
    assert not overlapping.cross_corroborated
    assert not single.cross_corroborated
    assert not unsupported.cross_corroborated

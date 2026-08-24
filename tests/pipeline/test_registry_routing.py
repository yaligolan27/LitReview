"""Domain routing matrix — spec §9.3b."""

from litreview.apis import registry
from litreview.config import Settings


def test_keyword_syntax_prefix_substring_exact_hebrew():
    scores = registry.classify_topic(
        "Solid rocket propulsion for launch vehicle nozzles")
    assert scores.get("aerospace", 0) >= 3  # rocket*, propulsion, launch vehicle, nozzle*

    scores = registry.classify_topic("radar surveillance systems for defense")
    assert scores.get("defense_security", 0) >= 3

    scores = registry.classify_topic("סקירה על טילים וביטחון לאומי")
    assert scores.get("defense_security", 0) >= 2


def test_deliberate_psychology_overlap():
    scores = registry.classify_topic("psychological interventions effectiveness")
    assert "biomed" in scores and "social_econ" in scores


def test_aerospace_routing_turns_on_topical_and_drops_biomed():
    result = registry.route(Settings(), "solid rocket motor nozzle propulsion design")
    assert "aerospace" in result.certain_domains
    assert "nasa_ntrs" in result.active and "osti" in result.active
    assert "pubmed" in result.dropped and "europepmc" in result.dropped
    # Universal core is never dropped.
    for src in ("openalex", "crossref", "semantic_scholar", "doaj"):
        assert src in result.active


def test_uncertain_domain_cannot_drop_sources():
    # A single keyword hit (score 1) must not shut anything down.
    result = registry.route(Settings(), "general social overview")
    assert result.dropped == []
    assert "pubmed" in result.active


def test_hybrid_topic_keeps_sources_needed_by_other_domain():
    # biomed wants to drop arxiv; cs_ai has arxiv in its core → guard 2 keeps it.
    result = registry.route(
        Settings(), "machine learning neural network models for clinical patient "
                    "disease therapy prediction")
    assert {"biomed", "cs_ai"} <= set(result.certain_domains)
    assert "arxiv" in result.active
    assert "dblp" in result.active  # cs_ai core, needed despite biomed avoid-list


def test_llm_domains_count_as_certain():
    result = registry.route(Settings(), "completely unrelated words",
                            llm_domains=["aerospace"])
    assert "aerospace" in result.certain_domains
    assert "nasa_ntrs" in result.active


def test_sources_override_wins():
    settings = Settings(sources_override=("openalex", "crossref"))
    result = registry.route(settings, "solid rocket motor")
    assert result.active == ["openalex", "crossref"]
    assert result.override == "SURVEY_SOURCES"


def test_offline_uses_mockdb_only():
    result = registry.route(Settings(), "anything", offline=True)
    assert result.active == ["mockdb"]

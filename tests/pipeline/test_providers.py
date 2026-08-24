"""Provider normalization contracts against inline recorded fixtures."""

from litreview.apis import crossref, dblp, europepmc, openalex, semantic_scholar


def test_openalex_normalize_inverted_abstract_and_fields():
    work = {
        "id": "https://openalex.org/W123",
        "display_name": "A Study of Things",
        "publication_year": 2023,
        "cited_by_count": 42,
        "type": "article",
        "language": "en",
        "is_retracted": False,
        "ids": {"doi": "https://doi.org/10.1000/xyz"},
        "abstract_inverted_index": {"Deep": [0], "learning": [1], "works": [2]},
        "authorships": [{"author": {"display_name": "Ada Lovelace"}}],
        "primary_location": {
            "landing_page_url": "https://example.org/paper",
            "source": {"display_name": "Journal of Things"}},
        "open_access": {"is_oa": True, "oa_url": "https://example.org/pdf"},
    }
    paper = openalex._normalize(work)
    assert paper.id == "W123"
    assert paper.doi == "10.1000/xyz"
    assert paper.abstract == "Deep learning works"
    assert paper.source_type == "journal-article"
    assert paper.language == "en" and paper.is_open_access
    assert paper.authors == ["Ada Lovelace"]


def test_crossref_normalize_year_authors_type():
    item = {
        "DOI": "10.1000/abc",
        "title": ["Sample Title"],
        "abstract": "<jats:p>An abstract.</jats:p>",
        "type": "journal-article",
        "container-title": ["The Journal"],
        "is-referenced-by-count": 7,
        "issued": {"date-parts": [[2021, 5]]},
        "author": [{"family": "Smith", "given": "Jane"}, {"family": "Levi"}],
        "URL": "https://doi.org/10.1000/abc",
    }
    paper = crossref._normalize(item)
    assert paper.year == 2021
    assert paper.authors == ["Smith, Jane", "Levi"]
    assert paper.abstract == "An abstract."
    assert paper.source_type == "journal-article"


def test_semantic_scholar_normalize_types_and_ids():
    item = {
        "paperId": "abc123",
        "title": "S2 Paper",
        "year": 2024,
        "venue": "NeurIPS",
        "citationCount": 12,
        "publicationTypes": ["JournalArticle"],
        "externalIds": {"DOI": "10.1000/s2"},
        "authors": [{"name": "Grace Hopper"}],
        "isOpenAccess": True,
        "openAccessPdf": {"url": "https://pdf"},
    }
    paper = semantic_scholar._normalize(item)
    assert paper.source_type == "journal-article"
    assert paper.doi == "10.1000/s2" and paper.pdf_url == "https://pdf"


def test_dblp_normalize_single_author_dict_and_type():
    hit = {"info": {"key": "conf/x/1", "title": "DBLP Paper.",
                    "venue": "ICML", "year": "2022",
                    "type": "Conference and Workshop Papers",
                    "authors": {"author": {"text": "Alan Turing"}},
                    "ee": "https://doi.org/10.1000/d"}}
    paper = dblp._normalize(hit)
    assert paper.title == "DBLP Paper"
    assert paper.authors == ["Alan Turing"]
    assert paper.source_type == "proceedings-article"
    assert paper.year == 2022


def test_europepmc_normalize():
    item = {"id": "12345", "source": "MED", "title": "EPMC Paper",
            "abstractText": "Text.", "pubYear": "2020",
            "authorString": "Doe J, Roe R", "journalTitle": "The Lancet",
            "citedByCount": 3, "doi": "10.1000/e", "pubType": "research-article",
            "isOpenAccess": "Y"}
    paper = europepmc._normalize(item)
    assert paper.year == 2020 and paper.is_open_access
    assert paper.source_type == "journal-article"
    assert paper.authors == ["Doe J", "Roe R"]

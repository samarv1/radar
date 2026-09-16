import pytest

from scrapers.company_names import normalize_company_identity
from scrapers.techcrunch import find_match, parse_amount, parse_company_link


def test_parse_company_link_returns_name_and_website_together():
    content = '<p><a href="https://acme.example/about">Acme</a> raised a seed round.</p>'

    assert parse_company_link(content) == ("Acme", "https://acme.example/about")


def test_parse_company_link_retains_first_homepage_as_website_fallback():
    content = (
        '<a href="https://acme.example/">learn more</a>'
        '<a href="https://other.example/news">Other source</a>'
    )

    assert parse_company_link(content) == (None, "https://acme.example/")


def test_accelerator_matching_requires_exact_company_identity():
    names = [normalize_company_identity("Benchmark Labs")]

    assert find_match("Benchmark", [42], names) is None
    assert find_match("Benchmark Labs, Inc.", [42], names) == 42


@pytest.mark.parametrize(
    "title",
    [
        "Boring Company is raising again at a $20B valuation",
        "Valar Atomics raises funding at a $6B valuation",
        "Acme is now valued at $3 billion after its latest round",
    ],
)
def test_parse_amount_ignores_valuations(title):
    assert parse_amount(title) is None


@pytest.mark.parametrize(
    ("title", "expected"),
    [
        ("Acme raises $25M in Series B funding", 25_000_000),
        ("Acme closes $2.5 million seed round", 2_500_000),
        ("Acme raises $40M at a $500M valuation", 40_000_000),
        ("At a $500M valuation, Acme raises $40M", 40_000_000),
    ],
)
def test_parse_amount_returns_funding_amount(title, expected):
    assert parse_amount(title) == expected

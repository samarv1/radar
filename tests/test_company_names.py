import pytest

from scrapers.company_names import (
    find_company_match,
    find_exact_company_match,
    normalize_company_identity,
    normalize_company_name,
)


def test_normalize_company_name_removes_suffixes_punctuation_and_ticker():
    assert normalize_company_name("Acme Technologies, Inc. (ACME)") == "acme"


def test_normalize_company_name_does_not_remove_suffix_substrings():
    assert normalize_company_name("Capitalise AIrways") == "capitalise airways"


def test_find_company_match_keeps_threshold_at_call_site():
    candidates = [normalize_company_name("Acme Labs"), normalize_company_name("Other Co")]

    assert find_company_match("Acme, Inc.", candidates, threshold=95) == (0, 100.0)
    assert find_company_match("Unrelated", candidates, threshold=95) is None


def test_company_identity_removes_only_trailing_legal_suffixes():
    assert normalize_company_identity("Acme Technologies, Inc.") == "acme technologies"
    assert normalize_company_identity("Gateway Capital Partners") == "gateway capital partners"


@pytest.mark.parametrize(
    ("news_name", "accelerator_name"),
    [
        ("Lion Energy Limited", "Helion Energy"),
        ("Finly", "Findly"),
        ("Coverwatch", "Overwatch"),
        ("STRAAND", "Strand AI"),
        ("Clove", "Clover"),
        ("Penguin Solutions", "Penguin AI"),
        ("Gateway Capital Partners", "Gateway"),
        ("Benchmark", "Benchmark Labs"),
        ("Scent Lab", "Ascent"),
        ("Brief", "AI Brief"),
        ("Edify", "Jedify"),
        ("Trala", "Strala"),
        ("Stacked", "Staked"),
    ],
)
def test_exact_company_matching_rejects_similar_company_names(news_name, accelerator_name):
    candidates = [normalize_company_identity(accelerator_name)]

    assert find_exact_company_match(news_name, candidates) is None


def test_exact_company_matching_accepts_legal_suffix_variants():
    candidates = [normalize_company_identity("Acme Technologies, Inc.")]

    assert find_exact_company_match("Acme Technologies", candidates) == 0

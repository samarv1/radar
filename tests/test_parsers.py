from scrapers.edgar import parse_form_d_xml
from scrapers.company_names import normalize_company_identity
from scrapers.signalbase import find_match, parse_page


def test_edgar_parser_extracts_nested_form_d_fields():
    parsed = parse_form_d_xml(
        """
        <edgarSubmission>
          <primaryIssuer>
            <entityName>Acme Robotics, Inc.</entityName>
            <issuerAddress><city>Oakland</city></issuerAddress>
          </primaryIssuer>
          <offeringData>
            <industryGroup><industryGroupType>Other Technology</industryGroupType></industryGroup>
            <dateOfFirstSale><value>2026-09-01</value></dateOfFirstSale>
            <offeringSalesAmounts><totalAmountSold>2500000</totalAmountSold></offeringSalesAmounts>
          </offeringData>
        </edgarSubmission>
        """
    )

    assert parsed["company_name"] == "Acme Robotics, Inc."
    assert parsed["city"] == "Oakland"
    assert parsed["industry_group"] == "Other Technology"
    assert parsed["date_of_first_sale"] == "2026-09-01"
    assert parsed["amount_raised"] == 2_500_000


def test_signalbase_parser_uses_article_metadata_and_company_link():
    row = parse_page(
        """
        <html><head>
          <meta property="og:title" content="Acme Raises $2.5M Seed | Signalbase">
          <meta name="description" content="Acme closed a seed round">
          <script type="application/ld+json">
            {"@type":"NewsArticle","datePublished":"2026-09-01T12:00:00Z"}
          </script>
        </head><body>
          <a href="https://acme.example/?utm_source=trysignalbase.com&amp;utm_medium=referral">Acme</a>
        </body></html>
        """,
        "https://www.trysignalbase.com/news/funding/acme-raises-seed",
    )

    assert row is not None
    assert row["company_name"] == "Acme"
    assert row["amount_usd"] == 2_500_000
    assert row["round_type"] == "Seed"
    assert row["website"] == "https://acme.example/"


def test_signalbase_accelerator_matching_requires_exact_company_identity():
    names = [normalize_company_identity("Helion Energy")]

    assert find_match("Lion Energy Limited", [7], names) is None
    assert find_match("Helion Energy, Inc.", [7], names) == 7

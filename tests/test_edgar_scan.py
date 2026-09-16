from datetime import date
from unittest.mock import MagicMock, Mock

from scrapers import edgar
from scrapers.edgar import filter_unknown_stubs


def test_filter_unknown_stubs_skips_database_and_in_run_duplicates():
    seen = {"known-accession"}
    stubs = [
        {"accession_no": "known-accession"},
        {"accession_no": "new-accession"},
        {"accession_no": "new-accession"},
        {"accession_no": "another-accession"},
    ]

    assert filter_unknown_stubs(stubs, seen) == [stubs[1], stubs[3]]
    assert seen == {"known-accession", "new-accession", "another-accession"}


def test_filter_unknown_stubs_leaves_invalid_stub_for_failure_accounting():
    stub = {"accession_no": "", "cik": ""}

    assert filter_unknown_stubs([stub], set()) == [stub]


def test_targeted_scan_revisits_known_filing_to_attach_accelerator(monkeypatch):
    response = Mock(status_code=200)
    response.json.return_value = {
        "filings": {
            "recent": {
                "form": ["D"],
                "filingDate": ["2026-01-02"],
                "accessionNumber": ["0001234567-26-000001"],
            }
        }
    }
    conn = MagicMock()
    cursor = conn.cursor.return_value.__enter__.return_value
    fetch_xml = Mock(return_value=("<xml />", "https://example.test/form.xml"))
    monkeypatch.setattr(edgar.requests, "get", lambda *args, **kwargs: response)
    monkeypatch.setattr(edgar.SEC_RATE_LIMITER, "wait", lambda: None)
    monkeypatch.setattr(edgar, "fetch_primary_xml", fetch_xml)
    monkeypatch.setattr(edgar, "parse_form_d_xml", lambda _: {"company_name": "Acme"})
    monkeypatch.setattr(edgar, "is_excluded_by_xml", lambda _: False)
    monkeypatch.setattr(edgar, "upsert_filing", lambda *_: False)
    monkeypatch.setattr(edgar, "_get_worker_connection", lambda *_: conn)

    result = edgar._targeted_one(7, "Acme", "1234567", date(2025, 1, 1), [], Mock())

    assert result == (0, 1, 0)
    fetch_xml.assert_called_once_with("1234567", "0001234567-26-000001")
    cursor.execute.assert_called_once_with(
        "UPDATE edgar_filings SET accelerator_id = %s WHERE accession_number = %s AND accelerator_id IS NULL",
        (7, "0001234567-26-000001"),
    )

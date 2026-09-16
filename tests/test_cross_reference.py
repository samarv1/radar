from unittest.mock import MagicMock

from scrapers.cross_reference import load_edgar_companies


def test_cross_reference_loads_only_unmatched_by_default():
    cursor = MagicMock()
    cursor.fetchall.return_value = [(1, "Acme, Inc.")]
    conn = MagicMock()
    conn.cursor.return_value.__enter__.return_value = cursor

    rows = load_edgar_companies(conn)

    assert rows == [(1, "Acme, Inc.", "acme")]
    cursor.execute.assert_called_once_with(
        "SELECT id, company_name FROM edgar_filings WHERE accelerator_id IS NULL"
    )


def test_cross_reference_reprocess_option_loads_all_filings():
    cursor = MagicMock()
    cursor.fetchall.return_value = []
    conn = MagicMock()
    conn.cursor.return_value.__enter__.return_value = cursor

    load_edgar_companies(conn, reprocess_all=True)

    cursor.execute.assert_called_once_with("SELECT id, company_name FROM edgar_filings")

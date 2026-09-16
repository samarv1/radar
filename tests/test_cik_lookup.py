from unittest.mock import Mock

from scrapers import cik_lookup


def test_authoritative_miss_records_checked_state(monkeypatch):
    conn = Mock()
    store_attempt = Mock()
    monkeypatch.setattr(cik_lookup, "search_edgar", lambda _: [])
    monkeypatch.setattr(cik_lookup, "get_connection", lambda: conn)
    monkeypatch.setattr(cik_lookup, "store_cik_attempt", store_attempt)

    cik_lookup._lookup_one((42, "Acme", 1, 1))

    store_attempt.assert_called_once_with(conn, 42, None, "not_found")
    conn.commit.assert_called_once()
    conn.close.assert_called_once()


def test_transient_search_failure_does_not_record_miss(monkeypatch):
    get_connection = Mock()
    monkeypatch.setattr(cik_lookup, "search_edgar", lambda _: None)
    monkeypatch.setattr(cik_lookup, "get_connection", get_connection)

    cik_lookup._lookup_one((42, "Acme", 1, 1))

    get_connection.assert_not_called()

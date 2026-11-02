from unittest.mock import MagicMock

import pytest

from scrapers import yc_hiring


@pytest.mark.parametrize("empty_field", [{}, {"website": None}, {"website": "  "}])
def test_missing_website_matches_by_name(monkeypatch, empty_field):
    conn, cursor = _mock_scrape(monkeypatch, [{"name": " Acme ", **empty_field}])
    cursor.fetchone.return_value = (7,)

    yc_hiring.scrape()

    assert cursor.execute.call_args_list[0].args[1] == ("Acme", None)
    assert cursor.execute.call_args_list[1].args[1] == ([7],)
    assert "SET yc_is_hiring = TRUE" in cursor.execute.call_args_list[1].args[0]
    conn.commit.assert_called_once()
    conn.close.assert_called_once()


@pytest.mark.parametrize("empty_field", [{}, {"name": None}, {"name": "  "}])
def test_missing_name_matches_by_website(monkeypatch, empty_field):
    conn, cursor = _mock_scrape(
        monkeypatch, [{"website": " https://acme.test ", **empty_field}]
    )
    cursor.fetchone.return_value = (7,)

    yc_hiring.scrape()

    assert cursor.execute.call_args_list[0].args[1] == (None, "https://acme.test")
    assert cursor.execute.call_args_list[1].args[1] == ([7],)
    conn.commit.assert_called_once()


@pytest.mark.parametrize(
    "company", [{}, {"name": None, "website": None}, {"name": " ", "website": " "}]
)
def test_empty_record_is_skipped_without_blocking_later_matches(monkeypatch, company):
    conn, cursor = _mock_scrape(monkeypatch, [company, {"name": "Acme"}])
    cursor.fetchone.return_value = (7,)

    yc_hiring.scrape()

    cursor.fetchone.assert_called_once()
    assert cursor.execute.call_args_list[0].args[1] == ("Acme", None)
    assert cursor.execute.call_args_list[1].args[1] == ([7],)
    conn.commit.assert_called_once()


def _mock_scrape(monkeypatch, companies):
    conn = MagicMock()
    cursor = conn.cursor.return_value.__enter__.return_value
    monkeypatch.setattr(yc_hiring, "get_connection", lambda: conn)
    monkeypatch.setattr(yc_hiring, "fetch_hiring_companies", lambda: companies)
    return conn, cursor

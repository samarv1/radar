from unittest.mock import MagicMock

from scrapers import enrich_edgar


def test_parse_enrichment_marks_malformed_xml_invalid():
    result = enrich_edgar.parse_enrichment("<broken")

    assert result == enrich_edgar.EnrichmentResult(parsed=False)


def test_parse_enrichment_accepts_valid_xml_with_no_optional_fields():
    result = enrich_edgar.parse_enrichment("<edgarSubmission />")

    assert result == enrich_edgar.EnrichmentResult(parsed=True)


def test_run_leaves_malformed_xml_pending(monkeypatch):
    conn, cursor = _connection_with_filing()
    monkeypatch.setattr(enrich_edgar, "get_connection", lambda: conn)
    monkeypatch.setattr(enrich_edgar, "fetch_xml", lambda _: "<broken")
    monkeypatch.setattr(enrich_edgar.time, "sleep", lambda _: None)

    enrich_edgar.run()

    assert cursor.execute.call_count == 1
    conn.commit.assert_called_once()


def test_run_completes_valid_all_null_xml(monkeypatch):
    conn, cursor = _connection_with_filing()
    monkeypatch.setattr(enrich_edgar, "get_connection", lambda: conn)
    monkeypatch.setattr(enrich_edgar, "fetch_xml", lambda _: "<edgarSubmission />")
    monkeypatch.setattr(enrich_edgar.time, "sleep", lambda _: None)

    enrich_edgar.run()

    assert cursor.execute.call_count == 2
    update = cursor.execute.call_args_list[1]
    assert "enriched_at = NOW()" in update.args[0]
    assert update.args[1] == (None, None, None, 7)
    conn.commit.assert_called_once()


def _connection_with_filing():
    conn = MagicMock()
    cursor = conn.cursor.return_value.__enter__.return_value
    cursor.fetchall.return_value = [(7, "Acme", "https://example.test/form.xml")]
    return conn, cursor

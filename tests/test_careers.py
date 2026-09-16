from unittest.mock import Mock

import requests

from scrapers.careers import ats_fetchers
from scrapers.careers.ats_fetchers import FetchResult
from scrapers.careers.categorize import categorize, classify
from scrapers.careers.db import sync_jobs
from scrapers.careers import discovery
from scrapers.careers import run


class Response:
    def __init__(self, status_code=200, payload=None):
        self.status_code = status_code
        self._payload = payload

    def json(self):
        if isinstance(self._payload, Exception):
            raise self._payload
        return self._payload


def test_classification_keeps_role_type_and_level_independent():
    classification = classify("Software Engineering Intern")

    assert classification.role_type == "engineering"
    assert classification.role_level == "intern"
    assert categorize("Software Engineering Intern") == "intern"


def test_greenhouse_distinguishes_empty_not_found_and_transient(monkeypatch):
    monkeypatch.setattr(ats_fetchers.time, "sleep", lambda _: None)

    monkeypatch.setattr(ats_fetchers.requests, "get", lambda *args, **kwargs: Response(payload={"jobs": []}))
    assert ats_fetchers.try_greenhouse("company").status == "empty"

    monkeypatch.setattr(ats_fetchers.requests, "get", lambda *args, **kwargs: Response(404, {}))
    assert ats_fetchers.try_greenhouse("company").status == "not_found"

    monkeypatch.setattr(ats_fetchers.requests, "get", lambda *args, **kwargs: Response(429, {}))
    assert ats_fetchers.try_greenhouse("company").status == "transient_error"

    def timeout(*args, **kwargs):
        raise requests.Timeout

    monkeypatch.setattr(ats_fetchers.requests, "get", timeout)
    assert ats_fetchers.try_greenhouse("company").status == "transient_error"


def test_malformed_success_response_is_transient(monkeypatch):
    monkeypatch.setattr(ats_fetchers.time, "sleep", lambda _: None)
    monkeypatch.setattr(
        ats_fetchers.requests,
        "get",
        lambda *args, **kwargs: Response(payload=ValueError("invalid json")),
    )

    assert ats_fetchers.try_greenhouse("company").status == "transient_error"


def test_ashby_normalizes_jobs_without_an_unsupported_date_field(monkeypatch):
    monkeypatch.setattr(ats_fetchers.time, "sleep", lambda _: None)
    response = Response(payload={
        "data": {
            "jobBoardWithTeams": {
                "teams": [{"id": "team-1", "name": "Engineering"}],
                "jobPostings": [{
                    "id": "job-1",
                    "title": "Software Engineer",
                    "locationName": "Remote",
                    "teamId": "team-1",
                }],
            },
        },
    })
    post = Mock(return_value=response)
    monkeypatch.setattr(ats_fetchers.requests, "post", post)

    result = ats_fetchers.try_ashby("company")

    assert result.status == "success"
    assert result.jobs == [{
        "job_id": "job-1",
        "title": "Software Engineer",
        "department": "Engineering",
        "location": "Remote",
        "job_url": "https://jobs.ashbyhq.com/company/job-1",
        "posted_at": None,
    }]
    assert "publishedAt" not in post.call_args.kwargs["json"]["query"]


def test_ashby_distinguishes_empty_and_missing_boards(monkeypatch):
    monkeypatch.setattr(ats_fetchers.time, "sleep", lambda _: None)
    responses = iter([
        Response(payload={
            "data": {
                "jobBoardWithTeams": {"teams": [], "jobPostings": []},
            },
        }),
        Response(payload={"data": {"jobBoardWithTeams": None}}),
    ])
    monkeypatch.setattr(ats_fetchers.requests, "post", lambda *args, **kwargs: next(responses))

    assert ats_fetchers.try_ashby("empty-company").status == "empty"
    assert ats_fetchers.try_ashby("missing-company").status == "not_found"


def test_ashby_graphql_and_malformed_responses_are_transient(monkeypatch):
    monkeypatch.setattr(ats_fetchers.time, "sleep", lambda _: None)
    responses = iter([
        Response(payload={"errors": [{"message": "query validation failed"}]}),
        Response(payload={"data": {"jobBoardWithTeams": {"teams": [], "jobPostings": {}}}}),
        Response(payload=ValueError("invalid json")),
    ])
    monkeypatch.setattr(ats_fetchers.requests, "post", lambda *args, **kwargs: next(responses))

    assert ats_fetchers.try_ashby("company").status == "transient_error"
    assert ats_fetchers.try_ashby("company").status == "transient_error"
    assert ats_fetchers.try_ashby("company").status == "transient_error"


def test_ashby_rate_limits_and_server_errors_are_transient(monkeypatch):
    monkeypatch.setattr(ats_fetchers.time, "sleep", lambda _: None)
    rate_limited = Mock(return_value=Response(429, {}))
    monkeypatch.setattr(ats_fetchers.requests, "post", rate_limited)

    assert ats_fetchers.try_ashby("company").status == "transient_error"
    assert rate_limited.call_count == 3

    monkeypatch.setattr(
        ats_fetchers.requests,
        "post",
        lambda *args, **kwargs: Response(500, {}),
    )
    assert ats_fetchers.try_ashby("company").status == "transient_error"


def test_known_board_transient_error_does_not_run_discovery(monkeypatch):
    monkeypatch.setitem(
        run.ATS_FETCHERS,
        "greenhouse",
        lambda slug: FetchResult("transient_error", "https://boards.greenhouse.io/company"),
    )
    discover = Mock()
    monkeypatch.setattr(run, "discover_ats_result", discover)

    result = run.resolve_careers({
        "website": "https://company.test",
        "careers_ats": "greenhouse",
        "careers_url": "https://boards.greenhouse.io/company",
    })

    assert result.status == "transient_error"
    discover.assert_not_called()


def test_discovery_timeout_is_transient(monkeypatch):
    monkeypatch.setattr(discovery.time, "sleep", lambda _: None)

    def timeout(*args, **kwargs):
        raise requests.Timeout

    monkeypatch.setattr(discovery.requests, "get", timeout)

    assert discovery.discover_ats_result("https://company.test").status == "transient_error"


def test_partial_discovery_failure_does_not_become_not_found(monkeypatch):
    monkeypatch.setattr(discovery.time, "sleep", lambda _: None)
    responses = iter([Response(404), requests.Timeout()])

    def mixed_result(*args, **kwargs):
        result = next(responses, requests.Timeout())
        if isinstance(result, Exception):
            raise result
        result.url = args[0]
        result.content = b""
        return result

    monkeypatch.setattr(discovery.requests, "get", mixed_result)

    assert discovery.discover_ats_result("https://company.test").status == "transient_error"


def test_transient_error_preserves_jobs_and_status(monkeypatch):
    connection = Mock()
    monkeypatch.setattr(
        run,
        "resolve_careers",
        lambda company: run.CareersResolution("transient_error", ats="greenhouse"),
    )
    sync = Mock()
    update = Mock()
    monkeypatch.setattr(run, "sync_jobs", sync)
    monkeypatch.setattr(run, "update_careers_status", update)

    found = run._scrape_one({"id": 1, "name": "Company", "website": "https://company.test"}, 1, 1, conn=connection)

    assert found is False
    connection.rollback.assert_called_once_with()
    connection.commit.assert_not_called()
    sync.assert_not_called()
    update.assert_not_called()


def test_authoritative_empty_board_clears_through_sync(monkeypatch):
    connection = Mock()
    board_url = "https://boards.greenhouse.io/company"
    monkeypatch.setattr(
        run,
        "resolve_careers",
        lambda company: run.CareersResolution("empty", ats="greenhouse", url=board_url, jobs=[]),
    )
    sync = Mock()
    update = Mock()
    monkeypatch.setattr(run, "sync_jobs", sync)
    monkeypatch.setattr(run, "update_careers_status", update)

    found = run._scrape_one({"id": 1, "name": "Company", "website": "https://company.test"}, 1, 1, conn=connection)

    assert found is True
    sync.assert_called_once_with(connection, 1, "greenhouse", [])
    update.assert_called_once_with(connection, 1, "greenhouse", board_url)
    connection.commit.assert_called_once_with()


class RecordingCursor:
    def __init__(self):
        self.executemany_call = None
        self.execute_calls = []

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return None

    def executemany(self, sql, rows):
        self.executemany_call = (sql, rows)

    def execute(self, sql, params):
        self.execute_calls.append((sql, params))


class RecordingConnection:
    def __init__(self):
        self.cursor_instance = RecordingCursor()

    def cursor(self):
        return self.cursor_instance


def test_sync_jobs_updates_mutable_fields_and_preserves_first_seen():
    connection = RecordingConnection()
    job = {
        "job_id": "job-1",
        "title": "Product Design Intern",
        "department": "Product",
        "location": "Remote",
        "job_url": "https://jobs.test/job-1",
        "posted_at": None,
    }

    sync_jobs(connection, 7, "greenhouse", [job])

    sql, rows = connection.cursor_instance.executemany_call
    assert "role_type = EXCLUDED.role_type" in sql
    assert "role_level = EXCLUDED.role_level" in sql
    assert "first_seen_at =" not in sql
    assert rows[0][6:9] == ("intern", "product", "intern")
    assert "DELETE FROM job_listings" in connection.cursor_instance.execute_calls[0][0]

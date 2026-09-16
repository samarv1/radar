from unittest.mock import Mock

from scrapers import producthunt


def test_fetch_launches_uses_requested_vote_threshold(monkeypatch):
    response = Mock(status_code=200)
    response.json.return_value = {
        "data": {
            "posts": {
                "edges": [
                    {"node": {"id": "1", "name": "Keep", "votesCount": 25}},
                    {"node": {"id": "2", "name": "Stop", "votesCount": 19}},
                ],
                "pageInfo": {"hasNextPage": True, "endCursor": "next"},
            }
        }
    }
    post = Mock(return_value=response)
    monkeypatch.setattr(producthunt.requests, "post", post)
    monkeypatch.setattr(producthunt.time, "sleep", lambda _: None)

    launches = producthunt.fetch_launches("token", days_back=7, min_votes=20)

    assert [launch["product_name"] for launch in launches] == ["Keep"]
    post.assert_called_once()

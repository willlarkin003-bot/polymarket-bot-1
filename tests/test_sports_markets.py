from unittest.mock import MagicMock, patch

from src.sports_markets import fetch_open_sports_markets


def _mock_response(payload):
    resp = MagicMock()
    resp.raise_for_status = MagicMock()
    resp.json = MagicMock(return_value=payload)
    return resp


def test_parses_team_named_outcomes():
    payload = [{
        "conditionId": "0xabc",
        "clobTokenIds": '["tok_yes", "tok_no"]',
        "outcomePrices": '["0.42", "0.58"]',
        "outcomes": '["Los Angeles Lakers", "Boston Celtics"]',
        "question": "Lakers vs Celtics",
        "description": "",
    }]
    with patch("src.sports_markets.requests.get", return_value=_mock_response(payload)):
        markets = fetch_open_sports_markets()
    assert len(markets) == 1
    m = markets[0]
    assert m.yes_token_id == "tok_yes"
    assert m.yes_price == 0.42
    assert m.outcome_labels == ["Los Angeles Lakers", "Boston Celtics"]


def test_defaults_outcome_labels_when_missing():
    payload = [{
        "conditionId": "0xdef",
        "clobTokenIds": ["tok_yes", "tok_no"],
        "outcomePrices": [0.6, 0.4],
        "question": "Will the Lakers win?",
        "description": "",
    }]
    with patch("src.sports_markets.requests.get", return_value=_mock_response(payload)):
        markets = fetch_open_sports_markets()
    assert markets[0].outcome_labels == ["Yes", "No"]


def test_skips_malformed_market_entries():
    payload = [{"conditionId": "0xbad"}]  # missing clobTokenIds etc.
    with patch("src.sports_markets.requests.get", return_value=_mock_response(payload)):
        markets = fetch_open_sports_markets()
    assert markets == []

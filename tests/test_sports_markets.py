from unittest.mock import MagicMock

import pytest

from src.sports_markets import fetch_open_sports_markets


def _fake_client(markets, bbo_by_slug):
    client = MagicMock()
    client.markets.list.return_value = {"markets": markets}
    client.markets.bbo.side_effect = lambda slug: bbo_by_slug[slug]
    return client


def _amount(value):
    return {"value": value, "currency": "USD"}


def test_parses_team_outcome_and_midpoint_price():
    markets = [{
        "slug": "chiefs-super-bowl",
        "title": "Will the Chiefs win the Super Bowl?",
        "description": "",
        "outcome": "Kansas City Chiefs",
        "active": True,
        "closed": False,
    }]
    bbo = {
        "chiefs-super-bowl": {
            "bestBid": _amount("0.40"),
            "bestAsk": _amount("0.44"),
        }
    }
    client = _fake_client(markets, bbo)
    result = fetch_open_sports_markets(client)
    assert len(result) == 1
    m = result[0]
    assert m.market_id == "chiefs-super-bowl"
    assert m.outcome_labels == ["Kansas City Chiefs"]
    assert m.yes_price == pytest.approx(0.42)


def test_falls_back_to_team_name_when_outcome_missing():
    markets = [{
        "slug": "ravens-super-bowl",
        "title": "Will the Ravens win the Super Bowl?",
        "description": "",
        "team": {"name": "Baltimore Ravens"},
        "active": True,
        "closed": False,
    }]
    bbo = {"ravens-super-bowl": {"bestBid": _amount("0.20"), "bestAsk": _amount("0.22")}}
    client = _fake_client(markets, bbo)
    result = fetch_open_sports_markets(client)
    assert result[0].outcome_labels == ["Baltimore Ravens"]


def test_skips_markets_missing_a_slug():
    markets = [{"title": "No slug here"}]
    client = _fake_client(markets, {})
    assert fetch_open_sports_markets(client) == []


def test_skips_markets_with_broken_bbo():
    markets = [{"slug": "broken-market", "title": "x", "outcome": "Team A"}]
    client = _fake_client(markets, {"broken-market": {"bestBid": _amount("0.5")}})  # missing bestAsk
    assert fetch_open_sports_markets(client) == []

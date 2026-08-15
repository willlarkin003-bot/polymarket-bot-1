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


def _market(slug, outcome="Kansas City Chiefs", title="Will the Chiefs win?"):
    return {"slug": slug, "title": title, "description": "", "outcome": outcome,
            "active": True, "closed": False}


def test_prefers_long_quote_when_present():
    bbo = {
        "chiefs-super-bowl": {
            "bestBid": _amount("0.40"),
            "bestAsk": _amount("0.44"),
            "longQuote": _amount("0.55"),
        }
    }
    client = _fake_client([_market("chiefs-super-bowl")], bbo)
    result = fetch_open_sports_markets(client)
    assert result[0].yes_price == pytest.approx(0.55)


def test_falls_back_to_bid_ask_midpoint_when_no_long_quote():
    bbo = {"chiefs-super-bowl": {"bestBid": _amount("0.40"), "bestAsk": _amount("0.44")}}
    client = _fake_client([_market("chiefs-super-bowl")], bbo)
    result = fetch_open_sports_markets(client)
    assert result[0].yes_price == pytest.approx(0.42)


def test_handles_one_sided_book_with_null_best_bid():
    # This is the real shape a thin/far-out futures market returns: bestBid is
    # explicitly null (not missing), only the ask side has depth.
    bbo = {
        "mlb-champ-nym": {
            "bestAsk": _amount("0.0020"),
            "bestBid": None,
            "askDepth": 11,
            "bidDepth": 0,
            "longQuote": _amount("0.0020"),
            "lastPriceSample": {
                "longPx": _amount("0.0010"),
                "shortPx": _amount("0.999"),
            },
        }
    }
    client = _fake_client([_market("mlb-champ-nym")], bbo)
    result = fetch_open_sports_markets(client)
    assert len(result) == 1
    assert result[0].yes_price == pytest.approx(0.0020)


def test_falls_back_to_last_price_sample_when_nothing_else_available():
    bbo = {
        "thin-market": {
            "bestBid": None,
            "bestAsk": None,
            "lastPriceSample": {"longPx": _amount("0.15")},
        }
    }
    client = _fake_client([_market("thin-market")], bbo)
    result = fetch_open_sports_markets(client)
    assert result[0].yes_price == pytest.approx(0.15)


def test_skips_market_with_no_usable_price_at_all():
    bbo = {"dead-market": {"bestBid": None, "bestAsk": None}}
    client = _fake_client([_market("dead-market")], bbo)
    assert fetch_open_sports_markets(client) == []


def test_falls_back_to_team_name_when_outcome_missing():
    markets = [{
        "slug": "ravens-super-bowl",
        "title": "Will the Ravens win the Super Bowl?",
        "description": "",
        "team": {"name": "Baltimore Ravens"},
        "active": True,
        "closed": False,
    }]
    bbo = {"ravens-super-bowl": {"longQuote": _amount("0.22")}}
    client = _fake_client(markets, bbo)
    result = fetch_open_sports_markets(client)
    assert result[0].outcome_labels == ["Baltimore Ravens"]


def test_skips_markets_missing_a_slug():
    markets = [{"title": "No slug here"}]
    client = _fake_client(markets, {})
    assert fetch_open_sports_markets(client) == []


def test_skips_markets_when_bbo_call_raises():
    client = _fake_client([_market("errors-out")], {})  # bbo_by_slug has no entry -> KeyError raised
    assert fetch_open_sports_markets(client) == []

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


def _bbo(**fields):
    """Wrap fields the way the live API actually nests them, under `marketData`."""
    return {"marketData": fields}


def _market(slug, outcome="Kansas City Chiefs", title="Will the Chiefs win?"):
    return {"slug": slug, "title": title, "description": "", "outcome": outcome,
            "active": True, "closed": False}


def test_real_ufc_market_response_shape():
    # Captured verbatim from a live account: client.markets.bbo() nests
    # everything under "marketData", not top-level as the SDK's type hints claim.
    bbo = {"aec-ufc-islmak-ianmac-2026-08-15": {
        "marketData": {
            "marketSlug": "aec-ufc-islmak-ianmac-2026-08-15",
            "currentPx": _amount("0.7400"),
            "lastTradePx": _amount("0.7500"),
            "settlementPx": _amount("0.7500"),
            "sharesTraded": "393224.0600",
            "openInterest": "471847.1900",
            "bestAsk": _amount("0.7500"),
            "bestBid": _amount("0.7400"),
            "askDepth": 18,
            "bidDepth": 20,
            "lastPriceSample": {
                "longPx": _amount("0.7500"),
                "shortPx": _amount("0.25"),
                "ts": "2026-08-15T20:13:58.063566775Z",
            },
            "longQuote": _amount("0.7500"),
            "shortQuote": _amount("0.26"),
        }
    }}
    client = _fake_client(
        [_market("aec-ufc-islmak-ianmac-2026-08-15", outcome="Islam Makhachev",
                  title="UFC: Makhachev vs McGregor")],
        bbo,
    )
    result = fetch_open_sports_markets(client)
    assert len(result) == 1
    assert result[0].yes_price == pytest.approx(0.75)
    assert result[0].outcome_labels == ["Islam Makhachev"]


def test_prefers_long_quote_when_present():
    bbo = {"chiefs-super-bowl": _bbo(
        bestBid=_amount("0.40"), bestAsk=_amount("0.44"), longQuote=_amount("0.55"),
    )}
    client = _fake_client([_market("chiefs-super-bowl")], bbo)
    result = fetch_open_sports_markets(client)
    assert result[0].yes_price == pytest.approx(0.55)


def test_falls_back_to_bid_ask_midpoint_when_no_long_quote():
    bbo = {"chiefs-super-bowl": _bbo(bestBid=_amount("0.40"), bestAsk=_amount("0.44"))}
    client = _fake_client([_market("chiefs-super-bowl")], bbo)
    result = fetch_open_sports_markets(client)
    assert result[0].yes_price == pytest.approx(0.42)


def test_handles_one_sided_book_with_null_best_bid():
    # Real shape a thin/far-out futures market returns: bestBid is explicitly
    # null (not missing), only the ask side has depth.
    bbo = {"mlb-champ-nym": _bbo(
        bestAsk=_amount("0.0020"), bestBid=None, askDepth=11, bidDepth=0,
        longQuote=_amount("0.0020"),
        lastPriceSample={"longPx": _amount("0.0010"), "shortPx": _amount("0.999")},
    )}
    client = _fake_client([_market("mlb-champ-nym")], bbo)
    result = fetch_open_sports_markets(client)
    assert len(result) == 1
    assert result[0].yes_price == pytest.approx(0.0020)


def test_falls_back_to_last_price_sample_when_nothing_else_available():
    bbo = {"thin-market": _bbo(
        bestBid=None, bestAsk=None, lastPriceSample={"longPx": _amount("0.15")},
    )}
    client = _fake_client([_market("thin-market")], bbo)
    result = fetch_open_sports_markets(client)
    assert result[0].yes_price == pytest.approx(0.15)


def test_skips_market_with_no_usable_price_at_all():
    bbo = {"dead-market": _bbo(bestBid=None, bestAsk=None)}
    client = _fake_client([_market("dead-market")], bbo)
    assert fetch_open_sports_markets(client) == []


def test_still_works_if_bbo_response_is_ever_flat_not_nested():
    # Defensive: if the API/SDK is ever fixed to match its own type hints and
    # returns fields top-level instead of under marketData, this should still work.
    bbo = {"chiefs-super-bowl": {"longQuote": _amount("0.60")}}
    client = _fake_client([_market("chiefs-super-bowl")], bbo)
    result = fetch_open_sports_markets(client)
    assert result[0].yes_price == pytest.approx(0.60)


def test_falls_back_to_team_name_when_outcome_missing():
    markets = [{
        "slug": "ravens-super-bowl",
        "title": "Will the Ravens win the Super Bowl?",
        "description": "",
        "team": {"name": "Baltimore Ravens"},
        "active": True,
        "closed": False,
    }]
    bbo = {"ravens-super-bowl": _bbo(longQuote=_amount("0.22"))}
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


def test_sorts_by_volume_descending_to_surface_liquid_markets():
    # The `sports` category is dominated by far-future, near-zero-liquidity
    # futures markets; without sorting, real actively-traded games can get
    # buried past the fetch limit entirely.
    client = _fake_client([], {})
    fetch_open_sports_markets(client)
    query = client.markets.list.call_args[0][0]
    assert query["orderBy"] == ["volume"]
    assert query["orderDirection"] == "desc"

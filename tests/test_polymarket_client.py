from unittest.mock import MagicMock

import pytest

from src.config import Config
from src.polymarket_client import PolymarketClient


def _config(dry_run=True, key_id="key", secret_key="secret"):
    return Config(
        key_id=key_id, secret_key=secret_key,
        anthropic_api_key="", anthropic_model="claude-haiku-4-5-20251001",
        odds_api_key="", odds_cache_ttl_seconds=1200, bankroll_usd=1000.0, kelly_multiplier=0.5,
        max_position_pct=0.05, max_open_positions=10,
        min_edge=0.04, min_bookmakers=3, match_confidence=0.6, dry_run=dry_run,
    )


def test_dry_run_never_calls_the_sdk():
    fake_sdk = MagicMock()
    client = PolymarketClient(_config(dry_run=True), fake_sdk)
    result = client.place_order("chiefs-super-bowl", "YES", 0.55, 50.0)
    fake_sdk.orders.create.assert_not_called()
    assert result["dry_run"] is True
    assert result["marketSlug"] == "chiefs-super-bowl"


def test_yes_side_maps_to_buy_long():
    fake_sdk = MagicMock()
    fake_sdk.orders.create.return_value = {"id": "order1"}
    client = PolymarketClient(_config(dry_run=False), fake_sdk)
    client.place_order("chiefs-super-bowl", "YES", 0.50, 50.0)
    body = fake_sdk.orders.create.call_args[0][0]
    assert body["intent"] == "ORDER_INTENT_BUY_LONG"
    assert body["marketSlug"] == "chiefs-super-bowl"
    assert body["price"] == {"value": "0.50", "currency": "USD"}
    assert body["quantity"] == 100


def test_no_side_maps_to_buy_short():
    fake_sdk = MagicMock()
    fake_sdk.orders.create.return_value = {"id": "order2"}
    client = PolymarketClient(_config(dry_run=False), fake_sdk)
    client.place_order("chiefs-super-bowl", "NO", 0.50, 50.0)
    body = fake_sdk.orders.create.call_args[0][0]
    assert body["intent"] == "ORDER_INTENT_BUY_SHORT"


def test_quantity_rounds_and_has_a_floor_of_one():
    fake_sdk = MagicMock()
    fake_sdk.orders.create.return_value = {"id": "order3"}
    client = PolymarketClient(_config(dry_run=False), fake_sdk)
    client.place_order("thin-market", "YES", 0.90, 0.10)
    body = fake_sdk.orders.create.call_args[0][0]
    assert body["quantity"] == 1


def test_live_mode_requires_credentials():
    fake_sdk = MagicMock()
    client = PolymarketClient(_config(dry_run=False, key_id="", secret_key=""), fake_sdk)
    with pytest.raises(RuntimeError):
        client.place_order("chiefs-super-bowl", "YES", 0.5, 50.0)
    fake_sdk.orders.create.assert_not_called()

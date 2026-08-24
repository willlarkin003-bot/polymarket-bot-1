import logging
import time

import pytest

import src.agent as agent_module
from src.config import Config
from src.sports_markets import SportsMarket
from src.state_store import StateStore, Trade


def _config(**overrides):
    base = dict(
        key_id="", secret_key="", anthropic_api_key="", anthropic_model="claude-haiku-4-5-20251001",
        odds_api_key="", odds_cache_ttl_seconds=1200,
        bankroll_usd=1000.0, kelly_multiplier=0.5, max_position_pct=0.05,
        max_open_positions=10, min_edge=0.04, min_bookmakers=3,
        match_confidence=0.6, dry_run=True,
    )
    base.update(overrides)
    return Config(**base)


def _market(slug, question="Will X win?", resolves_at=None):
    return SportsMarket(market_id=slug, question=question, description="",
                         yes_price=0.5, outcome_labels=["X"], resolves_at=resolves_at)


def test_logs_round_summary_with_skip_reasons(monkeypatch, tmp_path, caplog):
    db_path = str(tmp_path / "state.db")
    monkeypatch.setattr(agent_module, "StateStore", lambda: StateStore(db_path=db_path))
    monkeypatch.setattr(
        agent_module, "fetch_open_sports_markets",
        lambda client, **kwargs: [_market("m1"), _market("m2")],
    )

    agent = agent_module.TradingAgent(_config())

    with caplog.at_level(logging.INFO):
        agent.run_once()

    summary = next(r.message for r in caplog.records if "Round complete" in r.message)
    assert "2 markets" in summary
    assert "2 no signal" in summary
    assert "0 placed" in summary


def test_summary_counts_already_held_markets(monkeypatch, tmp_path, caplog):
    db_path = str(tmp_path / "state.db")
    monkeypatch.setattr(agent_module, "StateStore", lambda: StateStore(db_path=db_path))
    monkeypatch.setattr(
        agent_module, "fetch_open_sports_markets",
        lambda client, **kwargs: [_market("m1")],
    )

    agent = agent_module.TradingAgent(_config())
    agent.state.record_trade(
        Trade("m1", "YES", 0.5, 10.0, 0.6, 0.1, "sportsbook", "book_a, book_b", True, 0.0)
    )

    with caplog.at_level(logging.INFO):
        agent.run_once()

    summary = next(r.message for r in caplog.records if "Round complete" in r.message)
    assert "1 already held" in summary
    assert "0 no signal" in summary


def test_signal_engine_errors_are_tracked_separately_from_no_signal(monkeypatch, tmp_path, caplog):
    db_path = str(tmp_path / "state.db")
    monkeypatch.setattr(agent_module, "StateStore", lambda: StateStore(db_path=db_path))
    monkeypatch.setattr(
        agent_module, "fetch_open_sports_markets",
        lambda client, **kwargs: [_market("m1")],
    )

    class FailingSignalEngine:
        def __init__(self, *a, **kw):
            pass

        def estimate_probability(self, **kwargs):
            raise ValueError("bad model id")

    monkeypatch.setattr(agent_module, "SignalEngine", FailingSignalEngine)

    agent = agent_module.TradingAgent(_config(anthropic_api_key="sk-ant-fake"))

    with caplog.at_level(logging.INFO):
        agent.run_once()

    summary = next(r.message for r in caplog.records if "Round complete" in r.message)
    assert "1 no signal" in summary
    assert "1 signal errors" in summary

    rounds = agent.state.recent_rounds()
    assert rounds[0]["signal_errors"] == 1


def test_odds_events_are_cached_across_rounds_within_ttl(monkeypatch, tmp_path):
    db_path = str(tmp_path / "state.db")
    monkeypatch.setattr(agent_module, "StateStore", lambda: StateStore(db_path=db_path))
    monkeypatch.setattr(
        agent_module, "fetch_open_sports_markets",
        lambda client, **kwargs: [_market("nba-m1", question="Will the Lakers win the NBA game tonight?")],
    )

    call_count = {"n": 0}

    def fake_fetch_events(sport_key, api_key):
        call_count["n"] += 1
        return []

    monkeypatch.setattr(agent_module, "fetch_events", fake_fetch_events)

    fake_now = [1_000_000.0]
    monkeypatch.setattr(agent_module.time, "time", lambda: fake_now[0])

    agent = agent_module.TradingAgent(_config(odds_api_key="odds-key", odds_cache_ttl_seconds=1000))

    agent.run_once()
    agent.run_once()
    assert call_count["n"] == 1, "second round within the TTL should reuse cached odds"

    fake_now[0] += 2000  # advance past the TTL
    agent.run_once()
    assert call_count["n"] == 2, "odds should be re-fetched once the cache entry expires"


def test_settled_market_records_realized_pnl(monkeypatch, tmp_path, caplog):
    db_path = str(tmp_path / "state.db")
    monkeypatch.setattr(agent_module, "StateStore", lambda: StateStore(db_path=db_path))
    monkeypatch.setattr(agent_module, "fetch_open_sports_markets", lambda client, **kwargs: [])

    agent = agent_module.TradingAgent(_config())
    agent.state.record_trade(
        Trade("m1", "YES", 0.5, 40.0, 0.6, 0.1, "sportsbook", "", True, 0.0,
              market_question="Will the Lakers win?")
    )

    class FakeMarkets:
        def settlement(self, slug):
            return {"marketSlug": slug, "settlementPrice": {"value": "1.0", "currency": "USD"}, "settledAt": "x"}

    agent.polymarket.markets = FakeMarkets()

    with caplog.at_level(logging.INFO):
        agent.run_once()

    trades = agent.state.recent_trades()
    assert trades[0]["settled"] == 1
    assert trades[0]["outcome"] == "WON"
    assert trades[0]["profit_usd"] == pytest.approx(40.0)  # $40 at price 0.5 -> $80 payout, $40 profit

    summary = next(r.message for r in caplog.records if "Settled" in r.message and "trade(s)" in r.message)
    assert "1 trade(s)" in summary


def test_near_term_markets_win_position_slots_over_long_dated_ones(monkeypatch, tmp_path):
    db_path = str(tmp_path / "state.db")
    monkeypatch.setattr(agent_module, "StateStore", lambda: StateStore(db_path=db_path))

    now = time.time()
    far_market = _market("far", question="Season MVP", resolves_at=now + 60 * 86400)
    soon_market = _market("soon", question="Tonight's game", resolves_at=now + 2 * 86400)
    # Fetched with the long-dated one first, to prove sorting decides the outcome, not luck.
    monkeypatch.setattr(
        agent_module, "fetch_open_sports_markets", lambda client, **kwargs: [far_market, soon_market]
    )

    class FakeSignalEngine:
        def __init__(self, *a, **kw):
            pass

        def estimate_probability(self, **kwargs):
            return 0.7  # comfortably above min_edge for both markets

    monkeypatch.setattr(agent_module, "SignalEngine", FakeSignalEngine)

    agent = agent_module.TradingAgent(_config(
        anthropic_api_key="sk-ant-fake", max_open_positions=10,
        max_long_dated_positions=0, near_term_window_days=9,
    ))

    agent.run_once()

    trades = {t["market_id"] for t in agent.state.recent_trades()}
    assert trades == {"soon"}, "only the near-term market should get a slot when max_long_dated_positions=0"


def test_unresolved_market_stays_pending(monkeypatch, tmp_path):
    db_path = str(tmp_path / "state.db")
    monkeypatch.setattr(agent_module, "StateStore", lambda: StateStore(db_path=db_path))
    monkeypatch.setattr(agent_module, "fetch_open_sports_markets", lambda client, **kwargs: [])

    agent = agent_module.TradingAgent(_config())
    agent.state.record_trade(Trade("m1", "YES", 0.5, 40.0, 0.6, 0.1, "sportsbook", "", True, 0.0))

    class FakeMarkets:
        def settlement(self, slug):
            raise Exception("market has not settled yet")

    agent.polymarket.markets = FakeMarkets()
    agent.run_once()

    trades = agent.state.recent_trades()
    assert trades[0]["settled"] == 0

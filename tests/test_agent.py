import logging

import src.agent as agent_module
from src.config import Config
from src.sports_markets import SportsMarket
from src.state_store import StateStore


def _config(**overrides):
    base = dict(
        key_id="", secret_key="", anthropic_api_key="", odds_api_key="",
        bankroll_usd=1000.0, kelly_multiplier=0.5, max_position_pct=0.05,
        max_open_positions=10, min_edge=0.04, min_bookmakers=3,
        match_confidence=0.6, dry_run=True,
    )
    base.update(overrides)
    return Config(**base)


def _market(slug):
    return SportsMarket(market_id=slug, question="Will X win?", description="",
                         yes_price=0.5, outcome_labels=["X"])


def test_logs_round_summary_with_skip_reasons(monkeypatch, tmp_path, caplog):
    db_path = str(tmp_path / "state.db")
    monkeypatch.setattr(agent_module, "StateStore", lambda: StateStore(db_path=db_path))
    monkeypatch.setattr(
        agent_module, "fetch_open_sports_markets",
        lambda client: [_market("m1"), _market("m2")],
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
        lambda client: [_market("m1")],
    )

    agent = agent_module.TradingAgent(_config())
    from src.state_store import Trade
    agent.state.record_trade(
        Trade("m1", "YES", 0.5, 10.0, 0.6, 0.1, "sportsbook", True, 0.0)
    )

    with caplog.at_level(logging.INFO):
        agent.run_once()

    summary = next(r.message for r in caplog.records if "Round complete" in r.message)
    assert "1 already held" in summary
    assert "0 no signal" in summary

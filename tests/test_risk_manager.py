import os
import tempfile
import time
from dataclasses import replace

import pytest

from src.config import Config
from src.kelly import BetDecision
from src.risk_manager import RiskManager
from src.state_store import StateStore, Trade


@pytest.fixture
def config():
    return Config(
        key_id="", secret_key="",
        anthropic_api_key="", anthropic_model="claude-haiku-4-5-20251001",
        odds_api_key="", odds_cache_ttl_seconds=1200, bankroll_usd=1000.0, kelly_multiplier=0.5,
        max_position_pct=0.05, max_open_positions=2,
        min_edge=0.04, min_bookmakers=3, match_confidence=0.6, dry_run=True,
    )


@pytest.fixture
def state():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    store = StateStore(db_path=path)
    yield store
    os.remove(path)


def make_decision(side="YES", stake_usd=40.0):
    return BetDecision(side=side, edge=0.1, raw_kelly_fraction=0.1,
                        stake_fraction=stake_usd / 1000.0, stake_usd=stake_usd)


def test_rejects_pass_decision(config, state):
    risk = RiskManager(config, state)
    check = risk.check("m1", make_decision(side="PASS", stake_usd=0))
    assert not check.approved


def test_approves_valid_decision(config, state):
    risk = RiskManager(config, state)
    check = risk.check("m1", make_decision())
    assert check.approved


def test_rejects_stake_over_cap(config, state):
    risk = RiskManager(config, state)
    # max_position_pct=0.05 of $1000 = $50 cap
    check = risk.check("m1", make_decision(stake_usd=60.0))
    assert not check.approved


def test_rejects_duplicate_market(config, state):
    risk = RiskManager(config, state)
    from src.state_store import Trade
    state.record_trade(Trade("m1", "YES", 0.5, 40.0, 0.6, 0.1, "sportsbook", "book_a, book_b", True, 0.0))
    check = risk.check("m1", make_decision())
    assert not check.approved


def test_rejects_when_max_open_positions_reached(config, state):
    from src.state_store import Trade
    risk = RiskManager(config, state)
    state.record_trade(Trade("m1", "YES", 0.5, 40.0, 0.6, 0.1, "sportsbook", "book_a, book_b", True, time.time()))
    state.record_trade(Trade("m2", "YES", 0.5, 40.0, 0.6, 0.1, "sportsbook", "book_a, book_b", True, time.time()))
    check = risk.check("m3", make_decision())
    assert not check.approved


def test_max_open_positions_resets_for_positions_from_prior_weeks(config, state):
    from src.state_store import Trade
    risk = RiskManager(config, state)
    three_weeks_ago = time.time() - 21 * 86400
    state.record_trade(Trade("m1", "YES", 0.5, 40.0, 0.6, 0.1, "sportsbook", "book_a, book_b", True, three_weeks_ago))
    state.record_trade(Trade("m2", "YES", 0.5, 40.0, 0.6, 0.1, "sportsbook", "book_a, book_b", True, three_weeks_ago))
    check = risk.check("m3", make_decision())
    assert check.approved, "positions from prior weeks shouldn't count toward this week's max_open_positions"


def test_rejects_when_weekly_bankroll_exhausted(config, state):
    from src.state_store import Trade
    risk = RiskManager(config, state)
    state.record_trade(Trade("m1", "YES", 0.5, 980.0, 0.6, 0.1, "sportsbook", "book_a, book_b", True, time.time()))
    check = risk.check("m2", make_decision(stake_usd=40.0))
    assert not check.approved
    assert "weekly" in check.reason


def test_weekly_bankroll_resets_for_trades_from_prior_weeks(config, state):
    from src.state_store import Trade
    risk = RiskManager(config, state)
    three_weeks_ago = time.time() - 21 * 86400
    state.record_trade(Trade("m1", "YES", 0.5, 980.0, 0.6, 0.1, "sportsbook", "book_a, book_b", True, three_weeks_ago))
    check = risk.check("m2", make_decision(stake_usd=40.0))
    assert check.approved


def test_rejects_long_dated_bet_once_long_dated_cap_reached(config, state):
    config = replace(config, max_open_positions=10, max_long_dated_positions=1, near_term_window_days=9)
    risk = RiskManager(config, state)
    far_future = time.time() + 60 * 86400  # 60 days out - long-dated
    state.record_trade(
        Trade("m1", "YES", 0.5, 40.0, 0.6, 0.1, "sportsbook", "", True, time.time(),
              resolves_at=far_future)
    )
    check = risk.check("m2", make_decision(), resolves_at=far_future)
    assert not check.approved
    assert "long_dated" in check.reason


def test_near_term_bet_not_blocked_by_long_dated_cap(config, state):
    config = replace(config, max_open_positions=10, max_long_dated_positions=1, near_term_window_days=9)
    risk = RiskManager(config, state)
    far_future = time.time() + 60 * 86400
    state.record_trade(
        Trade("m1", "YES", 0.5, 40.0, 0.6, 0.1, "sportsbook", "", True, time.time(),
              resolves_at=far_future)
    )
    soon = time.time() + 2 * 86400  # 2 days out - well within the 9-day window
    check = risk.check("m2", make_decision(), resolves_at=soon)
    assert check.approved


def test_unknown_resolves_at_counts_as_long_dated(config, state):
    config = replace(config, max_open_positions=10, max_long_dated_positions=1, near_term_window_days=9)
    risk = RiskManager(config, state)
    state.record_trade(
        Trade("m1", "YES", 0.5, 40.0, 0.6, 0.1, "sportsbook", "", True, time.time(), resolves_at=0.0)
    )
    check = risk.check("m2", make_decision(), resolves_at=None)
    assert not check.approved
    assert "long_dated" in check.reason


def test_long_dated_cap_resets_for_positions_from_prior_weeks(config, state):
    config = replace(config, max_open_positions=10, max_long_dated_positions=1, near_term_window_days=9)
    risk = RiskManager(config, state)
    three_weeks_ago = time.time() - 21 * 86400
    far_future = time.time() + 60 * 86400
    state.record_trade(
        Trade("m1", "YES", 0.5, 40.0, 0.6, 0.1, "sportsbook", "", True, three_weeks_ago,
              resolves_at=far_future)
    )
    check = risk.check("m2", make_decision(), resolves_at=far_future)
    assert check.approved


def test_approves_bet_within_default_odds_range(config, state):
    risk = RiskManager(config, state)
    check = risk.check("m1", make_decision(), price=0.5)  # -100, within default -150..+600
    assert check.approved


def test_rejects_longshot_bet_outside_odds_range(config, state):
    # ~2% implied win probability -> roughly +4900, e.g. risking $25 to win $2500
    risk = RiskManager(config, state)
    check = risk.check("m1", make_decision(), price=0.02)
    assert not check.approved
    assert "odds" in check.reason


def test_rejects_heavily_favored_bet_outside_odds_range(config, state):
    risk = RiskManager(config, state)
    check = risk.check("m1", make_decision(), price=0.8)  # -400, more favored than -150
    assert not check.approved
    assert "odds" in check.reason


def test_skips_odds_range_check_when_price_not_given(config, state):
    risk = RiskManager(config, state)
    check = risk.check("m1", make_decision())  # no price passed
    assert check.approved


def test_odds_range_is_configurable(config, state):
    config = replace(config, min_american_odds=-1000.0, max_american_odds=5000.0)
    risk = RiskManager(config, state)
    check = risk.check("m1", make_decision(), price=0.02)  # would be rejected under the default range
    assert check.approved

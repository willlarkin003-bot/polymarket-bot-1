import os
import tempfile

import pytest

from src.config import Config
from src.kelly import BetDecision
from src.risk_manager import RiskManager
from src.state_store import StateStore


@pytest.fixture
def config():
    return Config(
        private_key="", funder_address="", clob_host="", chain_id=137,
        anthropic_api_key="", bankroll_usd=1000.0, kelly_multiplier=0.5,
        max_position_pct=0.05, max_open_positions=2, max_daily_loss_pct=0.1,
        min_edge=0.04, dry_run=True,
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
    state.record_trade(Trade("m1", "YES", 0.5, 40.0, 0.6, 0.1, True, 0.0))
    check = risk.check("m1", make_decision())
    assert not check.approved


def test_rejects_when_max_open_positions_reached(config, state):
    from src.state_store import Trade
    risk = RiskManager(config, state)
    state.record_trade(Trade("m1", "YES", 0.5, 40.0, 0.6, 0.1, True, 0.0))
    state.record_trade(Trade("m2", "YES", 0.5, 40.0, 0.6, 0.1, True, 0.0))
    check = risk.check("m3", make_decision())
    assert not check.approved

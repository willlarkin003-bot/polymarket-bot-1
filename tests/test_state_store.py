import sqlite3
import time

import pytest

from src.state_store import RoundSummary, StateStore, Trade


@pytest.fixture
def state(tmp_path):
    return StateStore(db_path=str(tmp_path / "state.db"))


def test_record_and_query_trade_with_source(state):
    state.record_trade(Trade("m1", "YES", 0.5, 40.0, 0.6, 0.1, "sportsbook", True, time.time()))
    assert state.has_position("m1")
    trades = state.recent_trades()
    assert len(trades) == 1
    assert trades[0]["source"] == "sportsbook"


def test_record_and_query_round_summary(state):
    state.record_round(RoundSummary(
        markets_fetched=50, already_held=2, no_signal=45, signal_errors=3, risk_rejected=1, placed=2,
        timestamp=time.time(),
    ))
    rounds = state.recent_rounds()
    assert len(rounds) == 1
    assert rounds[0]["markets_fetched"] == 50
    assert rounds[0]["signal_errors"] == 3
    assert rounds[0]["placed"] == 2


def test_recent_trades_and_rounds_are_ordered_newest_first(state):
    state.record_trade(Trade("old", "YES", 0.5, 10.0, 0.6, 0.1, "llm", True, 100.0))
    state.record_trade(Trade("new", "YES", 0.5, 10.0, 0.6, 0.1, "llm", True, 200.0))
    trades = state.recent_trades()
    assert [t["market_id"] for t in trades] == ["new", "old"]


def test_migrates_db_created_before_source_column_existed(tmp_path):
    db_path = str(tmp_path / "old.db")
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE trades (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                market_id TEXT NOT NULL,
                side TEXT NOT NULL,
                price REAL NOT NULL,
                stake_usd REAL NOT NULL,
                model_prob REAL NOT NULL,
                edge REAL NOT NULL,
                dry_run INTEGER NOT NULL,
                timestamp REAL NOT NULL
            )
            """
        )
        conn.execute(
            "INSERT INTO trades (market_id, side, price, stake_usd, model_prob, edge, dry_run, timestamp) "
            "VALUES ('old-market', 'YES', 0.5, 10.0, 0.6, 0.1, 1, 0.0)"
        )
        conn.commit()

    store = StateStore(db_path=db_path)  # should migrate in place, not raise
    assert store.has_position("old-market")

    store.record_trade(Trade("new-market", "YES", 0.5, 10.0, 0.6, 0.1, "llm", True, time.time()))
    trades = store.recent_trades()
    assert {t["market_id"] for t in trades} == {"old-market", "new-market"}


def test_migrates_rounds_table_created_before_signal_errors_column_existed(tmp_path):
    db_path = str(tmp_path / "old_rounds.db")
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE rounds (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                markets_fetched INTEGER NOT NULL,
                already_held INTEGER NOT NULL,
                no_signal INTEGER NOT NULL,
                risk_rejected INTEGER NOT NULL,
                placed INTEGER NOT NULL,
                timestamp REAL NOT NULL
            )
            """
        )
        conn.execute(
            "INSERT INTO rounds (markets_fetched, already_held, no_signal, risk_rejected, placed, timestamp) "
            "VALUES (50, 2, 45, 1, 2, 0.0)"
        )
        conn.commit()

    store = StateStore(db_path=db_path)  # should migrate in place, not raise
    rounds = store.recent_rounds()
    assert len(rounds) == 1
    assert rounds[0]["signal_errors"] == 0  # backfilled default for the pre-existing row

    store.record_round(RoundSummary(
        markets_fetched=10, already_held=0, no_signal=5, signal_errors=2, risk_rejected=0, placed=3,
        timestamp=time.time(),
    ))
    rounds = store.recent_rounds()
    assert len(rounds) == 2

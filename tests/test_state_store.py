import sqlite3
import time

import pytest

from src.state_store import RoundSummary, StateStore, Trade


@pytest.fixture
def state(tmp_path):
    return StateStore(db_path=str(tmp_path / "state.db"))


def test_record_and_query_trade_with_source(state):
    state.record_trade(Trade("m1", "YES", 0.5, 40.0, 0.6, 0.1, "sportsbook", "book_a, book_b", True, time.time()))
    assert state.has_position("m1")
    trades = state.recent_trades()
    assert len(trades) == 1
    assert trades[0]["source"] == "sportsbook"
    assert trades[0]["bookmakers"] == "book_a, book_b"


def test_record_trade_stores_market_question(state):
    state.record_trade(
        Trade("m1", "YES", 0.5, 40.0, 0.6, 0.1, "sportsbook", "", True, time.time(),
              market_question="Will the Lakers win?")
    )
    trades = state.recent_trades()
    assert trades[0]["market_question"] == "Will the Lakers win?"
    assert trades[0]["settled"] == 0


def test_unsettled_trades_excludes_settled_ones(state):
    state.record_trade(Trade("m1", "YES", 0.5, 40.0, 0.6, 0.1, "sportsbook", "", True, time.time()))
    state.record_trade(Trade("m2", "YES", 0.5, 40.0, 0.6, 0.1, "sportsbook", "", True, time.time()))
    unsettled = state.unsettled_trades()
    assert {t["market_id"] for t in unsettled} == {"m1", "m2"}

    trade_id = next(t["id"] for t in unsettled if t["market_id"] == "m1")
    state.mark_settled(trade_id, outcome="WON", payout_usd=72.7, profit_usd=32.7, settled_at=time.time())

    unsettled = state.unsettled_trades()
    assert {t["market_id"] for t in unsettled} == {"m2"}

    settled = next(t for t in state.recent_trades() if t["market_id"] == "m1")
    assert settled["settled"] == 1
    assert settled["outcome"] == "WON"
    assert settled["profit_usd"] == pytest.approx(32.7)


def test_pnl_summary_buckets_realized_profit(state):
    now = time.time()
    state.record_trade(Trade("m1", "YES", 0.5, 40.0, 0.6, 0.1, "sportsbook", "", True, now))
    state.record_trade(Trade("m2", "YES", 0.5, 40.0, 0.6, 0.1, "sportsbook", "", True, now))
    state.record_trade(Trade("m3", "YES", 0.5, 40.0, 0.6, 0.1, "sportsbook", "", True, now))

    ids = {t["market_id"]: t["id"] for t in state.unsettled_trades()}
    state.mark_settled(ids["m1"], outcome="WON", payout_usd=60.0, profit_usd=20.0, settled_at=now)
    state.mark_settled(ids["m2"], outcome="LOST", payout_usd=0.0, profit_usd=-40.0, settled_at=now)
    # m3 stays unsettled - pending

    summary = state.pnl_summary()
    assert summary["daily"]["profit_usd"] == pytest.approx(-20.0)
    assert summary["daily"]["settled_count"] == 2
    assert summary["all_time"]["profit_usd"] == pytest.approx(-20.0)
    assert summary["wins"] == 1
    assert summary["losses"] == 1
    assert summary["pending"]["count"] == 1
    assert summary["pending"]["stake_usd"] == pytest.approx(40.0)


def test_pnl_summary_excludes_trades_settled_before_the_bucket_cutoff(state):
    now = time.time()
    three_weeks_ago = now - 21 * 86400
    state.record_trade(Trade("old", "YES", 0.5, 40.0, 0.6, 0.1, "sportsbook", "", True, three_weeks_ago))
    trade_id = state.unsettled_trades()[0]["id"]
    state.mark_settled(trade_id, outcome="WON", payout_usd=60.0, profit_usd=20.0, settled_at=three_weeks_ago)

    summary = state.pnl_summary()
    assert summary["weekly"]["profit_usd"] == 0.0
    assert summary["weekly"]["settled_count"] == 0
    assert summary["all_time"]["profit_usd"] == pytest.approx(20.0)


def test_record_trade_stores_resolves_at(state):
    resolves_at = time.time() + 30 * 86400
    state.record_trade(
        Trade("m1", "YES", 0.5, 40.0, 0.6, 0.1, "sportsbook", "", True, time.time(),
              resolves_at=resolves_at)
    )
    trades = state.recent_trades()
    assert trades[0]["resolves_at"] == pytest.approx(resolves_at)


def test_long_dated_position_count_counts_far_out_and_unknown_dates(state):
    now = time.time()
    near_term_cutoff = now + 9 * 86400
    state.record_trade(
        Trade("far", "YES", 0.5, 40.0, 0.6, 0.1, "sportsbook", "", True, now,
              resolves_at=now + 60 * 86400)  # long-dated
    )
    state.record_trade(
        Trade("unknown", "YES", 0.5, 40.0, 0.6, 0.1, "sportsbook", "", True, now, resolves_at=0.0)
    )
    state.record_trade(
        Trade("soon", "YES", 0.5, 40.0, 0.6, 0.1, "sportsbook", "", True, now,
              resolves_at=now + 2 * 86400)  # near-term
    )
    assert state.long_dated_position_count(near_term_cutoff) == 2


def test_long_dated_position_count_resets_for_positions_from_prior_weeks(state):
    three_weeks_ago = time.time() - 21 * 86400
    near_term_cutoff = time.time() + 9 * 86400
    state.record_trade(
        Trade("old-far", "YES", 0.5, 40.0, 0.6, 0.1, "sportsbook", "", True, three_weeks_ago,
              resolves_at=time.time() + 60 * 86400)
    )
    assert state.long_dated_position_count(near_term_cutoff) == 0


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
    state.record_trade(Trade("old", "YES", 0.5, 10.0, 0.6, 0.1, "llm", "", True, 100.0))
    state.record_trade(Trade("new", "YES", 0.5, 10.0, 0.6, 0.1, "llm", "", True, 200.0))
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

    store.record_trade(Trade("new-market", "YES", 0.5, 10.0, 0.6, 0.1, "llm", "", True, time.time()))
    trades = store.recent_trades()
    assert {t["market_id"] for t in trades} == {"old-market", "new-market"}


def test_migrates_db_created_before_settlement_columns_existed(tmp_path):
    db_path = str(tmp_path / "old_settlement.db")
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
                source TEXT NOT NULL DEFAULT '',
                bookmakers TEXT NOT NULL DEFAULT '',
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
    unsettled = store.unsettled_trades()
    assert len(unsettled) == 1
    assert unsettled[0]["market_question"] == ""
    assert unsettled[0]["resolves_at"] == 0

    summary = store.pnl_summary()
    assert summary["pending"]["count"] == 1
    # the migrated row's timestamp is 0.0 (epoch), so it's outside "this week" and
    # doesn't count - this just confirms the migration didn't crash the query.
    assert store.long_dated_position_count(time.time() + 9 * 86400) == 0


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

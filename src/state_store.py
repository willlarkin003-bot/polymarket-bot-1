import sqlite3
import time
from contextlib import closing
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import List


def _current_week_start_ts() -> float:
    """Start of the current calendar week (Monday 00:00 UTC), as a Unix timestamp."""
    now = datetime.now(timezone.utc)
    monday = now.date() - timedelta(days=now.weekday())
    week_start = datetime(monday.year, monday.month, monday.day, tzinfo=timezone.utc)
    return week_start.timestamp()


@dataclass(frozen=True)
class Trade:
    market_id: str
    side: str
    price: float
    stake_usd: float
    model_prob: float
    edge: float
    source: str  # "sportsbook" or "llm" - which signal produced this bet
    dry_run: bool
    timestamp: float


@dataclass(frozen=True)
class RoundSummary:
    markets_fetched: int
    already_held: int
    no_signal: int
    signal_errors: int  # subset of no_signal caused by an exception (e.g. bad model/API key), not a real "no edge"
    risk_rejected: int
    placed: int
    timestamp: float


class StateStore:
    def __init__(self, db_path: str = "agent_state.db"):
        self.db_path = db_path
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.db_path)

    def _init_schema(self) -> None:
        with closing(self._connect()) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS trades (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    market_id TEXT NOT NULL,
                    side TEXT NOT NULL,
                    price REAL NOT NULL,
                    stake_usd REAL NOT NULL,
                    model_prob REAL NOT NULL,
                    edge REAL NOT NULL,
                    source TEXT NOT NULL DEFAULT '',
                    dry_run INTEGER NOT NULL,
                    timestamp REAL NOT NULL
                )
                """
            )
            # Migrate DBs created before the `source` column existed.
            existing_cols = {row[1] for row in conn.execute("PRAGMA table_info(trades)")}
            if "source" not in existing_cols:
                conn.execute("ALTER TABLE trades ADD COLUMN source TEXT NOT NULL DEFAULT ''")

            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_trades_market_id ON trades(market_id)"
            )

            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS rounds (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    markets_fetched INTEGER NOT NULL,
                    already_held INTEGER NOT NULL,
                    no_signal INTEGER NOT NULL,
                    signal_errors INTEGER NOT NULL DEFAULT 0,
                    risk_rejected INTEGER NOT NULL,
                    placed INTEGER NOT NULL,
                    timestamp REAL NOT NULL
                )
                """
            )
            # Migrate DBs created before the `signal_errors` column existed.
            existing_round_cols = {row[1] for row in conn.execute("PRAGMA table_info(rounds)")}
            if "signal_errors" not in existing_round_cols:
                conn.execute("ALTER TABLE rounds ADD COLUMN signal_errors INTEGER NOT NULL DEFAULT 0")

            conn.commit()

    def has_position(self, market_id: str) -> bool:
        with closing(self._connect()) as conn:
            row = conn.execute(
                "SELECT 1 FROM trades WHERE market_id = ? LIMIT 1", (market_id,)
            ).fetchone()
            return row is not None

    def record_trade(self, trade: Trade) -> None:
        with closing(self._connect()) as conn:
            conn.execute(
                """
                INSERT INTO trades
                    (market_id, side, price, stake_usd, model_prob, edge, source, dry_run, timestamp)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    trade.market_id,
                    trade.side,
                    trade.price,
                    trade.stake_usd,
                    trade.model_prob,
                    trade.edge,
                    trade.source,
                    int(trade.dry_run),
                    trade.timestamp,
                ),
            )
            conn.commit()

    def record_round(self, round_summary: RoundSummary) -> None:
        with closing(self._connect()) as conn:
            conn.execute(
                """
                INSERT INTO rounds
                    (markets_fetched, already_held, no_signal, signal_errors, risk_rejected, placed, timestamp)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    round_summary.markets_fetched,
                    round_summary.already_held,
                    round_summary.no_signal,
                    round_summary.signal_errors,
                    round_summary.risk_rejected,
                    round_summary.placed,
                    round_summary.timestamp,
                ),
            )
            conn.commit()

    def recent_trades(self, limit: int = 50) -> List[dict]:
        with closing(self._connect()) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT * FROM trades ORDER BY timestamp DESC LIMIT ?", (limit,)
            ).fetchall()
            return [dict(row) for row in rows]

    def recent_rounds(self, limit: int = 50) -> List[dict]:
        with closing(self._connect()) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT * FROM rounds ORDER BY timestamp DESC LIMIT ?", (limit,)
            ).fetchall()
            return [dict(row) for row in rows]

    def open_position_count(self) -> int:
        with closing(self._connect()) as conn:
            row = conn.execute("SELECT COUNT(DISTINCT market_id) FROM trades").fetchone()
            return row[0] if row else 0

    def spent_this_week_usd(self) -> float:
        """Total staked USD on trades opened since the start of the current calendar
        week (Monday 00:00 UTC). Resets automatically once a new week begins."""
        cutoff = _current_week_start_ts()
        with closing(self._connect()) as conn:
            row = conn.execute(
                "SELECT COALESCE(SUM(stake_usd), 0) FROM trades WHERE timestamp >= ?",
                (cutoff,),
            ).fetchone()
            return row[0] if row else 0.0

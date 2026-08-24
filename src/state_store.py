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


def _day_start_ts() -> float:
    now = datetime.now(timezone.utc)
    return datetime(now.year, now.month, now.day, tzinfo=timezone.utc).timestamp()


def _month_start_ts() -> float:
    now = datetime.now(timezone.utc)
    return datetime(now.year, now.month, 1, tzinfo=timezone.utc).timestamp()


def _year_start_ts() -> float:
    now = datetime.now(timezone.utc)
    return datetime(now.year, 1, 1, tzinfo=timezone.utc).timestamp()


@dataclass(frozen=True)
class Trade:
    market_id: str
    side: str
    price: float
    stake_usd: float
    model_prob: float
    edge: float
    source: str  # "sportsbook" or "llm" - which signal produced this bet
    bookmakers: str  # comma-separated book names backing a "sportsbook" trade, "" for "llm"
    dry_run: bool
    timestamp: float
    market_question: str = ""  # human-readable market title, e.g. "Will the Lakers win?"
    resolves_at: float = 0.0  # market's endDate as a Unix timestamp, 0 if unknown
    avg_book_odds: float = 0.0  # average raw American odds across contributing books for the side bet, 0 if unknown/llm


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
                    bookmakers TEXT NOT NULL DEFAULT '',
                    dry_run INTEGER NOT NULL,
                    timestamp REAL NOT NULL,
                    market_question TEXT NOT NULL DEFAULT '',
                    settled INTEGER NOT NULL DEFAULT 0,
                    outcome TEXT NOT NULL DEFAULT '',
                    payout_usd REAL NOT NULL DEFAULT 0,
                    profit_usd REAL NOT NULL DEFAULT 0,
                    settled_at REAL NOT NULL DEFAULT 0,
                    resolves_at REAL NOT NULL DEFAULT 0,
                    avg_book_odds REAL NOT NULL DEFAULT 0
                )
                """
            )
            # Migrate DBs created before these columns existed.
            existing_cols = {row[1] for row in conn.execute("PRAGMA table_info(trades)")}
            if "source" not in existing_cols:
                conn.execute("ALTER TABLE trades ADD COLUMN source TEXT NOT NULL DEFAULT ''")
            if "bookmakers" not in existing_cols:
                conn.execute("ALTER TABLE trades ADD COLUMN bookmakers TEXT NOT NULL DEFAULT ''")
            if "market_question" not in existing_cols:
                conn.execute("ALTER TABLE trades ADD COLUMN market_question TEXT NOT NULL DEFAULT ''")
            if "settled" not in existing_cols:
                conn.execute("ALTER TABLE trades ADD COLUMN settled INTEGER NOT NULL DEFAULT 0")
            if "outcome" not in existing_cols:
                conn.execute("ALTER TABLE trades ADD COLUMN outcome TEXT NOT NULL DEFAULT ''")
            if "payout_usd" not in existing_cols:
                conn.execute("ALTER TABLE trades ADD COLUMN payout_usd REAL NOT NULL DEFAULT 0")
            if "profit_usd" not in existing_cols:
                conn.execute("ALTER TABLE trades ADD COLUMN profit_usd REAL NOT NULL DEFAULT 0")
            if "settled_at" not in existing_cols:
                conn.execute("ALTER TABLE trades ADD COLUMN settled_at REAL NOT NULL DEFAULT 0")
            if "resolves_at" not in existing_cols:
                conn.execute("ALTER TABLE trades ADD COLUMN resolves_at REAL NOT NULL DEFAULT 0")
            if "avg_book_odds" not in existing_cols:
                conn.execute("ALTER TABLE trades ADD COLUMN avg_book_odds REAL NOT NULL DEFAULT 0")

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
                    (market_id, side, price, stake_usd, model_prob, edge, source, bookmakers, dry_run, timestamp, market_question, resolves_at, avg_book_odds)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    trade.market_id,
                    trade.side,
                    trade.price,
                    trade.stake_usd,
                    trade.model_prob,
                    trade.edge,
                    trade.source,
                    trade.bookmakers,
                    int(trade.dry_run),
                    trade.timestamp,
                    trade.market_question,
                    trade.resolves_at,
                    trade.avg_book_odds,
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
        """Distinct markets bet on since the current calendar week began (Monday
        00:00 UTC) - mirrors the weekly bankroll reset. Without this cutoff, this
        count only ever grows (nothing here tracks market settlement to free up a
        slot), so MAX_OPEN_POSITIONS would act as a one-time lifetime cap instead
        of a per-week one, permanently freezing new bets once it's ever been hit."""
        cutoff = _current_week_start_ts()
        with closing(self._connect()) as conn:
            row = conn.execute(
                "SELECT COUNT(DISTINCT market_id) FROM trades WHERE timestamp >= ?",
                (cutoff,),
            ).fetchone()
            return row[0] if row else 0

    def long_dated_position_count(self, near_term_cutoff: float) -> int:
        """Distinct markets bet on this week whose market resolves after
        `near_term_cutoff` - or has no known resolution date at all, treated
        conservatively as long-dated. Subset of open_position_count that
        MAX_LONG_DATED_POSITIONS caps, reserving the rest of the weekly
        position budget for markets resolving soon."""
        week_cutoff = _current_week_start_ts()
        with closing(self._connect()) as conn:
            row = conn.execute(
                "SELECT COUNT(DISTINCT market_id) FROM trades "
                "WHERE timestamp >= ? AND (resolves_at = 0 OR resolves_at > ?)",
                (week_cutoff, near_term_cutoff),
            ).fetchone()
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

    def unsettled_trades(self) -> List[dict]:
        with closing(self._connect()) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute("SELECT * FROM trades WHERE settled = 0").fetchall()
            return [dict(row) for row in rows]

    def mark_settled(
        self, trade_id: int, outcome: str, payout_usd: float, profit_usd: float, settled_at: float
    ) -> None:
        with closing(self._connect()) as conn:
            conn.execute(
                """
                UPDATE trades
                SET settled = 1, outcome = ?, payout_usd = ?, profit_usd = ?, settled_at = ?
                WHERE id = ?
                """,
                (outcome, payout_usd, profit_usd, settled_at, trade_id),
            )
            conn.commit()

    def pnl_summary(self) -> dict:
        """Realized profit/loss, bucketed by when each trade settled (not when it
        was placed) against UTC calendar boundaries - today since midnight, this
        week since Monday 00:00, this month since the 1st, this year since Jan 1.
        Includes dry-run trades: since the agent never closes/exits a position
        itself, this is the only way to see what the strategy would have earned."""
        with closing(self._connect()) as conn:
            def _bucket(cutoff: float) -> dict:
                row = conn.execute(
                    "SELECT COALESCE(SUM(profit_usd), 0), COUNT(*) FROM trades "
                    "WHERE settled = 1 AND settled_at >= ?",
                    (cutoff,),
                ).fetchone()
                return {"profit_usd": row[0], "settled_count": row[1]}

            summary = {
                "daily": _bucket(_day_start_ts()),
                "weekly": _bucket(_current_week_start_ts()),
                "monthly": _bucket(_month_start_ts()),
                "yearly": _bucket(_year_start_ts()),
                "all_time": _bucket(0.0),
            }

            wins, losses = conn.execute(
                "SELECT "
                "  SUM(CASE WHEN outcome = 'WON' THEN 1 ELSE 0 END), "
                "  SUM(CASE WHEN outcome = 'LOST' THEN 1 ELSE 0 END) "
                "FROM trades WHERE settled = 1"
            ).fetchone()
            summary["wins"] = wins or 0
            summary["losses"] = losses or 0

            pending_count, pending_stake = conn.execute(
                "SELECT COUNT(*), COALESCE(SUM(stake_usd), 0) FROM trades WHERE settled = 0"
            ).fetchone()
            summary["pending"] = {"count": pending_count, "stake_usd": pending_stake}

            return summary

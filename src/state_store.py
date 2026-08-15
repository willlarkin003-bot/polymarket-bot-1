import sqlite3
import time
from contextlib import closing
from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class Trade:
    market_id: str
    side: str
    price: float
    stake_usd: float
    model_prob: float
    edge: float
    dry_run: bool
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
                    dry_run INTEGER NOT NULL,
                    timestamp REAL NOT NULL
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_trades_market_id ON trades(market_id)"
            )
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
                    (market_id, side, price, stake_usd, model_prob, edge, dry_run, timestamp)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    trade.market_id,
                    trade.side,
                    trade.price,
                    trade.stake_usd,
                    trade.model_prob,
                    trade.edge,
                    int(trade.dry_run),
                    trade.timestamp,
                ),
            )
            conn.commit()

    def open_position_count(self) -> int:
        with closing(self._connect()) as conn:
            row = conn.execute("SELECT COUNT(DISTINCT market_id) FROM trades").fetchone()
            return row[0] if row else 0

    def realized_loss_today_usd(self) -> float:
        """Placeholder for daily-loss tracking: sums staked USD on trades opened in the
        last 24h. Wire this up to actual settlement/PnL data once positions resolve."""
        cutoff = time.time() - 86400
        with closing(self._connect()) as conn:
            row = conn.execute(
                "SELECT COALESCE(SUM(stake_usd), 0) FROM trades WHERE timestamp >= ?",
                (cutoff,),
            ).fetchone()
            return row[0] if row else 0.0

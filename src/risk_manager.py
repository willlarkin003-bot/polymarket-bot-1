from dataclasses import dataclass

from src.config import Config
from src.kelly import BetDecision
from src.state_store import StateStore


@dataclass(frozen=True)
class RiskCheck:
    approved: bool
    reason: str


class RiskManager:
    def __init__(self, config: Config, state: StateStore):
        self.config = config
        self.state = state

    def check(self, market_id: str, decision: BetDecision) -> RiskCheck:
        if decision.side == "PASS":
            return RiskCheck(False, "no edge above min_edge threshold")

        if decision.stake_usd <= 0:
            return RiskCheck(False, "sized stake is zero or negative")

        if self.state.has_position(market_id):
            return RiskCheck(False, "already have an open position in this market")

        if self.state.open_position_count() >= self.config.max_open_positions:
            return RiskCheck(False, "max_open_positions reached")

        weekly_spent = self.state.spent_this_week_usd()
        if weekly_spent + decision.stake_usd > self.config.bankroll_usd:
            return RiskCheck(False, "weekly bankroll fully committed; resets Monday 00:00 UTC")

        max_stake = self.config.max_position_pct * self.config.bankroll_usd
        if decision.stake_usd > max_stake:
            return RiskCheck(False, "stake exceeds max_position_pct cap")

        return RiskCheck(True, "ok")

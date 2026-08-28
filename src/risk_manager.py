import time
from dataclasses import dataclass
from typing import Optional

from src.config import Config
from src.kelly import BetDecision
from src.odds_provider import american_to_implied_prob, implied_prob_to_american
from src.state_store import StateStore


@dataclass(frozen=True)
class RiskCheck:
    approved: bool
    reason: str


class RiskManager:
    def __init__(self, config: Config, state: StateStore):
        self.config = config
        self.state = state

    def graduated_max_stake(self, price: float) -> float:
        """Interpolate the stake cap between LONGSHOT_MAX_STAKE_USD (at the
        longshot edge of the allowed odds range, MAX_AMERICAN_ODDS) and
        FAVORITE_MAX_STAKE_USD (at the favorite edge, MIN_AMERICAN_ODDS) - the
        closer to even the bet, the more it's allowed to stake. Bets outside
        the allowed range clamp to whichever edge they're nearest, but those
        get rejected by check()'s odds-range test anyway."""
        p_favorite_edge = american_to_implied_prob(self.config.min_american_odds)
        p_longshot_edge = american_to_implied_prob(self.config.max_american_odds)
        span = p_favorite_edge - p_longshot_edge
        if span <= 0:
            return self.config.favorite_max_stake_usd
        t = (price - p_longshot_edge) / span
        t = max(0.0, min(1.0, t))
        return self.config.longshot_max_stake_usd + t * (
            self.config.favorite_max_stake_usd - self.config.longshot_max_stake_usd
        )

    def check(
        self, market_id: str, decision: BetDecision, resolves_at: Optional[float] = None,
        price: Optional[float] = None,
    ) -> RiskCheck:
        if decision.side == "PASS":
            return RiskCheck(False, "no edge above min_edge threshold")

        if decision.stake_usd <= 0:
            return RiskCheck(False, "sized stake is zero or negative")

        if price is not None:
            american_odds = implied_prob_to_american(price)
            if not (self.config.min_american_odds <= american_odds <= self.config.max_american_odds):
                return RiskCheck(
                    False,
                    f"odds {american_odds:+.0f} outside configured range "
                    f"({self.config.min_american_odds:+.0f} to {self.config.max_american_odds:+.0f})",
                )

        if self.state.has_position(market_id):
            return RiskCheck(False, "already have an open position in this market")

        if self.state.open_position_count() >= self.config.max_open_positions:
            return RiskCheck(False, "max_open_positions reached")

        near_term_cutoff = time.time() + self.config.near_term_window_days * 86400
        is_long_dated = resolves_at is None or resolves_at > near_term_cutoff
        if is_long_dated and self.state.long_dated_position_count(near_term_cutoff) >= self.config.max_long_dated_positions:
            return RiskCheck(
                False,
                f"max_long_dated_positions reached - reserved for markets resolving "
                f"within {self.config.near_term_window_days:.0f} days",
            )

        weekly_spent = self.state.spent_this_week_usd()
        if weekly_spent + decision.stake_usd > self.config.bankroll_usd:
            return RiskCheck(False, "weekly bankroll fully committed; resets Monday 00:00 UTC")

        max_stake = self.config.max_position_pct * self.config.bankroll_usd
        if decision.stake_usd > max_stake:
            return RiskCheck(False, "stake exceeds max_position_pct cap")

        return RiskCheck(True, "ok")

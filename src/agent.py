import logging
import time
from typing import Optional, Tuple

from polymarket_us import PolymarketUS

from src.config import Config
from src.kelly import decide_bet
from src.odds_provider import fetch_events
from src.polymarket_client import PolymarketClient
from src.risk_manager import RiskManager
from src.signal_engine import SignalEngine
from src.sport_keys import guess_sport_key
from src.sports_markets import SportsMarket, fetch_open_sports_markets
from src.state_store import StateStore, Trade
from src.value_bet_finder import find_value_bet_signal

logger = logging.getLogger(__name__)


class TradingAgent:
    def __init__(self, config: Config):
        self.config = config
        self.state = StateStore()
        self.risk = RiskManager(config, self.state)
        self.signals = SignalEngine(api_key=config.anthropic_api_key) if config.anthropic_api_key else None
        self.polymarket = PolymarketUS(key_id=config.key_id or None, secret_key=config.secret_key or None)
        self.client = PolymarketClient(config, self.polymarket)
        self._odds_cache = {}

    def _events_for_sport(self, sport_key: str) -> list:
        if sport_key not in self._odds_cache:
            try:
                self._odds_cache[sport_key] = fetch_events(sport_key, self.config.odds_api_key)
            except Exception:
                logger.exception("Failed to fetch sportsbook odds for %s", sport_key)
                self._odds_cache[sport_key] = []
        return self._odds_cache[sport_key]

    def _estimate_probability(self, market: SportsMarket) -> Tuple[Optional[float], Optional[str]]:
        """Prefer a real edge (sportsbook consensus vs Polymarket price) over an
        LLM guess. Falls back to Claude only when no confident, well-covered
        sportsbook match exists for this market."""
        if self.config.odds_api_key:
            sport_key = guess_sport_key(f"{market.question} {market.description}")
            if sport_key:
                events = self._events_for_sport(sport_key)
                signal = find_value_bet_signal(
                    market, events, confidence_threshold=self.config.match_confidence
                )
                if signal and signal.num_bookmakers >= self.config.min_bookmakers:
                    logger.info(
                        "Sportsbook consensus for %r: %.3f (%d books, matched %s)",
                        market.question, signal.model_prob, signal.num_bookmakers, signal.yes_team,
                    )
                    return signal.model_prob, "sportsbook"

        if self.signals is not None:
            try:
                prob = self.signals.estimate_probability(
                    question=market.question,
                    description=market.description,
                    yes_price=market.yes_price,
                )
                return prob, "llm"
            except Exception:
                logger.exception("Signal generation failed for market %s", market.market_id)

        return None, None

    def run_once(self) -> None:
        markets = fetch_open_sports_markets(self.polymarket)
        logger.info("Fetched %d open sports markets", len(markets))
        self._odds_cache.clear()

        for market in markets:
            if self.state.has_position(market.market_id):
                continue

            model_prob, source = self._estimate_probability(market)
            if model_prob is None:
                continue

            decision = decide_bet(
                model_prob=model_prob,
                yes_price=market.yes_price,
                bankroll_usd=self.config.bankroll_usd,
                kelly_multiplier=self.config.kelly_multiplier,
                max_position_pct=self.config.max_position_pct,
                min_edge=self.config.min_edge,
            )

            check = self.risk.check(market.market_id, decision)
            if not check.approved:
                logger.debug("Skipping market %s: %s", market.market_id, check.reason)
                continue

            price = market.yes_price if decision.side == "YES" else 1.0 - market.yes_price

            logger.info(
                "Placing %s on market %r (signal=%s): model_prob=%.3f edge=%.3f stake=$%.2f",
                decision.side, market.question, source, model_prob, decision.edge, decision.stake_usd,
            )
            self.client.place_order(
                market_slug=market.market_id,
                side=decision.side,
                price=price,
                stake_usd=decision.stake_usd,
            )

            self.state.record_trade(
                Trade(
                    market_id=market.market_id,
                    side=decision.side,
                    price=price,
                    stake_usd=decision.stake_usd,
                    model_prob=model_prob,
                    edge=decision.edge,
                    dry_run=self.config.dry_run,
                    timestamp=time.time(),
                )
            )

    def run_loop(self, interval_seconds: int) -> None:
        logger.info("Starting agent loop, polling every %ds (dry_run=%s)",
                    interval_seconds, self.config.dry_run)
        while True:
            try:
                self.run_once()
            except Exception:
                logger.exception("Unhandled error during run_once; continuing")
            time.sleep(interval_seconds)

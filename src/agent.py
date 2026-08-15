import logging
import time

from src.config import Config
from src.kelly import decide_bet
from src.polymarket_client import PolymarketClient
from src.risk_manager import RiskManager
from src.signal_engine import SignalEngine
from src.sports_markets import fetch_open_sports_markets
from src.state_store import StateStore, Trade

logger = logging.getLogger(__name__)


class TradingAgent:
    def __init__(self, config: Config):
        self.config = config
        self.state = StateStore()
        self.risk = RiskManager(config, self.state)
        self.signals = SignalEngine(api_key=config.anthropic_api_key)
        self.client = PolymarketClient(config)

    def run_once(self) -> None:
        markets = fetch_open_sports_markets()
        logger.info("Fetched %d open sports markets", len(markets))

        for market in markets:
            if self.state.has_position(market.market_id):
                continue

            try:
                model_prob = self.signals.estimate_probability(
                    question=market.question,
                    description=market.description,
                    yes_price=market.yes_price,
                )
            except Exception:
                logger.exception("Signal generation failed for market %s", market.market_id)
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

            token_id = market.yes_token_id if decision.side == "YES" else market.no_token_id
            price = market.yes_price if decision.side == "YES" else 1.0 - market.yes_price

            logger.info(
                "Placing %s on market %r: model_prob=%.3f edge=%.3f stake=$%.2f",
                decision.side, market.question, model_prob, decision.edge, decision.stake_usd,
            )
            self.client.buy_shares(token_id=token_id, price=price, stake_usd=decision.stake_usd)

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

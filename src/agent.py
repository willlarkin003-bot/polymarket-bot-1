import logging
import time
from typing import List, Optional, Tuple

from polymarket_us import PolymarketUS

from src.config import Config
from src.kelly import decide_bet
from src.odds_provider import fetch_events
from src.polymarket_client import PolymarketClient
from src.risk_manager import RiskManager
from src.signal_engine import SignalEngine
from src.settlement import settle_trade
from src.sport_keys import guess_sport_key
from src.sports_markets import SportsMarket, fetch_open_sports_markets
from src.state_store import RoundSummary, StateStore, Trade
from src.value_bet_finder import find_value_bet_signal

logger = logging.getLogger(__name__)


class TradingAgent:
    def __init__(self, config: Config):
        self.config = config
        self.state = StateStore()
        self.risk = RiskManager(config, self.state)
        self.signals = (
            SignalEngine(api_key=config.anthropic_api_key, model=config.anthropic_model)
            if config.anthropic_api_key else None
        )
        self.polymarket = PolymarketUS(key_id=config.key_id or None, secret_key=config.secret_key or None)
        self.client = PolymarketClient(config, self.polymarket)
        self._odds_cache = {}  # sport_key -> (fetched_at, events) - persists across rounds, see _events_for_sport
        self._signal_errors = 0

    def _check_settlements(self) -> int:
        """Check every unsettled trade's market for a resolution and record its
        realized P&L. Runs regardless of DRY_RUN - a dry-run trade's stake was
        never actually risked, but checking what it *would have* earned is the
        whole point of dry-run testing. A market that hasn't resolved yet just
        raises/returns nothing useful here, so failures are silently skipped and
        retried next round rather than treated as an error."""
        settled_count = 0
        for trade in self.state.unsettled_trades():
            try:
                settlement = self.polymarket.markets.settlement(trade["market_id"])
                settlement_price = float(settlement["settlementPrice"]["value"])
            except Exception:
                continue

            result = settle_trade(
                side=trade["side"], entry_price=trade["price"],
                stake_usd=trade["stake_usd"], settlement_price=settlement_price,
            )
            self.state.mark_settled(
                trade_id=trade["id"], outcome=result.outcome,
                payout_usd=result.payout_usd, profit_usd=result.profit_usd,
                settled_at=time.time(),
            )
            settled_count += 1
            logger.info(
                "Settled %s on %r: %s, profit=$%.2f",
                trade["side"], trade["market_question"] or trade["market_id"],
                result.outcome, result.profit_usd,
            )
        return settled_count

    def _events_for_sport(self, sport_key: str) -> list:
        """Cross-round cached: The Odds API's free tier is 500 requests/month,
        and re-fetching fresh every 15-minute round burns through that in a
        couple of days. Odds don't move fast enough to need fetching more
        often than ODDS_CACHE_TTL_SECONDS (default 20 min) anyway."""
        cached = self._odds_cache.get(sport_key)
        if cached is not None:
            fetched_at, events = cached
            if time.time() - fetched_at < self.config.odds_cache_ttl_seconds:
                return events

        try:
            events = fetch_events(sport_key, self.config.odds_api_key)
        except Exception:
            logger.exception("Failed to fetch sportsbook odds for %s", sport_key)
            events = []
        self._odds_cache[sport_key] = (time.time(), events)
        return events

    def _estimate_probability(
        self, market: SportsMarket
    ) -> Tuple[Optional[float], Optional[str], List[str]]:
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
                        "Sportsbook consensus for %r: %.3f (%d books: %s, matched %s)",
                        market.question, signal.model_prob, signal.num_bookmakers,
                        ", ".join(signal.bookmakers), signal.yes_team,
                    )
                    return signal.model_prob, "sportsbook", signal.bookmakers

        if self.signals is not None:
            try:
                prob = self.signals.estimate_probability(
                    question=market.question,
                    description=market.description,
                    yes_price=market.yes_price,
                )
                return prob, "llm", []
            except Exception:
                logger.exception("Signal generation failed for market %s", market.market_id)
                self._signal_errors += 1

        return None, None, []

    def run_once(self) -> None:
        settled = self._check_settlements()
        if settled:
            logger.info("Settled %d trade(s) this round", settled)

        markets = fetch_open_sports_markets(self.polymarket, limit=self.config.market_fetch_limit)
        # Near-term markets get first claim on the weekly position budget, so
        # long-dated futures don't crowd out games resolving soon - see
        # RiskManager.check's max_long_dated_positions cap for the other half
        # of this: markets with no known resolves_at sort last (treated as
        # long-dated, same as the risk check does for an unknown date).
        markets.sort(key=lambda m: m.resolves_at if m.resolves_at is not None else float("inf"))
        logger.info("Fetched %d open sports markets", len(markets))
        self._signal_errors = 0

        already_held = 0
        no_signal = 0
        risk_rejected = 0
        placed = 0

        for market in markets:
            if self.state.has_position(market.market_id):
                already_held += 1
                continue

            model_prob, source, bookmakers = self._estimate_probability(market)
            if model_prob is None:
                no_signal += 1
                continue

            decision = decide_bet(
                model_prob=model_prob,
                yes_price=market.yes_price,
                bankroll_usd=self.config.bankroll_usd,
                kelly_multiplier=self.config.kelly_multiplier,
                max_position_pct=self.config.max_position_pct,
                min_edge=self.config.min_edge,
            )

            check = self.risk.check(market.market_id, decision, resolves_at=market.resolves_at)
            if not check.approved:
                logger.debug("Skipping market %s: %s", market.market_id, check.reason)
                risk_rejected += 1
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
                    source=source,
                    bookmakers=", ".join(bookmakers),
                    dry_run=self.config.dry_run,
                    timestamp=time.time(),
                    market_question=market.question,
                    resolves_at=market.resolves_at or 0.0,
                )
            )
            placed += 1

        logger.info(
            "Round complete: %d markets, %d already held, %d no signal (%d signal errors), "
            "%d risk-rejected, %d placed",
            len(markets), already_held, no_signal, self._signal_errors, risk_rejected, placed,
        )
        self.state.record_round(
            RoundSummary(
                markets_fetched=len(markets),
                already_held=already_held,
                no_signal=no_signal,
                signal_errors=self._signal_errors,
                risk_rejected=risk_rejected,
                placed=placed,
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

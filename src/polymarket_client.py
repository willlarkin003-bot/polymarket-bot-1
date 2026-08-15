import logging

from polymarket_us import PolymarketUS

from src.config import Config

logger = logging.getLogger(__name__)


class PolymarketClient:
    """Thin wrapper around the Polymarket US SDK's order-placement call. In dry-run
    mode, orders are logged and never submitted - no authenticated request is made.

    A market here represents a single named outcome (e.g. one team). Going "YES"
    means buying long that outcome; going "NO" means buying short it - there's no
    separate token/market for the opposing side the way the international CLOB
    works. `price` is expected to already be in the same 0-1 space for both
    directions (NO's price is `1 - yes_price`, computed by the caller), matching
    how CreateOrderParams uses a single `price` field regardless of intent.
    """

    def __init__(self, config: Config, client: PolymarketUS):
        self.config = config
        self.client = client

    def place_order(self, market_slug: str, side: str, price: float, stake_usd: float) -> dict:
        quantity = max(1, round(stake_usd / price))
        intent = "ORDER_INTENT_BUY_LONG" if side == "YES" else "ORDER_INTENT_BUY_SHORT"

        if self.config.dry_run:
            logger.info(
                "[DRY RUN] would place %s on %s: price=%.4f quantity=%d (~$%.2f)",
                intent, market_slug, price, quantity, stake_usd,
            )
            return {
                "dry_run": True,
                "marketSlug": market_slug,
                "intent": intent,
                "price": price,
                "quantity": quantity,
            }

        self.config.require_live_credentials()
        order = self.client.orders.create({
            "marketSlug": market_slug,
            "intent": intent,
            "type": "ORDER_TYPE_LIMIT",
            "price": {"value": f"{price:.2f}", "currency": "USD"},
            "quantity": quantity,
            "tif": "TIME_IN_FORCE_GOOD_TILL_CANCEL",
        })
        logger.info("Submitted live order for %s: %s", market_slug, order)
        return order

import logging

from py_clob_client.client import ClobClient
from py_clob_client.clob_types import OrderArgs
from py_clob_client.order_builder.constants import BUY

from src.config import Config

logger = logging.getLogger(__name__)


class PolymarketClient:
    """Thin wrapper around py-clob-client. In dry-run mode, orders are logged and
    never submitted - no client is even authenticated against the live API."""

    def __init__(self, config: Config):
        self.config = config
        self._client = None
        if not config.dry_run:
            config.require_live_credentials()
            self._client = ClobClient(
                host=config.clob_host,
                chain_id=config.chain_id,
                key=config.private_key,
                funder=config.funder_address,
                signature_type=1,
            )
            self._client.set_api_creds(self._client.create_or_derive_api_creds())

    def buy_shares(self, token_id: str, price: float, stake_usd: float) -> dict:
        """Buy `stake_usd` worth of shares of `token_id` at (at or better than) `price`."""
        size = round(stake_usd / price, 2)

        if self.config.dry_run or self._client is None:
            logger.info(
                "[DRY RUN] would BUY token=%s price=%.4f size=%.2f (~$%.2f)",
                token_id, price, size, stake_usd,
            )
            return {"dry_run": True, "token_id": token_id, "price": price, "size": size}

        order_args = OrderArgs(
            token_id=token_id,
            price=price,
            size=size,
            side=BUY,
        )
        signed_order = self._client.create_order(order_args)
        response = self._client.post_order(signed_order)
        logger.info("Submitted live order for token=%s: %s", token_id, response)
        return response

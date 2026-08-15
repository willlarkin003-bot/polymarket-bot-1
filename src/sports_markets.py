from dataclasses import dataclass
from typing import List, Optional

from polymarket_us import PolymarketUS


@dataclass(frozen=True)
class SportsMarket:
    market_id: str  # the market slug - used for state tracking and order placement
    question: str
    description: str
    yes_price: float  # market-implied probability of the LONG (yes) side, see _extract_yes_price
    outcome_labels: List[str]  # [team/outcome name this market's LONG side represents]


def _amount(value) -> Optional[float]:
    if not value or value.get("value") is None:
        return None
    try:
        return float(value["value"])
    except (TypeError, ValueError):
        return None


def _extract_yes_price(bbo: dict) -> Optional[float]:
    """Get a usable current-price estimate for the LONG side, even when the order
    book is thin or one-sided (common on far-out futures markets - one side of
    the book, or both, can be completely empty while the market is still active).

    Preference order: `longQuote` (Polymarket's own reference price for the long
    side, present regardless of book depth) -> midpoint of best bid/ask, when
    both actually exist -> the last traded long price, as a final fallback.

    The live `bbo` response nests all of these under a `marketData` key, unlike
    the SDK's own type hints (which claim they're top-level) - unwrap that first,
    falling back to treating `bbo` as already-flat for forward compatibility.
    """
    data = bbo.get("marketData", bbo)

    long_quote = _amount(data.get("longQuote"))
    if long_quote is not None:
        return long_quote

    best_bid = _amount(data.get("bestBid"))
    best_ask = _amount(data.get("bestAsk"))
    if best_bid is not None and best_ask is not None:
        return (best_bid + best_ask) / 2

    last_sample = data.get("lastPriceSample") or {}
    return _amount(last_sample.get("longPx"))


def fetch_open_sports_markets(client: PolymarketUS, limit: int = 50) -> List[SportsMarket]:
    """Pull active sports markets and their current price from the Polymarket US
    public market-data API. Reads (markets.list, markets.bbo) don't require
    authentication, so `client` can be a PolymarketUS instance with no
    key_id/secret_key set.

    Sorted by volume descending: the `sports` category also includes a large
    number of far-future, near-zero-liquidity futures markets (e.g. full-season
    championship futures), and default ordering surfaces those ahead of the
    actively-traded, near-term game lines this bot actually wants to trade.
    """
    response = client.markets.list({
        "categories": ["sports"],
        "active": True,
        "closed": False,
        "limit": limit,
        "orderBy": ["volume"],
        "orderDirection": "desc",
    })

    markets: List[SportsMarket] = []
    for m in response.get("markets", []):
        slug = m.get("slug")
        if not slug:
            continue

        try:
            bbo = client.markets.bbo(slug)
        except Exception:
            continue

        yes_price = _extract_yes_price(bbo)
        if yes_price is None or not 0.0 < yes_price < 1.0:
            continue

        team = m.get("team") or {}
        outcome_label = m.get("outcome") or team.get("name") or "Yes"

        markets.append(
            SportsMarket(
                market_id=slug,
                question=m.get("title", ""),
                description=m.get("description", ""),
                yes_price=yes_price,
                outcome_labels=[outcome_label],
            )
        )

    return markets

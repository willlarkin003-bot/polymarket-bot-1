from dataclasses import dataclass
from typing import List

from polymarket_us import PolymarketUS


@dataclass(frozen=True)
class SportsMarket:
    market_id: str  # the market slug - used for state tracking and order placement
    question: str
    description: str
    yes_price: float  # midpoint of best bid/ask, proxy for the market-implied probability
    outcome_labels: List[str]  # [team/outcome name this market's LONG side represents]


def fetch_open_sports_markets(client: PolymarketUS, limit: int = 50) -> List[SportsMarket]:
    """Pull active sports markets and their current best-bid/ask midpoint from the
    Polymarket US public market-data API. Reads (markets.list, markets.bbo) don't
    require authentication, so `client` can be a PolymarketUS instance with no
    key_id/secret_key set.
    """
    response = client.markets.list({
        "categories": ["sports"],
        "active": True,
        "closed": False,
        "limit": limit,
    })

    markets: List[SportsMarket] = []
    for m in response.get("markets", []):
        slug = m.get("slug")
        if not slug:
            continue

        try:
            bbo = client.markets.bbo(slug)
            best_bid = float(bbo["bestBid"]["value"])
            best_ask = float(bbo["bestAsk"]["value"])
        except (KeyError, TypeError, ValueError):
            continue

        mid_price = (best_bid + best_ask) / 2
        if not 0.0 < mid_price < 1.0:
            continue

        team = m.get("team") or {}
        outcome_label = m.get("outcome") or team.get("name") or "Yes"

        markets.append(
            SportsMarket(
                market_id=slug,
                question=m.get("title", ""),
                description=m.get("description", ""),
                yes_price=mid_price,
                outcome_labels=[outcome_label],
            )
        )

    return markets

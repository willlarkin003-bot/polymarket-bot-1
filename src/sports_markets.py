from dataclasses import dataclass
from typing import List

import requests

GAMMA_API = "https://gamma-api.polymarket.com"


@dataclass(frozen=True)
class SportsMarket:
    market_id: str  # condition_id, used as the CLOB market identifier
    yes_token_id: str
    no_token_id: str
    question: str
    description: str
    yes_price: float


def fetch_open_sports_markets(limit: int = 50) -> List[SportsMarket]:
    """Pull currently active, unresolved sports markets from Polymarket's Gamma API.

    Gamma's exact filter params have changed over time - if this stops returning
    results, check the current schema at https://docs.polymarket.com and adjust
    the params/parsing below accordingly.
    """
    resp = requests.get(
        f"{GAMMA_API}/markets",
        params={
            "active": "true",
            "closed": "false",
            "tag": "sports",
            "limit": limit,
            "order": "volume",
            "ascending": "false",
        },
        timeout=15,
    )
    resp.raise_for_status()
    raw_markets = resp.json()

    markets: List[SportsMarket] = []
    for m in raw_markets:
        try:
            token_ids = m["clobTokenIds"]
            if isinstance(token_ids, str):
                import json

                token_ids = json.loads(token_ids)
            outcome_prices = m.get("outcomePrices")
            if isinstance(outcome_prices, str):
                import json

                outcome_prices = json.loads(outcome_prices)

            markets.append(
                SportsMarket(
                    market_id=m["conditionId"],
                    yes_token_id=token_ids[0],
                    no_token_id=token_ids[1],
                    question=m.get("question", ""),
                    description=m.get("description", ""),
                    yes_price=float(outcome_prices[0]),
                )
            )
        except (KeyError, IndexError, TypeError, ValueError):
            continue

    return markets

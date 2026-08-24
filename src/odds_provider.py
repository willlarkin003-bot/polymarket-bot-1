from dataclasses import dataclass
from typing import List, Optional

import requests

ODDS_API_BASE = "https://api.the-odds-api.com/v4"


@dataclass(frozen=True)
class BookmakerLine:
    bookmaker: str
    team_price: dict  # {team_name: american_odds}


@dataclass(frozen=True)
class SportsbookEvent:
    event_id: str
    home_team: str
    away_team: str
    commence_time: str  # ISO8601
    lines: List[BookmakerLine]


def american_to_implied_prob(odds: float) -> float:
    """Convert American odds to the implied (vig-inflated) win probability."""
    if odds > 0:
        return 100.0 / (odds + 100.0)
    return -odds / (-odds + 100.0)


def devig_two_way(prob_a: float, prob_b: float) -> tuple:
    """Normalize a pair of implied probabilities that sum to >1 (due to the
    bookmaker's vig) back down to a fair pair that sums to exactly 1."""
    total = prob_a + prob_b
    if total <= 0:
        raise ValueError("implied probabilities must be positive")
    return prob_a / total, prob_b / total


def consensus_probability(event: SportsbookEvent, team: str) -> Optional[float]:
    """Average the de-vigged win probability for `team` across every bookmaker
    that quoted both sides of this event's moneyline. Returns None if no
    bookmaker quoted both sides."""
    other_team = event.away_team if team == event.home_team else event.home_team
    devigged_probs = []
    for line in event.lines:
        if team not in line.team_price or other_team not in line.team_price:
            continue
        p_team = american_to_implied_prob(line.team_price[team])
        p_other = american_to_implied_prob(line.team_price[other_team])
        fair_team, _ = devig_two_way(p_team, p_other)
        devigged_probs.append(fair_team)

    if not devigged_probs:
        return None
    return sum(devigged_probs) / len(devigged_probs)


def average_american_odds(event: SportsbookEvent, team: str) -> Optional[float]:
    """Average the raw (vig included) American odds quoted for `team`, across
    every bookmaker that quoted both sides - the actual number the books
    posted, as opposed to consensus_probability's de-vigged fair probability."""
    other_team = event.away_team if team == event.home_team else event.home_team
    prices = [
        line.team_price[team]
        for line in event.lines
        if team in line.team_price and other_team in line.team_price
    ]
    if not prices:
        return None
    return sum(prices) / len(prices)


def fetch_events(sport_key: str, api_key: str, regions: str = "us") -> List[SportsbookEvent]:
    """Pull live moneyline odds for `sport_key` from The Odds API
    (https://the-odds-api.com), across every US bookmaker it covers.

    Their schema has been stable but isn't guaranteed - if this stops parsing,
    check https://the-odds-api.com/liveapi/guides/v4/ and adjust below.
    """
    resp = requests.get(
        f"{ODDS_API_BASE}/sports/{sport_key}/odds",
        params={
            "apiKey": api_key,
            "regions": regions,
            "markets": "h2h",
            "oddsFormat": "american",
        },
        timeout=15,
    )
    resp.raise_for_status()
    raw_events = resp.json()

    events: List[SportsbookEvent] = []
    for e in raw_events:
        lines = []
        for bm in e.get("bookmakers", []):
            team_price = {}
            for market in bm.get("markets", []):
                if market.get("key") != "h2h":
                    continue
                for outcome in market.get("outcomes", []):
                    team_price[outcome["name"]] = float(outcome["price"])
            if team_price:
                lines.append(BookmakerLine(bookmaker=bm.get("key", ""), team_price=team_price))

        events.append(
            SportsbookEvent(
                event_id=e["id"],
                home_team=e["home_team"],
                away_team=e["away_team"],
                commence_time=e.get("commence_time", ""),
                lines=lines,
            )
        )

    return events

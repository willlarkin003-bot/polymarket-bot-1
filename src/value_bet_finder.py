from dataclasses import dataclass
from typing import List, Optional

from src.market_matcher import match_market
from src.odds_provider import SportsbookEvent, consensus_probability
from src.sports_markets import SportsMarket


@dataclass(frozen=True)
class ValueBetSignal:
    model_prob: float  # sportsbook-consensus win probability for the YES side
    matched_event_id: str
    yes_team: str
    num_bookmakers: int
    bookmakers: List[str]  # names of the books whose lines fed the consensus, e.g. ["draftkings", "fanduel"]


def find_value_bet_signal(
    market: SportsMarket,
    events: List[SportsbookEvent],
    confidence_threshold: float = 0.6,
) -> Optional[ValueBetSignal]:
    """Cross-reference a Polymarket sports market against live sportsbook odds
    and return a de-vigged consensus probability for its YES outcome, or None
    if no confident match / no bookmaker coverage exists."""
    matched = match_market(market, events, confidence_threshold=confidence_threshold)
    if matched is None:
        return None

    prob = consensus_probability(matched.event, matched.yes_team)
    if prob is None:
        return None

    other_team = (
        matched.event.away_team
        if matched.yes_team == matched.event.home_team
        else matched.event.home_team
    )
    contributing_books = [
        line.bookmaker
        for line in matched.event.lines
        if matched.yes_team in line.team_price and other_team in line.team_price
    ]

    return ValueBetSignal(
        model_prob=prob,
        matched_event_id=matched.event.event_id,
        yes_team=matched.yes_team,
        num_bookmakers=len(contributing_books),
        bookmakers=contributing_books,
    )

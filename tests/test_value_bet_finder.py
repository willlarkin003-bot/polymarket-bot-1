import pytest

from src.odds_provider import BookmakerLine, SportsbookEvent
from src.sports_markets import SportsMarket
from src.value_bet_finder import find_value_bet_signal


def test_finds_value_bet_signal_from_matched_event():
    market = SportsMarket(
        market_id="m1",
        question="Lakers vs Celtics", description="",
        yes_price=0.5, outcome_labels=["Los Angeles Lakers", "Boston Celtics"],
    )
    events = [
        SportsbookEvent(
            event_id="e1", home_team="Boston Celtics", away_team="Los Angeles Lakers",
            commence_time="",
            lines=[
                BookmakerLine("book_a", {"Boston Celtics": -150, "Los Angeles Lakers": 130}),
                BookmakerLine("book_b", {"Boston Celtics": -140, "Los Angeles Lakers": 120}),
            ],
        )
    ]
    signal = find_value_bet_signal(market, events)
    assert signal is not None
    assert signal.yes_team == "Los Angeles Lakers"
    assert signal.num_bookmakers == 2
    assert 0.35 < signal.model_prob < 0.45  # Lakers are the underdog in these lines
    assert signal.avg_yes_odds == pytest.approx(125)  # avg of Lakers' +130/+120
    assert signal.avg_no_odds == pytest.approx(-145)  # avg of Celtics' -150/-140


def test_returns_none_when_no_match():
    market = SportsMarket(
        market_id="m1",
        question="Will it rain tomorrow?", description="",
        yes_price=0.5, outcome_labels=["Yes", "No"],
    )
    events = [
        SportsbookEvent(event_id="e1", home_team="A", away_team="B", commence_time="", lines=[])
    ]
    assert find_value_bet_signal(market, events) is None

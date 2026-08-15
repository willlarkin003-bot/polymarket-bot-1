from src.market_matcher import match_market
from src.odds_provider import BookmakerLine, SportsbookEvent
from src.sports_markets import SportsMarket


def _market(question, outcome_labels, description=""):
    return SportsMarket(
        market_id="m1",
        question=question, description=description, yes_price=0.5,
        outcome_labels=outcome_labels,
    )


def _event(home, away):
    return SportsbookEvent(
        event_id="e1", home_team=home, away_team=away, commence_time="",
        lines=[BookmakerLine("book", {home: -120, away: 110})],
    )


def test_matches_team_named_outcome_directly():
    market = _market("Lakers vs Celtics", outcome_labels=["Los Angeles Lakers", "Boston Celtics"])
    events = [_event("Boston Celtics", "Los Angeles Lakers")]
    matched = match_market(market, events)
    assert matched is not None
    assert matched.yes_team == "Los Angeles Lakers"


def test_matches_yes_no_market_via_question_text():
    market = _market(
        "Will the Los Angeles Lakers beat the Boston Celtics on Jan 1?",
        outcome_labels=["Yes", "No"],
    )
    events = [_event("Boston Celtics", "Los Angeles Lakers")]
    matched = match_market(market, events)
    assert matched is not None
    assert matched.yes_team == "Los Angeles Lakers"


def test_returns_none_below_confidence_threshold():
    market = _market("Will it rain tomorrow?", outcome_labels=["Yes", "No"])
    events = [_event("Boston Celtics", "Los Angeles Lakers")]
    assert match_market(market, events, confidence_threshold=0.6) is None


def test_returns_none_with_no_events():
    market = _market("Lakers vs Celtics", outcome_labels=["Los Angeles Lakers", "Boston Celtics"])
    assert match_market(market, []) is None

import pytest

from src.odds_provider import (
    BookmakerLine,
    SportsbookEvent,
    american_to_implied_prob,
    average_american_odds,
    consensus_probability,
    devig_two_way,
    implied_prob_to_american,
)


def test_american_to_implied_prob_favorite():
    assert american_to_implied_prob(-150) == pytest.approx(0.6)


def test_american_to_implied_prob_underdog():
    assert american_to_implied_prob(130) == pytest.approx(100 / 230)


def test_implied_prob_to_american_favorite():
    assert implied_prob_to_american(0.6) == pytest.approx(-150)


def test_implied_prob_to_american_underdog():
    # ~14.29% implied - the +600 boundary of the "no extreme longshots" filter
    assert implied_prob_to_american(100 / 700) == pytest.approx(600)


def test_implied_prob_to_american_round_trips_with_american_to_implied_prob():
    for odds in (-300, -150, -110, 110, 150, 600, 2500):
        assert implied_prob_to_american(american_to_implied_prob(odds)) == pytest.approx(odds)


def test_implied_prob_to_american_rejects_out_of_range():
    with pytest.raises(ValueError):
        implied_prob_to_american(0.0)
    with pytest.raises(ValueError):
        implied_prob_to_american(1.0)


def test_devig_two_way_sums_to_one():
    fair_a, fair_b = devig_two_way(0.6, 100 / 230)
    assert fair_a + fair_b == pytest.approx(1.0)
    assert fair_a > fair_b


def test_devig_two_way_rejects_zero_total():
    with pytest.raises(ValueError):
        devig_two_way(0.0, 0.0)


def test_consensus_probability_averages_across_books():
    event = SportsbookEvent(
        event_id="e1", home_team="Boston Celtics", away_team="Los Angeles Lakers",
        commence_time="2026-01-01T00:00:00Z",
        lines=[
            BookmakerLine("book_a", {"Boston Celtics": -150, "Los Angeles Lakers": 130}),
            BookmakerLine("book_b", {"Boston Celtics": -140, "Los Angeles Lakers": 120}),
        ],
    )
    prob = consensus_probability(event, "Boston Celtics")
    assert 0.55 < prob < 0.62


def test_consensus_probability_ignores_incomplete_lines():
    event = SportsbookEvent(
        event_id="e1", home_team="Team A", away_team="Team B", commence_time="",
        lines=[BookmakerLine("book_a", {"Team A": -150})],  # missing Team B price
    )
    assert consensus_probability(event, "Team A") is None


def test_consensus_probability_no_lines_returns_none():
    event = SportsbookEvent(event_id="e1", home_team="A", away_team="B", commence_time="", lines=[])
    assert consensus_probability(event, "A") is None


def test_average_american_odds_averages_the_raw_price():
    event = SportsbookEvent(
        event_id="e1", home_team="Boston Celtics", away_team="Los Angeles Lakers",
        commence_time="",
        lines=[
            BookmakerLine("book_a", {"Boston Celtics": -150, "Los Angeles Lakers": 130}),
            BookmakerLine("book_b", {"Boston Celtics": -140, "Los Angeles Lakers": 120}),
        ],
    )
    assert average_american_odds(event, "Boston Celtics") == pytest.approx(-145)
    assert average_american_odds(event, "Los Angeles Lakers") == pytest.approx(125)


def test_average_american_odds_ignores_incomplete_lines():
    event = SportsbookEvent(
        event_id="e1", home_team="Team A", away_team="Team B", commence_time="",
        lines=[BookmakerLine("book_a", {"Team A": -150})],  # missing Team B price
    )
    assert average_american_odds(event, "Team A") is None


def test_average_american_odds_no_lines_returns_none():
    event = SportsbookEvent(event_id="e1", home_team="A", away_team="B", commence_time="", lines=[])
    assert average_american_odds(event, "A") is None

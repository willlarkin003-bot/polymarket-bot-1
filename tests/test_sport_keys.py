from src.sport_keys import guess_sport_key


def test_recognizes_common_leagues():
    assert guess_sport_key("Will the Lakers win the NBA game tonight?") == "basketball_nba"
    assert guess_sport_key("NFL Week 1: Chiefs vs Ravens") == "americanfootball_nfl"


def test_returns_none_for_unknown_text():
    assert guess_sport_key("Will it rain tomorrow?") is None

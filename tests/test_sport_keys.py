from src.sport_keys import guess_sport_key


def test_recognizes_common_leagues():
    assert guess_sport_key("Will the Lakers win the NBA game tonight?") == "basketball_nba"
    assert guess_sport_key("NFL Week 1: Chiefs vs Ravens") == "americanfootball_nfl"


def test_returns_none_for_unknown_text():
    assert guess_sport_key("Will it rain tomorrow?") is None


def test_recognizes_wnba_instead_of_matching_the_nba_substring():
    assert guess_sport_key("Golden State vs Portland WNBA game") == "basketball_wnba"


def test_recognizes_brasileirao():
    assert guess_sport_key("Will EC Bahia win against SC Internacional in the Brasileirao?") == "soccer_brazil_campeonato"

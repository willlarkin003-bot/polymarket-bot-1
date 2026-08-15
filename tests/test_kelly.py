import pytest

from src.kelly import decide_bet, kelly_fraction


def test_kelly_fraction_positive_edge():
    # model thinks 60% YES, market prices it at 50%
    f = kelly_fraction(model_prob=0.6, price=0.5)
    assert f == pytest.approx(0.2)


def test_kelly_fraction_no_edge():
    f = kelly_fraction(model_prob=0.5, price=0.5)
    assert f == pytest.approx(0.0)


def test_kelly_fraction_negative_edge():
    f = kelly_fraction(model_prob=0.4, price=0.5)
    assert f < 0


def test_kelly_fraction_rejects_invalid_price():
    with pytest.raises(ValueError):
        kelly_fraction(model_prob=0.5, price=1.0)
    with pytest.raises(ValueError):
        kelly_fraction(model_prob=0.5, price=0.0)


def test_decide_bet_buys_yes_on_positive_edge():
    decision = decide_bet(
        model_prob=0.65, yes_price=0.5, bankroll_usd=1000,
        kelly_multiplier=0.5, max_position_pct=0.5, min_edge=0.04,
    )
    assert decision.side == "YES"
    assert decision.edge == pytest.approx(0.15)
    # raw kelly = (0.65-0.5)/(1-0.5) = 0.3; half-kelly = 0.15 -> $150
    assert decision.stake_usd == pytest.approx(150.0)


def test_decide_bet_buys_no_on_negative_edge():
    decision = decide_bet(
        model_prob=0.2, yes_price=0.5, bankroll_usd=1000,
        kelly_multiplier=0.5, max_position_pct=0.5, min_edge=0.04,
    )
    assert decision.side == "NO"
    assert decision.stake_usd > 0


def test_decide_bet_passes_when_edge_too_small():
    decision = decide_bet(
        model_prob=0.51, yes_price=0.5, bankroll_usd=1000,
        kelly_multiplier=0.5, max_position_pct=0.5, min_edge=0.04,
    )
    assert decision.side == "PASS"
    assert decision.stake_usd == 0


def test_decide_bet_respects_max_position_pct():
    decision = decide_bet(
        model_prob=0.99, yes_price=0.5, bankroll_usd=1000,
        kelly_multiplier=1.0, max_position_pct=0.05, min_edge=0.04,
    )
    assert decision.side == "YES"
    assert decision.stake_usd == pytest.approx(50.0)

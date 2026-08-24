import pytest

from src.settlement import settle_trade


def test_yes_bet_wins():
    result = settle_trade(side="YES", entry_price=0.55, stake_usd=25.0, settlement_price=1.0)
    assert result.outcome == "WON"
    assert result.payout_usd == pytest.approx(45.45, abs=0.01)
    assert result.profit_usd == pytest.approx(20.45, abs=0.01)


def test_yes_bet_loses():
    result = settle_trade(side="YES", entry_price=0.55, stake_usd=25.0, settlement_price=0.0)
    assert result.outcome == "LOST"
    assert result.payout_usd == 0.0
    assert result.profit_usd == -25.0


def test_no_bet_wins():
    # entry_price is already the NO/short price (1 - yes_price at bet time)
    result = settle_trade(side="NO", entry_price=0.30, stake_usd=25.0, settlement_price=0.0)
    assert result.outcome == "WON"
    assert result.payout_usd == pytest.approx(83.33, abs=0.01)
    assert result.profit_usd == pytest.approx(58.33, abs=0.01)


def test_no_bet_loses():
    result = settle_trade(side="NO", entry_price=0.30, stake_usd=25.0, settlement_price=1.0)
    assert result.outcome == "LOST"
    assert result.payout_usd == 0.0
    assert result.profit_usd == -25.0


def test_push_when_payout_equals_stake():
    result = settle_trade(side="YES", entry_price=0.5, stake_usd=50.0, settlement_price=0.5)
    assert result.outcome == "PUSH"
    assert result.profit_usd == 0.0


def test_rejects_non_positive_entry_price():
    with pytest.raises(ValueError):
        settle_trade(side="YES", entry_price=0.0, stake_usd=25.0, settlement_price=1.0)

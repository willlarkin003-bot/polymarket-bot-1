from dataclasses import dataclass


@dataclass(frozen=True)
class SettlementResult:
    outcome: str  # "WON", "LOST", or "PUSH"
    payout_usd: float
    profit_usd: float


def settle_trade(side: str, entry_price: float, stake_usd: float, settlement_price: float) -> SettlementResult:
    """Compute the realized payout/profit for one trade once its market has resolved.

    `settlement_price` and `entry_price` are both in the same 0-1 long-side price
    space used everywhere else in this codebase (a NO trade's `entry_price` is
    already `1 - yes_price`, computed at bet time - see polymarket_client.py):
    1.0 means the long/YES outcome happened, 0.0 means it didn't.
    """
    if entry_price <= 0:
        raise ValueError(f"entry_price must be > 0, got {entry_price}")

    shares = stake_usd / entry_price
    won_side_price = settlement_price if side == "YES" else (1.0 - settlement_price)
    payout = shares * won_side_price
    profit = payout - stake_usd

    if abs(profit) < 1e-9:
        outcome = "PUSH"
    elif profit > 0:
        outcome = "WON"
    else:
        outcome = "LOST"

    return SettlementResult(outcome=outcome, payout_usd=round(payout, 2), profit_usd=round(profit, 2))

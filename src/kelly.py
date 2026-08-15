from dataclasses import dataclass


@dataclass(frozen=True)
class BetDecision:
    side: str  # "YES", "NO", or "PASS"
    edge: float  # model probability minus market-implied probability, on the chosen side
    raw_kelly_fraction: float  # uncapped, unscaled Kelly fraction of bankroll
    stake_fraction: float  # after Kelly multiplier + position cap
    stake_usd: float


def kelly_fraction(model_prob: float, price: float) -> float:
    """Fraction of bankroll to stake buying a YES share at `price` (payout $1),
    given the model's estimated probability of YES. Negative when there is no edge."""
    if not 0.0 < price < 1.0:
        raise ValueError(f"price must be in (0, 1), got {price}")
    return (model_prob - price) / (1.0 - price)


def decide_bet(
    model_prob: float,
    yes_price: float,
    bankroll_usd: float,
    kelly_multiplier: float,
    max_position_pct: float,
    min_edge: float,
) -> BetDecision:
    """Pick a side (YES/NO/PASS) and a Kelly-sized stake.

    `yes_price` is the current market price of a YES share (NO share is priced at
    1 - yes_price in a standard binary market).
    """
    yes_edge = model_prob - yes_price
    no_edge = (1.0 - model_prob) - (1.0 - yes_price)  # == yes_price - model_prob

    if yes_edge >= min_edge and yes_edge >= no_edge:
        side, edge, price = "YES", yes_edge, yes_price
    elif no_edge >= min_edge:
        side, edge, price = "NO", no_edge, 1.0 - yes_price
    else:
        return BetDecision(side="PASS", edge=max(yes_edge, no_edge), raw_kelly_fraction=0.0,
                            stake_fraction=0.0, stake_usd=0.0)

    prob_for_side = model_prob if side == "YES" else 1.0 - model_prob
    raw_f = kelly_fraction(prob_for_side, price)
    scaled_f = max(0.0, raw_f) * kelly_multiplier
    capped_f = min(scaled_f, max_position_pct)

    return BetDecision(
        side=side,
        edge=edge,
        raw_kelly_fraction=raw_f,
        stake_fraction=capped_f,
        stake_usd=round(capped_f * bankroll_usd, 2),
    )

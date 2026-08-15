# Polymarket Sports Trading Agent

An autonomous agent that reads live sports markets on [Polymarket](https://polymarket.com),
asks Claude for a calibrated win-probability estimate, sizes a position with the
**Kelly criterion**, and places the order through Polymarket's official CLOB SDK.

## Read this first

- **This places real trades with real money once `DRY_RUN=false`.** Prediction markets are
  speculative; you can lose your entire stake on any position. Nothing here is financial advice.
- Any specific return numbers you've seen in videos or marketing about "AI trading bots"
  (win rates, overnight profits, etc.) are **not** reproduced or guaranteed by this code.
  Past results of any strategy, on any account, do not predict future results.
- The LLM probability estimate in `src/signal_engine.py` is a starting point, not a validated
  edge. It only knows what you put in the prompt — plug in real odds/injury/lineup data sources
  before trusting it with size.
- Start in dry-run mode, on a small bankroll figure, and watch the logs before ever setting
  `DRY_RUN=false`.

## How it works

```
sports_markets.py  -> pulls open sports markets from Polymarket's Gamma API
signal_engine.py   -> asks Claude for a calibrated P(YES) given the market question
kelly.py           -> converts (model probability, market price) into a bet size
risk_manager.py    -> caps position size, open positions, and daily loss
polymarket_client.py -> signs and submits the order via py-clob-client (or logs it, in dry run)
state_store.py     -> SQLite ledger of positions/trades, so the agent never double-bets a market
agent.py           -> ties the above into a poll loop
```

## Setup

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # fill in your keys
```

Required environment variables (see `.env.example`):

| Variable | Purpose |
|---|---|
| `POLYMARKET_PRIVATE_KEY` | Private key of the wallet that funds and signs orders. **Never commit this.** |
| `POLYMARKET_FUNDER_ADDRESS` | Polymarket proxy wallet address holding your USDC. |
| `ANTHROPIC_API_KEY` | Used by `signal_engine.py` to generate probability estimates. |
| `BANKROLL_USD` | Bankroll the Kelly sizing is computed against. |
| `DRY_RUN` | `true` (default) logs intended trades without submitting orders. Set `false` to trade live. |

## Run

```bash
python main.py --once          # one pass over current sports markets, dry run by default
python main.py --interval 300  # poll every 5 minutes, forever
python main.py --live          # actually submit orders (requires DRY_RUN=false or this flag)
```

## Tests

```bash
pytest tests/
```

## Kelly sizing

For a binary market where a YES share costs `P` and pays `$1` if YES resolves true, and the
model's estimated probability of YES is `p`, the Kelly-optimal fraction of bankroll to stake is:

```
f* = (p - P) / (1 - P)         when p > P  (buy YES)
f* = (P - p) / P               when p < P  (buy NO)
```

`kelly.py` applies a configurable fractional-Kelly multiplier (half-Kelly by default) and a hard
cap (`MAX_POSITION_PCT`) on top of the raw formula, since full Kelly is high-variance and the
probability estimate itself is uncertain.

## License

MIT — see `LICENSE`.

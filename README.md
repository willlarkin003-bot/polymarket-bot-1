# Polymarket US Sports Trading Agent

An autonomous agent that reads live sports markets on [Polymarket US](https://polymarket.us)
(the CFTC-regulated US exchange, not the offshore polymarket.com site), cross-references them
against live odds from real sportsbooks to find genuine value bets, sizes a position with the
**Kelly criterion**, and places the order through Polymarket US's official Python SDK. Falls
back to a Claude probability estimate only for markets sportsbooks don't cover.

## Read this first

- **This places real trades with real money once `DRY_RUN=false`.** Prediction markets are
  speculative; you can lose your entire stake on any position. Nothing here is financial advice.
- Any specific return numbers you've seen in videos or marketing about "AI trading bots"
  (win rates, overnight profits, etc.) are **not** reproduced or guaranteed by this code.
  Past results of any strategy, on any account, do not predict future results.
- This uses Polymarket US's `key_id`/`secret_key` API credentials (Settings -> Trading API in
  the app) — not a crypto wallet private key. Lower custody risk than the offshore site, but
  still a live trading credential; treat it accordingly.
- **`polymarket_client.py`'s NO/short-side pricing is a well-reasoned inference, not a verified
  fact.** `CreateOrderParams` uses one `price` field for both `ORDER_INTENT_BUY_LONG` and
  `ORDER_INTENT_BUY_SHORT`, which strongly implies a single unified 0-1 price space (same
  convention as Kalshi) rather than the API auto-flipping the price for you — so this code
  submits `1 - yes_price` for NO bets. Verify this against a small manual order before trusting
  it with real size; if it's wrong, NO-side bets would be mis-priced.
- The sportsbook cross-referencing (see below) is a real edge signal, but the Polymarket-to-game
  matching (`src/market_matcher.py`) is best-effort text matching. Watch the logged `matched %s`
  team names for the first while and confirm they're actually right before trusting it with size.
- The Claude fallback signal (`src/signal_engine.py`) only knows what's in the prompt — it's
  meaningfully weaker than the sportsbook consensus and only used when no confident match exists.
- **If bets stop happening entirely, check the dashboard's "Signal errors" column first.** An
  invalid `ANTHROPIC_MODEL`, an expired/rate-limited `ODDS_API_KEY`, or bad Odds API credentials
  all fail *silently* into "no signal" from the outside — every market just quietly gets skipped,
  round after round, with nothing obviously wrong until you look at `agent.log` or that column.
- Start in dry-run mode, on a small bankroll figure, and watch the logs before ever setting
  `DRY_RUN=false`.

## How it works

```
sports_markets.py   -> pulls active sports markets + best-bid/ask from Polymarket US
odds_provider.py    -> pulls live moneyline odds from real sportsbooks (The Odds API)
sport_keys.py       -> guesses which sport/league a Polymarket question is about
market_matcher.py   -> matches a Polymarket market to the sportsbook game it's asking about
value_bet_finder.py -> de-vigs + averages sportsbook odds into a consensus win probability
signal_engine.py    -> Claude fallback P(YES) for markets with no confident sportsbook match
kelly.py            -> converts (model probability, market price) into a bet size
risk_manager.py     -> caps position size, open positions, and total weekly spend
polymarket_client.py -> submits the order via the polymarket-us SDK (or logs it, in dry run)
state_store.py      -> SQLite ledger of positions/trades, so the agent never double-bets a market
agent.py            -> ties the above into a poll loop
```

## Setup

Requires Python 3.10+ (the `polymarket-us` SDK's minimum).

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # fill in your keys
```

Required environment variables (see `.env.example`):

| Variable | Purpose |
|---|---|
| `POLYMARKET_KEY_ID` | Polymarket US API key ID (Settings -> Trading API). **Never commit this.** |
| `POLYMARKET_SECRET_KEY` | Polymarket US API secret key, paired with the above. **Never commit this.** |
| `ANTHROPIC_API_KEY` | Fallback probability estimate, only used when no sportsbook match exists. |
| `ANTHROPIC_MODEL` | Model ID for the fallback signal (default `claude-haiku-4-5-20251001`). Must be a real, currently-available model — an invalid one fails every call silently (see "Read this first" above). |
| `ODDS_API_KEY` | [The Odds API](https://the-odds-api.com) key. Powers the real value-bet signal — leave blank and every market falls back to the weaker Claude-only estimate. |
| `ODDS_CACHE_TTL_SECONDS` | How long to reuse fetched sportsbook odds *across scheduled runs*, not just within one (default 1200s / 20 min). Keeps you inside the Odds API free tier — see below. |
| `MIN_BOOKMAKERS` | Minimum number of books that must quote both sides of a game before its consensus is trusted (default 3). |
| `MATCH_CONFIDENCE` | Minimum text-match confidence (0–1) to link a Polymarket market to a sportsbook game (default 0.6). |
| `BANKROLL_USD` | **Weekly** budget. Kelly sizing is computed against it, and once total stakes since Monday 00:00 UTC reach this amount, the agent stops opening new positions until the next Monday, when the count resets. |
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

## Weekly bankroll reset

`BANKROLL_USD` is spent, not just referenced: `risk_manager.py` sums every trade's stake since
the most recent Monday 00:00 UTC (`state_store.spent_this_week_usd`), and rejects any new trade
that would push that total past `BANKROLL_USD`. Once the week's budget is committed, the agent
simply stops opening positions — existing open positions are untouched — until the next Monday,
when the sum naturally resets to zero. There's no separate "top up" step in code: if you're
adding fresh USDC to the wallet each week, just make sure it's there before Monday's reset.

## Value bets via sportsbook cross-referencing

For each open Polymarket sports market, `agent.py` (`_estimate_probability`) does this:

1. `sport_keys.guess_sport_key` keyword-matches the question/description to an Odds API sport
   (e.g. "NBA" -> `basketball_nba`). Unrecognized sports skip straight to the Claude fallback.
2. `odds_provider.fetch_events` pulls live moneyline odds for that sport from every US
   bookmaker The Odds API covers. Cached per sport for `ODDS_CACHE_TTL_SECONDS` (default 20
   min) - across scheduled runs, not just within one - since odds don't move fast enough to
   need fetching every 15 minutes, and the free tier's 500 requests/month doesn't survive
   fetching that often uncached (this was a real bug: earlier versions re-fetched every single
   round, which exhausts the free tier in about 2 days and then silently kills every sportsbook
   signal until the month rolls over).
3. `market_matcher.match_market` figures out which game the Polymarket question is about and
   which team's win corresponds to its YES outcome — either directly, from the market's own
   `outcome`/`team.name` field (Polymarket US markets are already per-outcome), or by
   extracting the subject team from "Will X beat Y?" phrasing as a fallback. Below
   `MATCH_CONFIDENCE`, it gives up rather than guessing.
4. `odds_provider.consensus_probability` removes each bookmaker's vig
   (`american_to_implied_prob` + `devig_two_way`) and averages the fair probability across
   every book that quoted both sides — that average is the "true" probability estimate.
5. If fewer than `MIN_BOOKMAKERS` books quoted both sides, the match is discarded (too thin to
   trust) and the market falls through to the Claude estimate instead.

The resulting probability feeds into `kelly.decide_bet` exactly like the LLM signal did before —
the difference is it's now backed by real market prices from books that have their own money on
the line, not a language model's guess. Every placed trade's log line shows which signal source
was used (`signal=sportsbook` vs `signal=llm`) so you can see how often each is firing. For
sportsbook-sourced trades, the log line and the dashboard's "Bookmakers" column also name the
specific books that fed the consensus (e.g. `draftkings, fanduel, betmgm`), so you can see exactly
whose lines the edge came from.

**What you need to turn this on:**
- An account and API key at [the-odds-api.com](https://the-odds-api.com) — the free tier is
  500 requests/month. With the default 20-minute `ODDS_CACHE_TTL_SECONDS` and a 15-minute cron,
  a sport's odds get re-fetched roughly every other round, not every round — a handful of
  active sports should comfortably fit the free tier. Lower the TTL only if you've upgraded
  the plan or you're tracking very few sports.
- `LEAGUE_TO_ODDS_SPORT_KEY` in `src/sport_keys.py` only covers the major US leagues plus a
  few others out of the box — add entries for any sport/league you trade that isn't in there,
  or it'll silently fall back to the Claude estimate for those markets.

## Dashboard

`python dashboard.py` (or double-click `open_dashboard.bat` on Windows) starts a read-only web
page at `http://localhost:8765` showing recent rounds, bet signals, and weekly bankroll usage.
It only reads `agent_state.db`, so it's safe to leave running alongside the agent.

### View from your phone (public URL)

The dashboard only binds to `127.0.0.1` — it isn't reachable from outside your PC by default.
To check it from your phone or another device, tunnel it out with [ngrok](https://ngrok.com)
(free) instead of exposing the port directly:

1. **Set a login first.** Open `.env` and set `DASHBOARD_USERNAME` and `DASHBOARD_PASSWORD` to
   values only you know — without these, anyone with the public URL could see your bot's
   activity and bankroll. Restart the dashboard after saving.
2. Sign up free at [ngrok.com](https://ngrok.com), then on the dashboard grab your authtoken
   from **Your Authtoken** and, in a terminal, run:
   ```
   ngrok config add-authtoken <your-token>
   ```
3. Download `ngrok.exe` (Windows) from [ngrok.com/download](https://ngrok.com/download) and put
   it in this same `polymarket-bot-1` folder.
4. Double-click `start_public_dashboard.bat`. It opens two windows: the dashboard, and an ngrok
   tunnel. The ngrok window prints a `Forwarding` line with a URL like
   `https://xxxx-xx-xx-xxx-xx.ngrok-free.app` — that's your public link.
5. Open that URL on your phone. It'll prompt for the username/password from step 1.

The free ngrok URL changes each time you restart the tunnel. If you want a URL that never
changes, claim a free static domain under **Domains** in your ngrok dashboard, then run
`ngrok http 8765 --domain=your-name.ngrok-free.app` instead (or edit that flag into
`start_public_dashboard.bat`).

Your bot and its data never leave your PC — ngrok just forwards traffic to the dashboard
already running locally.

## Running unattended

`python main.py --interval 900` runs forever, polling every 15 minutes — fine on a machine you
leave on. For anything that isn't always-on, run one pass at a time on a schedule instead:

```bash
python main.py --once --live
```

**Cron** (edit with `crontab -e`, runs every 15 minutes):
```
*/15 * * * * cd /path/to/polymarket-bot-1 && .venv/bin/python main.py --once --live >> agent.log 2>&1
```

**systemd timer** (`/etc/systemd/system/polymarket-agent.service` + a matching `.timer` unit, or
just `systemd-run --on-calendar='*:0/15' ...`) if you want it to survive reboots and get real
logs via `journalctl`.

Either way, `agent_state.db` (the SQLite ledger) must live on that same machine/disk across runs
— it's what makes the weekly reset and duplicate-market checks work. Don't wipe it between runs.

## License

MIT — see `LICENSE`.

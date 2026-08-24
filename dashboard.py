"""Local read-only dashboard for watching the agent while it's in dry-run testing.

Run with `python dashboard.py` from the repo root (same folder as main.py, so
it picks up the same .env and agent_state.db), then open http://localhost:8765
in a browser. Auto-refreshes every 30 seconds. Stdlib only - no extra install.
"""

import html
import http.server
import socketserver
from datetime import datetime

from src.config import Config
from src.state_store import StateStore

PORT = 8765


def _fmt_ts(ts: float) -> str:
    return datetime.fromtimestamp(ts).strftime("%m/%d %H:%M:%S")


def _esc(value) -> str:
    return html.escape(str(value))


def render_page(state: StateStore, config: Config) -> bytes:
    trades = state.recent_trades(50)
    rounds = state.recent_rounds(50)
    weekly_spent = state.spent_this_week_usd()
    weekly_pct = min(100.0, (weekly_spent / config.bankroll_usd) * 100) if config.bankroll_usd else 0.0
    mode = "LIVE TRADING" if not config.dry_run else "DRY RUN (testing)"
    mode_color = "#e5484d" if not config.dry_run else "#3fb950"
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    rounds_rows = "".join(
        f"<tr><td>{_fmt_ts(r['timestamp'])}</td><td>{r['markets_fetched']}</td>"
        f"<td>{r['already_held']}</td><td>{r['no_signal']}</td>"
        f"<td>{'<b style=\"color:#e5484d\">' + str(r['signal_errors']) + '</b>' if r.get('signal_errors') else r.get('signal_errors', 0)}</td>"
        f"<td>{r['risk_rejected']}</td><td><b>{r['placed']}</b></td></tr>"
        for r in rounds
    ) or "<tr><td colspan='7' class='empty'>No rounds recorded yet - wait for the next scheduled run.</td></tr>"

    trades_rows = "".join(
        f"<tr><td>{_fmt_ts(t['timestamp'])}</td><td>{_esc(t['market_id'])}</td>"
        f"<td>{_esc(t['side'])}</td><td>${t['price']:.2f}</td><td>${t['stake_usd']:.2f}</td>"
        f"<td>{t['model_prob']:.2f}</td><td>{t['edge']:.2f}</td>"
        f"<td>{_esc(t['source'] or '?')}</td>"
        f"<td>{_esc(t['bookmakers']) if t.get('bookmakers') else '-'}</td>"
        f"<td>{'LIVE' if not t['dry_run'] else 'dry-run'}</td></tr>"
        for t in trades
    ) or "<tr><td colspan='10' class='empty'>No bet signals logged yet.</td></tr>"

    page = f"""<!doctype html>
<html>
<head>
<meta http-equiv="refresh" content="30">
<meta charset="utf-8">
<title>Polymarket Bot Dashboard</title>
<style>
  body {{ font-family: -apple-system, Segoe UI, Arial, sans-serif; background: #0f1117; color: #e6e6e6; margin: 0; padding: 24px 32px; }}
  h1 {{ font-size: 20px; margin: 0 0 4px; }}
  .sub {{ color: #9aa0a6; font-size: 13px; margin-bottom: 24px; }}
  .badge {{ display: inline-block; padding: 3px 10px; border-radius: 999px; font-size: 12px; font-weight: 600; color: #0f1117; background: {mode_color}; margin-left: 10px; vertical-align: middle; }}
  .cards {{ display: flex; gap: 16px; margin-bottom: 32px; flex-wrap: wrap; }}
  .card {{ background: #1a1d27; border: 1px solid #2a2e3a; border-radius: 8px; padding: 16px 20px; min-width: 170px; }}
  .card .label {{ font-size: 11px; color: #9aa0a6; text-transform: uppercase; letter-spacing: .05em; }}
  .card .value {{ font-size: 24px; font-weight: 600; margin-top: 4px; }}
  table {{ width: 100%; border-collapse: collapse; margin-bottom: 32px; font-size: 13px; }}
  th, td {{ text-align: left; padding: 8px 10px; border-bottom: 1px solid #2a2e3a; }}
  th {{ color: #9aa0a6; font-weight: 500; text-transform: uppercase; font-size: 11px; }}
  h2 {{ font-size: 15px; margin-bottom: 12px; color: #cfd3da; }}
  .bar-bg {{ background: #2a2e3a; border-radius: 6px; height: 8px; width: 100%; overflow: hidden; margin-top: 10px; }}
  .bar-fill {{ background: #4f8ef7; height: 100%; }}
  .empty {{ color: #6b7280; font-style: italic; }}
</style>
</head>
<body>
  <h1>Polymarket Sports Trading Agent<span class="badge">{mode}</span></h1>
  <div class="sub">Auto-refreshes every 30s &middot; Last loaded {now}</div>

  <div class="cards">
    <div class="card"><div class="label">Rounds logged</div><div class="value">{len(rounds)}</div></div>
    <div class="card"><div class="label">Bet signals logged</div><div class="value">{len(trades)}</div></div>
    <div class="card" style="min-width:220px">
      <div class="label">Weekly bankroll used</div>
      <div class="value">${weekly_spent:.2f} / ${config.bankroll_usd:.0f}</div>
      <div class="bar-bg"><div class="bar-fill" style="width:{weekly_pct:.0f}%"></div></div>
    </div>
  </div>

  <h2>Recent rounds (every scheduled run, whether or not it bet)</h2>
  <table>
    <tr><th>Time</th><th>Fetched</th><th>Already held</th><th>No signal</th><th>Signal errors</th><th>Risk-rejected</th><th>Placed</th></tr>
    {rounds_rows}
  </table>

  <h2>Recent bet signals</h2>
  <table>
    <tr><th>Time</th><th>Market</th><th>Side</th><th>Price</th><th>Stake</th><th>Model P</th><th>Edge</th><th>Signal</th><th>Bookmakers</th><th>Mode</th></tr>
    {trades_rows}
  </table>
</body>
</html>"""
    return page.encode("utf-8")


def main() -> None:
    config = Config.load()
    state = StateStore()

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(render_page(state, config))

        def log_message(self, format: str, *args) -> None:
            pass  # keep the console quiet

    try:
        httpd = socketserver.TCPServer(("127.0.0.1", PORT), Handler)
    except OSError:
        print(f"Port {PORT} is already in use - the dashboard is probably already running.")
        print(f"Just open http://localhost:{PORT} in your browser.")
        return

    with httpd:
        print(f"Dashboard running at http://localhost:{PORT}  (Ctrl+C to stop)")
        httpd.serve_forever()


if __name__ == "__main__":
    main()

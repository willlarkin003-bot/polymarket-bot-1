import argparse
import logging
from dataclasses import replace

from src.agent import TradingAgent
from src.config import Config


def main() -> None:
    parser = argparse.ArgumentParser(description="Polymarket sports trading agent")
    parser.add_argument("--once", action="store_true", help="Run a single pass and exit")
    parser.add_argument("--interval", type=int, default=300,
                         help="Seconds between polls when looping (default 300)")
    parser.add_argument("--live", action="store_true",
                         help="Force live trading regardless of DRY_RUN env var")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    config = Config.load()
    if args.live:
        config = replace(config, dry_run=False)

    agent = TradingAgent(config)

    if args.once:
        agent.run_once()
    else:
        agent.run_loop(args.interval)


if __name__ == "__main__":
    main()

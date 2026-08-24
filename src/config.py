import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


def _bool_env(name: str, default: bool) -> bool:
    val = os.getenv(name)
    if val is None:
        return default
    return val.strip().lower() in ("1", "true", "yes", "on")


def _float_env(name: str, default: float) -> float:
    val = os.getenv(name)
    return float(val) if val else default


def _int_env(name: str, default: int) -> int:
    val = os.getenv(name)
    return int(val) if val else default


@dataclass(frozen=True)
class Config:
    key_id: str
    secret_key: str
    anthropic_api_key: str
    anthropic_model: str
    odds_api_key: str
    odds_cache_ttl_seconds: int
    bankroll_usd: float
    kelly_multiplier: float
    max_position_pct: float
    max_open_positions: int
    min_edge: float
    min_bookmakers: int
    match_confidence: float
    dry_run: bool
    dashboard_username: str = ""
    dashboard_password: str = ""
    near_term_window_days: float = 9.0
    max_long_dated_positions: int = 5
    market_fetch_limit: int = 150

    @staticmethod
    def load() -> "Config":
        return Config(
            key_id=os.getenv("POLYMARKET_KEY_ID", ""),
            secret_key=os.getenv("POLYMARKET_SECRET_KEY", ""),
            anthropic_api_key=os.getenv("ANTHROPIC_API_KEY", ""),
            anthropic_model=os.getenv("ANTHROPIC_MODEL", "claude-haiku-4-5-20251001"),
            odds_api_key=os.getenv("ODDS_API_KEY", ""),
            odds_cache_ttl_seconds=_int_env("ODDS_CACHE_TTL_SECONDS", 1200),
            bankroll_usd=_float_env("BANKROLL_USD", 1000.0),
            kelly_multiplier=_float_env("KELLY_MULTIPLIER", 0.5),
            max_position_pct=_float_env("MAX_POSITION_PCT", 0.05),
            max_open_positions=_int_env("MAX_OPEN_POSITIONS", 25),
            min_edge=_float_env("MIN_EDGE", 0.025),
            min_bookmakers=_int_env("MIN_BOOKMAKERS", 3),
            match_confidence=_float_env("MATCH_CONFIDENCE", 0.6),
            dry_run=_bool_env("DRY_RUN", True),
            dashboard_username=os.getenv("DASHBOARD_USERNAME", ""),
            dashboard_password=os.getenv("DASHBOARD_PASSWORD", ""),
            near_term_window_days=_float_env("NEAR_TERM_WINDOW_DAYS", 9.0),
            max_long_dated_positions=_int_env("MAX_LONG_DATED_POSITIONS", 5),
            market_fetch_limit=_int_env("MARKET_FETCH_LIMIT", 150),
        )

    def require_live_credentials(self) -> None:
        missing = [
            name
            for name, val in (
                ("POLYMARKET_KEY_ID", self.key_id),
                ("POLYMARKET_SECRET_KEY", self.secret_key),
            )
            if not val
        ]
        if missing:
            raise RuntimeError(
                f"Missing required env vars for live trading: {', '.join(missing)}"
            )

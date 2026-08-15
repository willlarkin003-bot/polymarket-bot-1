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
    odds_api_key: str
    bankroll_usd: float
    kelly_multiplier: float
    max_position_pct: float
    max_open_positions: int
    min_edge: float
    min_bookmakers: int
    match_confidence: float
    dry_run: bool

    @staticmethod
    def load() -> "Config":
        return Config(
            key_id=os.getenv("POLYMARKET_KEY_ID", ""),
            secret_key=os.getenv("POLYMARKET_SECRET_KEY", ""),
            anthropic_api_key=os.getenv("ANTHROPIC_API_KEY", ""),
            odds_api_key=os.getenv("ODDS_API_KEY", ""),
            bankroll_usd=_float_env("BANKROLL_USD", 1000.0),
            kelly_multiplier=_float_env("KELLY_MULTIPLIER", 0.5),
            max_position_pct=_float_env("MAX_POSITION_PCT", 0.05),
            max_open_positions=_int_env("MAX_OPEN_POSITIONS", 10),
            min_edge=_float_env("MIN_EDGE", 0.04),
            min_bookmakers=_int_env("MIN_BOOKMAKERS", 3),
            match_confidence=_float_env("MATCH_CONFIDENCE", 0.6),
            dry_run=_bool_env("DRY_RUN", True),
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

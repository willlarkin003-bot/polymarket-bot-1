from typing import Optional

LEAGUE_TO_ODDS_SPORT_KEY = {
    "nfl": "americanfootball_nfl",
    "college football": "americanfootball_ncaaf",
    "ncaaf": "americanfootball_ncaaf",
    "nba": "basketball_nba",
    "college basketball": "basketball_ncaab",
    "ncaab": "basketball_ncaab",
    "mlb": "baseball_mlb",
    "nhl": "icehockey_nhl",
    "premier league": "soccer_epl",
    "epl": "soccer_epl",
    "champions league": "soccer_uefa_champs_league",
    "mls": "soccer_usa_mls",
    "ufc": "mma_mixed_martial_arts",
    "atp": "tennis_atp",
    "wta": "tennis_wta",
}


def guess_sport_key(text: str) -> Optional[str]:
    """Best-effort mapping from free text (market question/description) to an
    Odds API sport key. Polymarket doesn't expose a clean league field to key
    off, so this just keyword-searches - extend LEAGUE_TO_ODDS_SPORT_KEY as you
    hit sports/leagues it doesn't recognize."""
    lowered = text.lower()
    for keyword, sport_key in LEAGUE_TO_ODDS_SPORT_KEY.items():
        if keyword in lowered:
            return sport_key
    return None

import difflib
import re
from dataclasses import dataclass
from typing import List, Optional

from src.odds_provider import SportsbookEvent
from src.sports_markets import SportsMarket

_SUBJECT_PATTERN = re.compile(
    r"will\s+(?:the\s+)?(.+?)\s+(?:beat|defeat|win\s+(?:against|over)|win\b)",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class MatchedMarket:
    market: SportsMarket
    event: SportsbookEvent
    yes_team: str  # the team whose win == this market's YES outcome resolving true


def _extract_subject_team(question: str) -> Optional[str]:
    """For phrasing like 'Will the Lakers beat the Celtics?', pull out the team
    the question is actually asking about ('Lakers'), not just any team name
    mentioned in the sentence."""
    match = _SUBJECT_PATTERN.search(question)
    return match.group(1).strip() if match else None


def _match_score(text: str, team: str) -> float:
    text_l, team_l = text.lower(), team.lower()
    if team_l in text_l:
        return 1.0
    return difflib.SequenceMatcher(None, text_l, team_l).ratio()


def match_market(
    market: SportsMarket,
    events: List[SportsbookEvent],
    confidence_threshold: float = 0.6,
) -> Optional[MatchedMarket]:
    """Find the sportsbook event a Polymarket sports market is about, and which
    team's win corresponds to that market resolving YES.

    Two cases: markets whose first outcome IS a team name (Gamma's `outcomes`
    field) are matched directly - high confidence. Yes/No-phrased markets
    ("Will the Lakers beat the Celtics?") have the subject team extracted from
    the question text instead - lower confidence, since it depends on the
    question's exact phrasing. This is best-effort text matching; verify
    matches manually before trusting it with live size on an unfamiliar sport.
    """
    yes_label = market.outcome_labels[0] if market.outcome_labels else ""
    if yes_label.strip().lower() in ("yes", "no", ""):
        candidate_text = _extract_subject_team(market.question) or market.question
    else:
        candidate_text = yes_label

    best_event, best_team, best_score = None, None, 0.0
    for event in events:
        for team in (event.home_team, event.away_team):
            score = _match_score(candidate_text, team)
            if score > best_score:
                best_event, best_team, best_score = event, team, score

    if best_event is None or best_score < confidence_threshold:
        return None

    return MatchedMarket(market=market, event=best_event, yes_team=best_team)

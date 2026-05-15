"""Signal rules. Each rule looks at a fixture + its recent snapshots and
returns a Signal if conditions are met, else None.

Add new rules here. The poller iterates all RULES on every live fixture.
"""
from dataclasses import dataclass
from typing import Optional


@dataclass
class Signal:
    rule_name: str
    market: str            # 'goals', 'corners', etc.
    suggested_bet: str     # human-readable
    confidence: int        # 1..5
    criteria: dict         # snapshot of what triggered it


def _safe_int(v) -> int:
    try:
        return int(v) if v is not None else 0
    except (ValueError, TypeError):
        return 0


def _sum_stat(stats_by_team: dict, key: str) -> int:
    """Sum a stat across both teams."""
    total = 0
    for team_stats in stats_by_team.values():
        total += _safe_int(team_stats.get(key))
    return total


# ---- Rule 1: shots burst — late-game pressure with no recent goal ----

def shots_burst(fixture: dict, current_stats: dict, history: list[dict]) -> Optional[Signal]:
    """3+ shots on goal in the last ~10 min, score still ripe for a goal."""
    minute = fixture.get("fixture", {}).get("status", {}).get("elapsed") or 0
    if minute < 25 or minute > 85:
        return None

    home_goals = fixture.get("goals", {}).get("home") or 0
    away_goals = fixture.get("goals", {}).get("away") or 0

    older = [h for h in history if h.get("minute") and minute - h["minute"] >= 8]
    if not older:
        return None
    base = older[0]
    base_stats = base.get("stats") or {}

    current_shots = _sum_stat(current_stats, "Shots on Goal")
    base_shots = _sum_stat(base_stats, "Shots on Goal")
    shots_delta = current_shots - base_shots

    if base["home_score"] != home_goals or base["away_score"] != away_goals:
        return None

    if shots_delta >= 3:
        return Signal(
            rule_name="shots_burst",
            market="goals",
            suggested_bet="Next goal within ~10 min · Over current line",
            confidence=min(5, 2 + shots_delta // 2),
            criteria={
                "minute": minute,
                "shots_delta": shots_delta,
                "score": f"{home_goals}-{away_goals}",
                "window_min": minute - base["minute"],
            },
        )
    return None


# ---- Rule 2: corner spam — corners pile up ----

def corner_spam(fixture: dict, current_stats: dict, history: list[dict]) -> Optional[Signal]:
    minute = fixture.get("fixture", {}).get("status", {}).get("elapsed") or 0
    if minute < 30 or minute > 85:
        return None

    older = [h for h in history if h.get("minute") and minute - h["minute"] >= 8]
    if not older:
        return None
    base = older[0]
    base_stats = base.get("stats") or {}

    current_corners = _sum_stat(current_stats, "Corner Kicks")
    base_corners = _sum_stat(base_stats, "Corner Kicks")
    delta = current_corners - base_corners

    if delta >= 4:
        return Signal(
            rule_name="corner_spam",
            market="corners",
            suggested_bet="Next corner within ~5 min · Over current line",
            confidence=min(5, 2 + delta // 2),
            criteria={
                "minute": minute,
                "corners_delta": delta,
                "window_min": minute - base["minute"],
            },
        )
    return None


# ---- Rule 3: late-game push for a trailing team ----

def late_push(fixture: dict, current_stats: dict, history: list[dict]) -> Optional[Signal]:
    minute = fixture.get("fixture", {}).get("status", {}).get("elapsed") or 0
    if minute < 75 or minute > 88:
        return None

    home_goals = fixture.get("goals", {}).get("home") or 0
    away_goals = fixture.get("goals", {}).get("away") or 0
    if home_goals == away_goals:
        return None

    teams = fixture.get("teams", {})
    home_id = teams.get("home", {}).get("id")
    away_id = teams.get("away", {}).get("id")
    trailing_id = home_id if home_goals < away_goals else away_id

    trailing_stats = current_stats.get(trailing_id, {})
    dangerous = _safe_int(trailing_stats.get("Dangerous Attacks"))
    possession = _safe_int(trailing_stats.get("Ball Possession"))

    if dangerous >= 40 and possession >= 55:
        return Signal(
            rule_name="late_push",
            market="goals",
            suggested_bet="Trailing team to score next · BTTS yes",
            confidence=3,
            criteria={
                "minute": minute,
                "trailing_team": trailing_id,
                "dangerous_attacks": dangerous,
                "possession": possession,
            },
        )
    return None


# Master list — poller iterates this
RULES = [shots_burst, corner_spam, late_push]

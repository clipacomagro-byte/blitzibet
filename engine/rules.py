"""Signal rules. Three risk profiles + watch tier.

  - risk='safe'   → high probability play (4-5 confidence)
  - risk='medium' → balanced momentum (3 confidence)
  - risk='risky'  → speculative, high reward (2 confidence)

Tier ('signal' vs 'watch') is orthogonal to risk:
  - tier='signal' → bet recommendation
  - tier='watch'  → heads-up only
"""
from dataclasses import dataclass
from typing import Optional


@dataclass
class Signal:
    rule_name: str
    market: str
    suggested_bet: str
    confidence: int
    criteria: dict
    tier: str = "signal"
    risk: str = "medium"


def _safe_int(v):
    try:
        return int(v) if v is not None else 0
    except (ValueError, TypeError):
        return 0


def _sum_stat(stats_by_team, key):
    total = 0
    for team_stats in stats_by_team.values():
        total += _safe_int(team_stats.get(key))
    return total


def _team_stat(stats_by_team, team_id, key):
    return _safe_int((stats_by_team.get(team_id) or {}).get(key))


# =============================================================
# SAFE RULES — high probability, fewer triggers
# =============================================================

def dominance_btts(fixture, current_stats, history):
    """Both teams creating chances, no BTTS yet -> BTTS yes by FT."""
    minute = fixture.get("fixture", {}).get("status", {}).get("elapsed") or 0
    if minute < 50 or minute > 80:
        return None

    home_goals = fixture.get("goals", {}).get("home") or 0
    away_goals = fixture.get("goals", {}).get("away") or 0
    if home_goals > 0 and away_goals > 0:
        return None  # BTTS already hit

    teams = fixture.get("teams", {})
    home_id = teams.get("home", {}).get("id")
    away_id = teams.get("away", {}).get("id")

    home_attacks = _team_stat(current_stats, home_id, "Dangerous Attacks")
    away_attacks = _team_stat(current_stats, away_id, "Dangerous Attacks")

    if home_attacks >= 30 and away_attacks >= 30:
        return Signal(
            rule_name="dominance_btts",
            market="btts",
            suggested_bet="BTTS yes by full time",
            confidence=4,
            tier="signal",
            risk="safe",
            criteria={
                "minute": minute,
                "home_attacks": home_attacks,
                "away_attacks": away_attacks,
            },
        )
    return None


def over_volume(fixture, current_stats, history):
    """High total shot volume already -> over X.5 final shots."""
    minute = fixture.get("fixture", {}).get("status", {}).get("elapsed") or 0
    if minute < 55 or minute > 75:
        return None

    total_shots = _sum_stat(current_stats, "Total Shots")
    if total_shots >= 14:
        line = total_shots + 6
        return Signal(
            rule_name="over_volume",
            market="shots",
            suggested_bet=f"Over {line}.5 total shots by FT",
            confidence=4,
            tier="signal",
            risk="safe",
            criteria={"minute": minute, "total_shots": total_shots},
        )
    return None


# =============================================================
# MEDIUM RULES — momentum-based, balanced
# =============================================================

def shots_burst(fixture, current_stats, history):
    """Shots-on-goal surge.
    3+ delta = SAFE, 2 = MEDIUM, 1 = WATCH."""
    minute = fixture.get("fixture", {}).get("status", {}).get("elapsed") or 0
    if minute < 25 or minute > 85:
        return None

    home_goals = fixture.get("goals", {}).get("home") or 0
    away_goals = fixture.get("goals", {}).get("away") or 0

    older = [
        h for h in history
        if h.get("minute") and minute - h["minute"] >= 7
    ]
    if not older:
        return None
    base = older[0]
    base_stats = base.get("stats") or {}

    if base.get("home_score") != home_goals or base.get("away_score") != away_goals:
        return None

    current_shots = _sum_stat(current_stats, "Shots on Goal")
    base_shots = _sum_stat(base_stats, "Shots on Goal")
    delta = current_shots - base_shots

    if delta >= 3:
        return Signal(
            rule_name="shots_burst_safe",
            market="goals",
            suggested_bet="Next goal within ~10 min · Over current line",
            confidence=4,
            tier="signal",
            risk="safe",
            criteria={"minute": minute, "shots_delta": delta},
        )
    if delta == 2:
        return Signal(
            rule_name="shots_burst",
            market="goals",
            suggested_bet="Next goal within ~10 min",
            confidence=3,
            tier="signal",
            risk="medium",
            criteria={"minute": minute, "shots_delta": delta},
        )
    if delta == 1:
        return Signal(
            rule_name="shots_burst_watch",
            market="goals",
            suggested_bet="Watch tier - momentum building",
            confidence=2,
            tier="watch",
            risk="medium",
            criteria={"minute": minute, "shots_delta": delta},
        )
    return None


def corner_spam(fixture, current_stats, history):
    """Corner surge.
    4+ delta = SAFE, 3 = MEDIUM, 2 = WATCH."""
    minute = fixture.get("fixture", {}).get("status", {}).get("elapsed") or 0
    if minute < 25 or minute > 85:
        return None

    older = [
        h for h in history
        if h.get("minute") and minute - h["minute"] >= 7
    ]
    if not older:
        return None
    base = older[0]
    base_stats = base.get("stats") or {}

    current_corners = _sum_stat(current_stats, "Corner Kicks")
    base_corners = _sum_stat(base_stats, "Corner Kicks")
    delta = current_corners - base_corners

    if delta >= 4:
        return Signal(
            rule_name="corner_spam_safe",
            market="corners",
            suggested_bet="Next corner within ~5 min · Over current line",
            confidence=4,
            tier="signal",
            risk="safe",
            criteria={"minute": minute, "corners_delta": delta},
        )
    if delta == 3:
        return Signal(
            rule_name="corner_spam",
            market="corners",
            suggested_bet="Next corner within ~5 min",
            confidence=3,
            tier="signal",
            risk="medium",
            criteria={"minute": minute, "corners_delta": delta},
        )
    if delta == 2:
        return Signal(
            rule_name="corner_spam_watch",
            market="corners",
            suggested_bet="Watch tier - corners building",
            confidence=2,
            tier="watch",
            risk="medium",
            criteria={"minute": minute, "corners_delta": delta},
        )
    return None


def attack_surge(fixture, current_stats, history):
    """Dangerous attacks spike — pre-shot momentum signal."""
    minute = fixture.get("fixture", {}).get("status", {}).get("elapsed") or 0
    if minute < 25 or minute > 85:
        return None

    older = [
        h for h in history
        if h.get("minute") and minute - h["minute"] >= 7
    ]
    if not older:
        return None
    base = older[0]
    base_stats = base.get("stats") or {}

    current_attacks = _sum_stat(current_stats, "Dangerous Attacks")
    base_attacks = _sum_stat(base_stats, "Dangerous Attacks")
    delta = current_attacks - base_attacks

    if delta >= 18:
        return Signal(
            rule_name="attack_surge",
            market="goals",
            suggested_bet="Next goal within ~10 min",
            confidence=3,
            tier="signal",
            risk="medium",
            criteria={"minute": minute, "attacks_delta": delta},
        )
    if delta >= 12:
        return Signal(
            rule_name="attack_surge_watch",
            market="goals",
            suggested_bet="Watch tier - pressure building",
            confidence=2,
            tier="watch",
            risk="medium",
            criteria={"minute": minute, "attacks_delta": delta},
        )
    return None


# =============================================================
# RISKY RULES — speculative, higher reward
# =============================================================

def late_push(fixture, current_stats, history):
    """Trailing team pressing late."""
    minute = fixture.get("fixture", {}).get("status", {}).get("elapsed") or 0
    if minute < 70 or minute > 88:
        return None

    home_goals = fixture.get("goals", {}).get("home") or 0
    away_goals = fixture.get("goals", {}).get("away") or 0
    if home_goals == away_goals:
        return None

    teams = fixture.get("teams", {})
    home_id = teams.get("home", {}).get("id")
    away_id = teams.get("away", {}).get("id")
    trailing_id = home_id if home_goals < away_goals else away_id

    trail_attacks = _team_stat(current_stats, trailing_id, "Dangerous Attacks")
    trail_poss = _team_stat(current_stats, trailing_id, "Ball Possession")

    if trail_attacks >= 35 and trail_poss >= 55:
        return Signal(
            rule_name="late_push",
            market="goals",
            suggested_bet="Trailing team to score - BTTS yes",
            confidence=3,
            tier="signal",
            risk="risky",
            criteria={
                "minute": minute,
                "trail_attacks": trail_attacks,
                "trail_poss": trail_poss,
            },
        )
    if trail_attacks >= 25 and trail_poss >= 52:
        return Signal(
            rule_name="late_push_watch",
            market="goals",
            suggested_bet="Watch tier - trailing team applying pressure",
            confidence=2,
            tier="watch",
            risk="risky",
            criteria={
                "minute": minute,
                "trail_attacks": trail_attacks,
                "trail_poss": trail_poss,
            },
        )
    return None


def htft_swing(fixture, current_stats, history):
    """Score level but one team clearly dominant -> that team wins FT."""
    minute = fixture.get("fixture", {}).get("status", {}).get("elapsed") or 0
    if minute < 60 or minute > 78:
        return None

    home_goals = fixture.get("goals", {}).get("home") or 0
    away_goals = fixture.get("goals", {}).get("away") or 0
    if home_goals != away_goals:
        return None

    teams = fixture.get("teams", {})
    home_id = teams.get("home", {}).get("id")
    away_id = teams.get("away", {}).get("id")

    home_attacks = _team_stat(current_stats, home_id, "Dangerous Attacks")
    away_attacks = _team_stat(current_stats, away_id, "Dangerous Attacks")
    home_poss = _team_stat(current_stats, home_id, "Ball Possession")
    away_poss = _team_stat(current_stats, away_id, "Ball Possession")

    if home_attacks == 0 or away_attacks == 0:
        return None

    if home_attacks >= away_attacks * 1.8 and home_poss >= 58:
        return Signal(
            rule_name="htft_swing_home",
            market="htft",
            suggested_bet="Draw HT / Home win FT",
            confidence=2,
            tier="signal",
            risk="risky",
            criteria={
                "minute": minute,
                "home_attacks": home_attacks,
                "away_attacks": away_attacks,
            },
        )
    if away_attacks >= home_attacks * 1.8 and away_poss >= 58:
        return Signal(
            rule_name="htft_swing_away",
            market="htft",
            suggested_bet="Draw HT / Away win FT",
            confidence=2,
            tier="signal",
            risk="risky",
            criteria={
                "minute": minute,
                "home_attacks": home_attacks,
                "away_attacks": away_attacks,
            },
        )
    return None


RULES = [
    # SAFE
    dominance_btts,
    over_volume,
    # MEDIUM
    shots_burst,
    corner_spam,
    attack_surge,
    # RISKY
    late_push,
    htft_swing,
]

"""Signal rules — three risk profiles + instant moment detection.
  - risk='safe'   -> high probability play (confidence 4-5)
  - risk='medium' -> balanced momentum (confidence 3)
  - risk='risky'  -> speculative, high reward (confidence 2)
  - risk='urgent' -> instant moment (goal scored, big chance, big save)
"""
from dataclasses import dataclass


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
# URGENT — instant moment detection (goal, big chance, big save)
# =============================================================

def goal_alert(fixture, current_stats, history):
    """Goal just scored - fire instant alert with new score context."""
    minute = fixture.get("fixture", {}).get("status", {}).get("elapsed") or 0
    if not history:
        return None
    base = history[0]
    home_goals = fixture.get("goals", {}).get("home") or 0
    away_goals = fixture.get("goals", {}).get("away") or 0
    base_home = base.get("home_score") or 0
    base_away = base.get("away_score") or 0
    if home_goals + away_goals <= base_home + base_away:
        return None  # no new goal
    teams = fixture.get("teams", {})
    home_name = teams.get("home", {}).get("name", "Home")
    away_name = teams.get("away", {}).get("name", "Away")
    scorer = home_name if home_goals > base_home else away_name
    return Signal(
        rule_name="goal_alert",
        market="goals",
        suggested_bet=(
            f"GOAL: {scorer} scores at {minute}' - "
            f"{home_goals}-{away_goals}. Re-evaluate next-goal markets."
        ),
        confidence=5,
        tier="signal",
        risk="urgent",
        criteria={
            "minute": minute,
            "new_score": f"{home_goals}-{away_goals}",
            "scorer_side": "home" if home_goals > base_home else "away",
        },
    )


def big_chance(fixture, current_stats, history):
    """Keeper saves spiking - chances mounting, goal imminent."""
    minute = fixture.get("fixture", {}).get("status", {}).get("elapsed") or 0
    if minute < 10 or minute > 85:
        return None
    older = [h for h in history if h.get("minute") and minute - h["minute"] >= 4]
    if not older:
        return None
    base = older[0]
    base_stats = base.get("stats") or {}
    current_saves = _sum_stat(current_stats, "Goalkeeper Saves")
    base_saves = _sum_stat(base_stats, "Goalkeeper Saves")
    delta = current_saves - base_saves
    if delta >= 2:
        home_goals = fixture.get("goals", {}).get("home") or 0
        away_goals = fixture.get("goals", {}).get("away") or 0
        return Signal(
            rule_name="big_chance",
            market="goals",
            suggested_bet="Major chances created - next goal / over current line",
            confidence=4,
            tier="signal",
            risk="urgent",
            criteria={
                "minute": minute,
                "saves_delta": delta,
                "score": f"{home_goals}-{away_goals}",
            },
        )
    return None


# =============================================================
# SAFE — high probability plays
# =============================================================

def dominance_btts(fixture, current_stats, history):
    """Both teams creating, no BTTS yet -> BTTS yes by FT."""
    minute = fixture.get("fixture", {}).get("status", {}).get("elapsed") or 0
    if minute < 50 or minute > 80:
        return None
    home_goals = fixture.get("goals", {}).get("home") or 0
    away_goals = fixture.get("goals", {}).get("away") or 0
    if home_goals > 0 and away_goals > 0:
        return None
    teams = fixture.get("teams", {})
    home_id = teams.get("home", {}).get("id")
    away_id = teams.get("away", {}).get("id")
    home_a = _team_stat(current_stats, home_id, "Dangerous Attacks")
    away_a = _team_stat(current_stats, away_id, "Dangerous Attacks")
    if home_a >= 30 and away_a >= 30:
        return Signal(
            rule_name="dominance_btts", market="btts",
            suggested_bet="BTTS yes by full time",
            confidence=4, tier="signal", risk="safe",
            criteria={"minute": minute, "home_attacks": home_a, "away_attacks": away_a},
        )
    return None


def over_volume(fixture, current_stats, history):
    """High shot volume -> over X.5 total shots by FT."""
    minute = fixture.get("fixture", {}).get("status", {}).get("elapsed") or 0
    if minute < 55 or minute > 75:
        return None
    total_shots = _sum_stat(current_stats, "Total Shots")
    if total_shots >= 14:
        line = total_shots + 6
        return Signal(
            rule_name="over_volume", market="shots",
            suggested_bet=f"Over {line}.5 total shots by FT",
            confidence=4, tier="signal", risk="safe",
            criteria={"minute": minute, "total_shots": total_shots},
        )
    return None


# =============================================================
# MEDIUM / RISKY — momentum-based
# =============================================================

def shots_burst(fixture, current_stats, history):
    """Shots-on-goal surge. 3+ = SAFE, 2 = MEDIUM."""
    minute = fixture.get("fixture", {}).get("status", {}).get("elapsed") or 0
    if minute < 25 or minute > 85:
        return None
    home_goals = fixture.get("goals", {}).get("home") or 0
    away_goals = fixture.get("goals", {}).get("away") or 0
    older = [h for h in history if h.get("minute") and minute - h["minute"] >= 7]
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
            rule_name="shots_burst_safe", market="goals",
            suggested_bet="Next goal within ~10 min - Over current line",
            confidence=4, tier="signal", risk="safe",
            criteria={"minute": minute, "shots_delta": delta},
        )
    if delta == 2:
        return Signal(
            rule_name="shots_burst", market="goals",
            suggested_bet="Next goal within ~10 min",
            confidence=3, tier="signal", risk="medium",
            criteria={"minute": minute, "shots_delta": delta},
        )
    return None


def corner_spam(fixture, current_stats, history):
    """Corner surge. 4+ = SAFE, 3 = MEDIUM."""
    minute = fixture.get("fixture", {}).get("status", {}).get("elapsed") or 0
    if minute < 25 or minute > 85:
        return None
    older = [h for h in history if h.get("minute") and minute - h["minute"] >= 7]
    if not older:
        return None
    base = older[0]
    base_stats = base.get("stats") or {}
    current_c = _sum_stat(current_stats, "Corner Kicks")
    base_c = _sum_stat(base_stats, "Corner Kicks")
    delta = current_c - base_c
    if delta >= 4:
        return Signal(
            rule_name="corner_spam_safe", market="corners",
            suggested_bet="Next corner within ~5 min - Over current line",
            confidence=4, tier="signal", risk="safe",
            criteria={"minute": minute, "corners_delta": delta},
        )
    if delta == 3:
        return Signal(
            rule_name="corner_spam", market="corners",
            suggested_bet="Next corner within ~5 min",
            confidence=3, tier="signal", risk="medium",
            criteria={"minute": minute, "corners_delta": delta},
        )
    return None


def attack_surge(fixture, current_stats, history):
    """Dangerous attacks spike."""
    minute = fixture.get("fixture", {}).get("status", {}).get("elapsed") or 0
    if minute < 25 or minute > 85:
        return None
    older = [h for h in history if h.get("minute") and minute - h["minute"] >= 7]
    if not older:
        return None
    base = older[0]
    base_stats = base.get("stats") or {}
    current_a = _sum_stat(current_stats, "Dangerous Attacks")
    base_a = _sum_stat(base_stats, "Dangerous Attacks")
    delta = current_a - base_a
    if delta >= 18:
        return Signal(
            rule_name="attack_surge", market="goals",
            suggested_bet="Next goal within ~10 min",
            confidence=3, tier="signal", risk="medium",
            criteria={"minute": minute, "attacks_delta": delta},
        )
    return None


def late_push(fixture, current_stats, history):
    """Trailing team pressing in final 20 min."""
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
    trail_a = _team_stat(current_stats, trailing_id, "Dangerous Attacks")
    trail_p = _team_stat(current_stats, trailing_id, "Ball Possession")
    if trail_a >= 35 and trail_p >= 55:
        return Signal(
            rule_name="late_push", market="goals",
            suggested_bet="Trailing team to score - BTTS yes",
            confidence=3, tier="signal", risk="risky",
            criteria={"minute": minute, "trail_attacks": trail_a, "trail_poss": trail_p},
        )
    return None


def htft_swing(fixture, current_stats, history):
    """Score level but one team dominant -> that team wins FT."""
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
    home_a = _team_stat(current_stats, home_id, "Dangerous Attacks")
    away_a = _team_stat(current_stats, away_id, "Dangerous Attacks")
    home_p = _team_stat(current_stats, home_id, "Ball Possession")
    away_p = _team_stat(current_stats, away_id, "Ball Possession")
    if home_a == 0 or away_a == 0:
        return None
    if home_a >= away_a * 1.8 and home_p >= 58:
        return Signal(
            rule_name="htft_swing_home", market="htft",
            suggested_bet="Draw HT / Home win FT",
            confidence=2, tier="signal", risk="risky",
            criteria={"minute": minute, "home_attacks": home_a, "away_attacks": away_a},
        )
    if away_a >= home_a * 1.8 and away_p >= 58:
        return Signal(
            rule_name="htft_swing_away", market="htft",
            suggested_bet="Draw HT / Away win FT",
            confidence=2, tier="signal", risk="risky",
            criteria={"minute": minute, "home_attacks": home_a, "away_attacks": away_a},
        )
    return None


RULES = [
    # URGENT (instant moment detection)
    goal_alert,
    big_chance,
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

"""Signal rules — three risk profiles + instant moment detection."""
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
# URGENT — instant match-changers
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
        return None
    teams = fixture.get("teams", {})
    home_name = teams.get("home", {}).get("name", "Home")
    away_name = teams.get("away", {}).get("name", "Away")
    scorer = home_name if home_goals > base_home else away_name
    return Signal(
        rule_name="goal_alert", market="goals",
        suggested_bet=(
            f"GOAL: {scorer} scores at {minute}' - "
            f"{home_goals}-{away_goals}. Re-evaluate next-goal markets."
        ),
        confidence=5, tier="signal", risk="urgent",
        criteria={"minute": minute, "new_score": f"{home_goals}-{away_goals}"},
    )


def red_card_pressure(fixture, current_stats, history):
    """Red card after 60' - 10 v 11 changes everything."""
    minute = fixture.get("fixture", {}).get("status", {}).get("elapsed") or 0
    if minute < 60 or minute > 92:
        return None
    older = [h for h in history if h.get("minute") and minute - h["minute"] >= 3]
    if not older:
        return None
    base = older[0]
    base_stats = base.get("stats") or {}
    current_reds = _sum_stat(current_stats, "Red Cards")
    base_reds = _sum_stat(base_stats, "Red Cards")
    if current_reds <= base_reds:
        return None
    teams = fixture.get("teams", {})
    home_id = teams.get("home", {}).get("id")
    away_id = teams.get("away", {}).get("id")
    home_name = teams.get("home", {}).get("name", "Home")
    away_name = teams.get("away", {}).get("name", "Away")
    home_red_now = _team_stat(current_stats, home_id, "Red Cards")
    home_red_base = _team_stat(base_stats, home_id, "Red Cards")
    red_side = "home" if home_red_now > home_red_base else "away"
    advantaged = away_name if red_side == "home" else home_name
    home_goals = fixture.get("goals", {}).get("home") or 0
    away_goals = fixture.get("goals", {}).get("away") or 0
    return Signal(
        rule_name="red_card_late", market="goals",
        suggested_bet=(
            f"Red card at {minute}' - {advantaged} has man advantage. "
            f"Over current goal line, {advantaged} to score next."
        ),
        confidence=4, tier="signal", risk="urgent",
        criteria={
            "minute": minute, "red_side": red_side,
            "score": f"{home_goals}-{away_goals}",
        },
    )


def rapid_goals(fixture, current_stats, history):
    """Two goals in under 5 min - match exploding, over markets in play."""
    minute = fixture.get("fixture", {}).get("status", {}).get("elapsed") or 0
    if not history or minute < 5:
        return None
    home_goals = fixture.get("goals", {}).get("home") or 0
    away_goals = fixture.get("goals", {}).get("away") or 0
    current_total = home_goals + away_goals
    older = [h for h in history if h.get("minute") and minute - h["minute"] >= 5]
    if not older:
        return None
    base = older[0]
    base_total = (base.get("home_score") or 0) + (base.get("away_score") or 0)
    if current_total - base_total >= 2:
        return Signal(
            rule_name="rapid_goals", market="goals",
            suggested_bet=(
                f"2 goals in last 5 min - match wide open. "
                f"Over current line, another goal in 10."
            ),
            confidence=4, tier="signal", risk="urgent",
            criteria={"minute": minute, "goals_delta": current_total - base_total},
        )
    return None


def late_equalizer(fixture, current_stats, history):
    """Equalizer scored after 75' - momentum massively swings."""
    minute = fixture.get("fixture", {}).get("status", {}).get("elapsed") or 0
    if minute < 75 or minute > 92:
        return None
    home_goals = fixture.get("goals", {}).get("home") or 0
    away_goals = fixture.get("goals", {}).get("away") or 0
    if home_goals != away_goals or home_goals == 0:
        return None
    older = [h for h in history if h.get("minute") and minute - h["minute"] >= 3]
    if not older:
        return None
    base = older[0]
    base_h = base.get("home_score") or 0
    base_a = base.get("away_score") or 0
    if base_h == base_a:
        return None
    # was unequal, now equal -> equalizer
    return Signal(
        rule_name="late_equalizer", market="goals",
        suggested_bet=(
            f"Late equalizer at {minute}' - "
            f"momentum swing. Next goal markets live."
        ),
        confidence=4, tier="signal", risk="urgent",
        criteria={"minute": minute, "equalized_score": f"{home_goals}-{away_goals}"},
    )


def card_storm(fixture, current_stats, history):
    """2+ yellow cards in under 5 min - heated match, more cards likely."""
    minute = fixture.get("fixture", {}).get("status", {}).get("elapsed") or 0
    if minute < 20 or minute > 88:
        return None
    older = [h for h in history if h.get("minute") and minute - h["minute"] >= 5]
    if not older:
        return None
    base = older[0]
    base_stats = base.get("stats") or {}
    current_yellows = _sum_stat(current_stats, "Yellow Cards")
    base_yellows = _sum_stat(base_stats, "Yellow Cards")
    if current_yellows - base_yellows >= 2:
        return Signal(
            rule_name="card_storm", market="cards",
            suggested_bet=(
                f"{current_yellows - base_yellows} yellows in 5 min - "
                f"over 4.5 cards in play, more incoming."
            ),
            confidence=3, tier="signal", risk="medium",
            criteria={"minute": minute, "yellow_delta": current_yellows - base_yellows},
        )
    return None


# =============================================================
# SAFE
# =============================================================

def dominance_btts(fixture, current_stats, history):
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
# MEDIUM / RISKY
# =============================================================

def shots_burst(fixture, current_stats, history):
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
    # URGENT - match-changers
    goal_alert,
    red_card_pressure,
    rapid_goals,
    late_equalizer,
    # MEDIUM event
    card_storm,
    # SAFE
    dominance_btts,
    over_volume,
    # MOMENTUM
    shots_burst,
    corner_spam,
    attack_surge,
    # RISKY
    late_push,
    htft_swing,
]

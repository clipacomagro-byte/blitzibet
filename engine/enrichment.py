"""Signal enrichment. When a rule fires:
  1. Pull extra context (H2H history)
  2. Build a structured context dict
  3. Call Claude to write the narrative
"""
import logging

from data import api_football as api
from data import claude_client

log = logging.getLogger("blitzibet.enrichment")


async def build_narrative(fixture: dict, current_stats: dict,
                          history: list[dict], signal) -> str | None:
    teams = fixture.get("teams", {})
    home_id = teams.get("home", {}).get("id")
    away_id = teams.get("away", {}).get("id")
    home_name = teams.get("home", {}).get("name", "Home")
    away_name = teams.get("away", {}).get("name", "Away")
    minute = fixture.get("fixture", {}).get("status", {}).get("elapsed") or 0
    home_goals = fixture.get("goals", {}).get("home") or 0
    away_goals = fixture.get("goals", {}).get("away") or 0
    league = fixture.get("league", {}).get("name", "")

    live_lines = []
    for team_id, stats in current_stats.items():
        name = home_name if team_id == home_id else (away_name if team_id == away_id else f"team#{team_id}")
        bits = []
        if "Shots on Goal" in stats:
            bits.append(f"shots on goal {stats['Shots on Goal']}")
        if "Total Shots" in stats:
            bits.append(f"total shots {stats['Total Shots']}")
        if "Corner Kicks" in stats:
            bits.append(f"corners {stats['Corner Kicks']}")
        if "Dangerous Attacks" in stats:
            bits.append(f"dangerous attacks {stats['Dangerous Attacks']}")
        if "Ball Possession" in stats:
            bits.append(f"possession {stats['Ball Possession']}%")
        if bits:
            live_lines.append(f"  {name}: " + ", ".join(bits))
    live_stats_text = "\n".join(live_lines) if live_lines else "no stats available"

    crit = signal.criteria or {}
    delta_lines = []
    if "shots_delta" in crit:
        delta_lines.append(f"  shots on goal: +{crit['shots_delta']} in last {crit.get('window_min', 10)} min")
    if "corners_delta" in crit:
        delta_lines.append(f"  corners: +{crit['corners_delta']} in last {crit.get('window_min', 10)} min")
    if "dangerous_attacks" in crit:
        delta_lines.append(f"  trailing team dangerous attacks: {crit['dangerous_attacks']}")
    if "possession" in crit:
        delta_lines.append(f"  trailing team possession: {crit['possession']}%")
    delta_text = "\n".join(delta_lines) if delta_lines else "no delta data"

    h2h_text = "no recent meetings on file"
    try:
        if home_id and away_id:
            h2h = await api.head_to_head(home_id, away_id, last_n=5)
            if h2h:
                h2h_text = _summarise_h2h(h2h)
    except Exception as e:
        log.warning("H2H fetch failed: %s", e)

    context = {
        "fixture_label": f"{home_name} vs {away_name}",
        "home_goals": home_goals,
        "away_goals": away_goals,
        "minute": minute,
        "league": league,
        "rule_name": signal.rule_name,
        "live_stats_text": live_stats_text,
        "delta_text": delta_text,
        "h2h_text": h2h_text,
    }

    tier = getattr(signal, "tier", "signal")
    return await claude_client.write_signal_narrative(context, tier=tier)


def _summarise_h2h(h2h: list[dict]) -> str:
    lines = []
    goals_total = 0
    games_counted = 0
    for m in h2h[:5]:
        h_score, a_score = 0, 0
        for s in m.get("scores") or []:
            if s.get("description") != "CURRENT":
                continue
            score_obj = s.get("score") or {}
            side = score_obj.get("participant")
            goals = score_obj.get("goals") or 0
            if side == "home":
                h_score = goals
            elif side == "away":
                a_score = goals
        total = h_score + a_score
        goals_total += total
        games_counted += 1
        date = (m.get("starting_at") or "")[:10]
        lines.append(f"  {date}: {h_score}-{a_score} ({total} goals)")
    avg = (goals_total / games_counted) if games_counted else 0
    header = f"Last {games_counted} meetings, avg {avg:.1f} goals/match:"
    return header + "\n" + "\n".join(lines)

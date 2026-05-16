"""SportMonks football data client (Growth plan and up).
Reshapes SportMonks v3 responses to match the shape the rest of the engine uses.
"""
import logging
import httpx
from config import API_FOOTBALL_KEY

log = logging.getLogger(__name__)

BASE_URL = "https://api.sportmonks.com/v3/football"

STAT_TYPE_MAP = {
    86: "Shots on Goal",
    41: "Total Shots",
    34: "Corner Kicks",
    44: "Dangerous Attacks",
    43: "Attacks",
    45: "Ball Possession",
    49: "Shots off Goal",
    51: "Offsides",
    56: "Fouls",
    57: "Goalkeeper Saves",
    58: "Throw Ins",
    60: "Yellow Cards",
    64: "Red Cards",
}

_stats_cache = {}


class APIFootballError(Exception):
    pass


def _params(extra=None):
    p = {"api_token": API_FOOTBALL_KEY}
    if extra:
        p.update(extra)
    return p


async def probe():
    async with httpx.AsyncClient(timeout=15) as client:
        r = await client.get(
            f"{BASE_URL}/livescores/inplay",
            params=_params({"per_page": 1}),
        )
        r.raise_for_status()
        data = r.json()
    if "subscription" in data:
        return {"response": {"subscription": data["subscription"]}}
    return {"response": {"ok": True}}


async def live_fixtures(league_ids=None):
    params = _params({
        "include": "participants;statistics;scores;periods;state;league",
    })
    if league_ids:
        ids = ",".join(str(i) for i in league_ids)
        params["filters"] = f"fixtureLeagues:{ids}"

    async with httpx.AsyncClient(timeout=20) as client:
        r = await client.get(f"{BASE_URL}/livescores/inplay", params=params)
        r.raise_for_status()
        data = r.json()

    # SportMonks returns {"message": "...", "subscription": [...]} when
    # there are no matching live games. Treat as empty, don't crash.
    if "data" not in data:
        log.info(
            "No live fixtures: %s",
            data.get("message", "no data key in response"),
        )
        return []

    if not data["data"]:
        return []

    fixtures = []
    for fx in data["data"]:
        reshaped, cached_stats = _reshape_fixture(fx)
        fixtures.append(reshaped)
        fid = reshaped["fixture"]["id"]
        if fid is not None:
            _stats_cache[fid] = cached_stats
    return fixtures


def _reshape_fixture(fx):
    participants = fx.get("participants") or []
    home = {}
    away = {}
    for p in participants:
        loc = (p.get("meta") or {}).get("location")
        if loc == "home":
            home = p
        elif loc == "away":
            away = p

    home_score, away_score = 0, 0
    for s in fx.get("scores") or []:
        if s.get("description") != "CURRENT":
            continue
        score_obj = s.get("score") or {}
        side = score_obj.get("participant")
        goals = score_obj.get("goals") or 0
        if side == "home":
            home_score = goals
        elif side == "away":
            away_score = goals

    minute = 0
    for p in fx.get("periods") or []:
        if p.get("ticking"):
            minute = p.get("minutes") or 0
            break

    by_team = {}
    for stat in fx.get("statistics") or []:
        team_id = stat.get("participant_id")
        type_id = stat.get("type_id")
        if team_id is None or type_id not in STAT_TYPE_MAP:
            continue
        raw = stat.get("data")
        value = raw.get("value") if isinstance(raw, dict) else None
        if value is None:
            continue
        by_team.setdefault(team_id, []).append({
            "type": STAT_TYPE_MAP[type_id],
            "value": value,
        })

    stats_list = []
    for tid, s in by_team.items():
        stats_list.append({"team": {"id": tid}, "statistics": s})

    league = fx.get("league") or {}
    fixture_dict = {
        "fixture": {
            "id": fx.get("id"),
            "status": {"elapsed": minute},
        },
        "teams": {
            "home": {
                "id": home.get("id"),
                "name": home.get("name", "Home"),
            },
            "away": {
                "id": away.get("id"),
                "name": away.get("name", "Away"),
            },
        },
        "league": {"name": league.get("name", "")},
        "goals": {"home": home_score, "away": away_score},
    }
    return fixture_dict, stats_list


async def fixture_statistics(fixture_id):
    cached = _stats_cache.get(fixture_id)
    if cached is not None:
        return cached

    params = _params({"include": "statistics;participants"})
    async with httpx.AsyncClient(timeout=15) as client:
        r = await client.get(
            f"{BASE_URL}/fixtures/{fixture_id}",
            params=params,
        )
        r.raise_for_status()
        data = r.json()
    fx = data.get("data") or {}
    if not fx:
        return []

    by_team = {}
    for stat in fx.get("statistics") or []:
        team_id = stat.get("participant_id")
        type_id = stat.get("type_id")
        if team_id is None or type_id not in STAT_TYPE_MAP:
            continue
        raw = stat.get("data")
        value = raw.get("value") if isinstance(raw, dict) else None
        if value is None:
            continue
        by_team.setdefault(team_id, []).append({
            "type": STAT_TYPE_MAP[type_id],
            "value": value,
        })

    out = []
    for tid, s in by_team.items():
        out.append({"team": {"id": tid}, "statistics": s})
    return out


async def head_to_head(team1_id, team2_id, last_n=5):
    """Returns normalized list of last N meetings.
    Each item: {date, home_score, away_score, total_goals}."""
    params = _params({"include": "participants;scores"})
    url = f"{BASE_URL}/fixtures/head-to-head/{team1_id}/{team2_id}"
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.get(url, params=params)
            r.raise_for_status()
            data = r.json()
    except Exception as e:
        log.warning("H2H request failed: %s", e)
        return []

    fixtures = data.get("data") or []
    out = []
    for fx in fixtures[:last_n]:
        h_score, a_score = 0, 0
        for s in fx.get("scores") or []:
            if s.get("description") != "CURRENT":
                continue
            score_obj = s.get("score") or {}
            side = score_obj.get("participant")
            goals = score_obj.get("goals") or 0
            if side == "home":
                h_score = goals
            elif side == "away":
                a_score = goals
        date = (fx.get("starting_at") or "")[:10]
        out.append({
            "date": date,
            "home_score": h_score,
            "away_score": a_score,
            "total_goals": h_score + a_score,
        })
    return out


async def fixture_events(fixture_id):
    params = _params({"include": "events"})
    async with httpx.AsyncClient(timeout=15) as client:
        r = await client.get(
            f"{BASE_URL}/fixtures/{fixture_id}",
            params=params,
        )
        r.raise_for_status()
        data = r.json()
    fx = data.get("data") or {}
    events = fx.get("events") or []
    out = []
    for ev in events:
        is_goal = ev.get("type_id") == 14
        type_name = "Goal"
        if not is_goal:
            type_name = (ev.get("type") or {}).get("name") or "Other"
        out.append({
            "type": type_name,
            "time": {"elapsed": ev.get("minute") or 0},
        })
    return out


def stats_to_dict(stats_response):
    out = {}
    for team_block in stats_response:
        team_id = (team_block.get("team") or {}).get("id")
        if team_id is None:
            continue
        out[team_id] = {}
        for entry in team_block.get("statistics") or []:
            stat_type = entry.get("type")
            val = entry.get("value")
            if isinstance(val, str) and val.endswith("%"):
                try:
                    val = int(val.rstrip("%"))
                except ValueError:
                    pass
            if val is None:
                val = 0
            out[team_id][stat_type] = val
    return out

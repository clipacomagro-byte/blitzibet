"""SportMonks football data client.

Same function signatures as the original API-Football client — rest of the
engine doesn't need to change.

Docs: https://docs.sportmonks.com/v3/
"""
import logging
import httpx
from config import API_FOOTBALL_KEY  # repurposed: now holds the SportMonks token

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

_stats_cache: dict[int, list] = {}


class APIFootballError(Exception):
    pass


def _params(extra: dict | None = None) -> dict:
    p = {"api_token": API_FOOTBALL_KEY}
    if extra:
        p.update(extra)
    return p


async def probe() -> dict:
    async with httpx.AsyncClient(timeout=15) as client:
        r = await client.get(
            f"{BASE_URL}/livescores/inplay",
            params=_params({"per_page": 1}),
        )
        r.raise_for_status()
        data = r.json()
    if "subscription" in data:
        return {"response": {"subscription": data["subscription"]}}
    return {"response": {"ok": True, "rate_limit": data.get("rate_limit")}}


async def live_fixtures(league_ids: list[int] | None = None) -> list[dict]:
    params = _params({
        "include": "participants;statistics;scores;periods;state;league",
    })
    if league_ids:
        params["filters"] = f"fixtureLeagues:{','.join(str(i) for i in league_ids)}"

    async with httpx.AsyncClient(timeout=20) as client:
        r = await client.get(f"{BASE_URL}/livescores/inplay", params=params)
        r.raise_for_status()
        data = r.json()

    if "data" not in data:
        raise APIFootballError(str(data))

    fixtures = []
    for fx in data["data"]:
        reshaped, cached_stats = _reshape_fixture(fx)
        fixtures.append(reshaped)
        if reshaped["fixture"]["id"] is not None:
            _stats_cache[reshaped["fixture"]["id"]] = cached_stats
    return fixtures


def _reshape_fixture(fx: dict) -> tuple[dict, list]:
    participants = fx.get("participants") or []
    home = next(
        (p for p in participants if (p.get("meta") or {}).get("location") == "home"),
        {},
    )
    away = next(
        (p for p in participants if (p.get("meta") or {}).get("location") == "away"),
        {},
    )

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

    by_team: dict[int, list] = {}
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

    stats_list = [
        {"team": {"id": tid}, "statistics": s} for tid, s in by_team.items()
    ]

    league = fx.get("league") or {}
    fixture_dict = {
        "fixture": {
            "id": fx.get("id"),
            "status": {"elapsed": minute},
        },
        "teams": {
            "home": {"id": home.get("id"), "name": home.get("name", "Home")},
            "away": {"id": away.get("id"), "name": away.get("name", "Away")},
        },
        "league": {"name": league.get("name", "")},
        "goals": {"home": home_score, "away": away_score},
    }
    return fixture_dict, stats_list


async def fixture_statistics(fixture_id: int) -> list[dict]:
    cached = _stats_cache.get(fixture_id)
    if cached is not None:
        return cached

    params = _params({"include": "statistics;participants"})
    async with httpx.AsyncClient(timeout=15) as client:
        r = await client.get(f"{BASE_URL}/fixtures/{fixture_id}", params=params)
        r.raise_for_status()
        data = r.json()
    fx = data.get("data") or {}
    if not fx:
        raise APIFootballError(f"No fixture {fixture_id}")

    by_team: dict[int, list] = {}
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
    return [{"team": {"id": tid}, "statistics": s} for tid, s in by_team.items()]


async def head_to_head(team1_id: int, team2_id: int, last_n: int = 5) -> list[dict]:
    """Last N head-to-head fixtures between two teams. Returns [] on error."""
    params = _params({"include": "participants;scores"})
    url = f"{BASE_URL}/fixtures/head-to-head/{team1_id}/{team2_id}"
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.get(url, params=params)
            r.raise_for_status()
            data = r.json()
    except Exception as e:
        log.warning("H2H request failed for %s vs %s: %s", team1_id, team2_id, e)
        return []
    fixtures = data.get("data") or []
    return fixtures[:last_n]


async def fixture_events(fixture_id: int) -> list[dict]:
    params = _params({"include": "events"})
    async with httpx.AsyncClient(timeout=15) as client:
        r = await client.get(f"{BASE_URL}/fixtures/{fixture_id}", params=params)
        r.raise_for_status()
        data = r.json()
    fx = data.get("data") or {}
    events = fx.get("events") or []
    out = []
    for ev in events:
        is_goal = ev.get("type_id") == 14
        out.append({
            "type": "Goal" if is_goal else ((ev.get("type") or {}).get("name") or "Other"),
            "time": {"elapsed": ev.get("minute") or 0},
        })
    return out


def stats_to_dict(stats_response: list[dict]) -> dict[int, dict]:
    out: dict[int, dict] = {}
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
            out[team_id][stat_type] = val if val is not None else 0
    return out

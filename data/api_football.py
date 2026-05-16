"""API-Football client (api-sports.io direct, free tier).
Sign up at https://api-football.com — uses x-apisports-key header.
"""
import logging
import httpx
from config import API_FOOTBALL_KEY

log = logging.getLogger(__name__)

BASE_URL = "https://v3.football.api-sports.io"


class APIFootballError(Exception):
    pass


def _headers() -> dict[str, str]:
    return {"x-apisports-key": API_FOOTBALL_KEY}


async def probe() -> dict:
    async with httpx.AsyncClient(timeout=15) as client:
        r = await client.get(f"{BASE_URL}/status", headers=_headers())
        r.raise_for_status()
        return r.json()


async def live_fixtures(league_ids: list[int] | None = None) -> list[dict]:
    """All currently live football fixtures."""
    params: dict = {"live": "all"}
    if league_ids:
        params["league"] = "-".join(str(i) for i in league_ids)
    async with httpx.AsyncClient(timeout=15) as client:
        r = await client.get(f"{BASE_URL}/fixtures", headers=_headers(), params=params)
        r.raise_for_status()
        data = r.json()
    if data.get("errors"):
        # Empty errors dict means no error
        errs = data["errors"]
        if isinstance(errs, dict) and not errs:
            pass
        elif isinstance(errs, list) and not errs:
            pass
        else:
            log.warning("API-Football returned errors: %s", errs)
            return []
    return data.get("response", []) or []


async def fixture_statistics(fixture_id: int) -> list[dict]:
    async with httpx.AsyncClient(timeout=15) as client:
        r = await client.get(
            f"{BASE_URL}/fixtures/statistics",
            headers=_headers(),
            params={"fixture": fixture_id},
        )
        r.raise_for_status()
        data = r.json()
    return data.get("response", []) or []


async def head_to_head(team1_id: int, team2_id: int, last_n: int = 5) -> list[dict]:
    """Returns normalized list: [{date, home_score, away_score, total_goals}].
    Empty list on any failure — degrades gracefully."""
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.get(
                f"{BASE_URL}/fixtures/headtohead",
                headers=_headers(),
                params={"h2h": f"{team1_id}-{team2_id}", "last": last_n},
            )
            r.raise_for_status()
            data = r.json()
    except Exception as e:
        log.warning("H2H request failed for %s vs %s: %s", team1_id, team2_id, e)
        return []
    out = []
    for fx in data.get("response", []) or []:
        goals = fx.get("goals") or {}
        h_score = goals.get("home") or 0
        a_score = goals.get("away") or 0
        date = (fx.get("fixture") or {}).get("date", "")[:10]
        out.append({
            "date": date,
            "home_score": h_score,
            "away_score": a_score,
            "total_goals": h_score + a_score,
        })
    return out


async def fixture_events(fixture_id: int) -> list[dict]:
    async with httpx.AsyncClient(timeout=15) as client:
        r = await client.get(
            f"{BASE_URL}/fixtures/events",
            headers=_headers(),
            params={"fixture": fixture_id},
        )
        r.raise_for_status()
        data = r.json()
    return data.get("response", []) or []


def stats_to_dict(stats_response: list[dict]) -> dict[int, dict]:
    """Flatten API-Football's [{team, statistics:[{type,value}]}] to {team_id: {type: value}}."""
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

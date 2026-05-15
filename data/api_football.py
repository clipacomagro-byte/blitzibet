"""API-Football client. Free tier: 100 req/day. Pro: $19/mo for 75k/day.

Docs: https://www.api-football.com/documentation-v3
"""
import logging
import httpx
from config import API_FOOTBALL_KEY, API_FOOTBALL_HOST

log = logging.getLogger(__name__)

BASE_URL = f"https://{API_FOOTBALL_HOST}"


class APIFootballError(Exception):
    pass


def _headers() -> dict[str, str]:
    return {
        "x-rapidapi-key": API_FOOTBALL_KEY,
        "x-rapidapi-host": API_FOOTBALL_HOST,
    }


async def probe() -> dict:
    """Sanity check the API key and reach. Returns the /status payload."""
    async with httpx.AsyncClient(timeout=15) as client:
        r = await client.get(f"{BASE_URL}/status", headers=_headers())
        r.raise_for_status()
        return r.json()


async def live_fixtures(league_ids: list[int] | None = None) -> list[dict]:
    """All currently live football fixtures. Optionally filter by league ids."""
    params: dict = {"live": "all"}
    if league_ids:
        params["league"] = "-".join(str(i) for i in league_ids)
    async with httpx.AsyncClient(timeout=15) as client:
        r = await client.get(f"{BASE_URL}/fixtures", headers=_headers(), params=params)
        r.raise_for_status()
        data = r.json()
    if data.get("errors"):
        raise APIFootballError(str(data["errors"]))
    return data.get("response", [])


async def fixture_statistics(fixture_id: int) -> list[dict]:
    """Per-team statistics block for one fixture."""
    async with httpx.AsyncClient(timeout=15) as client:
        r = await client.get(
            f"{BASE_URL}/fixtures/statistics",
            headers=_headers(),
            params={"fixture": fixture_id},
        )
        r.raise_for_status()
        data = r.json()
    if data.get("errors"):
        raise APIFootballError(str(data["errors"]))
    return data.get("response", [])


async def fixture_events(fixture_id: int) -> list[dict]:
    """Goals, cards, subs etc. — used for outcome resolution."""
    async with httpx.AsyncClient(timeout=15) as client:
        r = await client.get(
            f"{BASE_URL}/fixtures/events",
            headers=_headers(),
            params={"fixture": fixture_id},
        )
        r.raise_for_status()
        data = r.json()
    return data.get("response", [])


def stats_to_dict(stats_response: list[dict]) -> dict[int, dict]:
    """API returns [{team:{id}, statistics:[{type, value},...]}, ...].
    Flatten to {team_id: {stat_type: value}}."""
    out: dict[int, dict] = {}
    for team_block in stats_response:
        team_id = team_block["team"]["id"]
        out[team_id] = {}
        for entry in team_block.get("statistics", []):
            stat_type = entry.get("type")
            val = entry.get("value")
            if isinstance(val, str) and val.endswith("%"):
                try:
                    val = int(val.rstrip("%"))
                except ValueError:
                    pass
            out[team_id][stat_type] = val if val is not None else 0
    return out

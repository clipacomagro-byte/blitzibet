"""Live game poller. Every POLL_INTERVAL_SECONDS:
  1. Fetch all live football fixtures
  2. For each, fetch stats and store a snapshot
  3. Run every rule, fire signals when matched
  4. Notify subscribed users
"""
import asyncio
import logging
from datetime import datetime

from config import POLL_INTERVAL_SECONDS, SIGNAL_COOLDOWN_MINUTES
from data import api_football as api
from data import models
from engine import rules
from engine.notifier import dispatch_signal

log = logging.getLogger("blitzibet.poller")


async def poll_once() -> None:
    log.info("Poll tick at %s", datetime.utcnow().isoformat())
    try:
        live = await api.live_fixtures()
    except Exception as e:
        log.exception("Failed to fetch live fixtures: %s", e)
        return

    log.info("Found %d live fixtures", len(live))

    for fx in live:
        try:
            await _process_fixture(fx)
        except Exception:
            log.exception("Processing failed for fixture %s", fx.get("fixture", {}).get("id"))


async def _process_fixture(fx: dict) -> None:
    fixture = fx.get("fixture", {})
    fixture_id = fixture.get("id")
    if not fixture_id:
        return

    minute = fixture.get("status", {}).get("elapsed") or 0
    teams = fx.get("teams", {})
    home_name = teams.get("home", {}).get("name", "Home")
    away_name = teams.get("away", {}).get("name", "Away")
    label = f"{home_name} v {away_name}"
    league = fx.get("league", {}).get("name", "")
    home_goals = fx.get("goals", {}).get("home") or 0
    away_goals = fx.get("goals", {}).get("away") or 0

    raw_stats = await api.fixture_statistics(fixture_id)
    stats_by_team = api.stats_to_dict(raw_stats)
    if not stats_by_team:
        return

    await models.save_snapshot(fixture_id, minute, home_goals, away_goals, stats_by_team)
    history = await models.recent_snapshots(fixture_id, limit=20)

    for rule_fn in rules.RULES:
        rule_name = rule_fn.__name__
        if await models.is_on_cooldown(fixture_id, rule_name, SIGNAL_COOLDOWN_MINUTES):
            continue

        signal = rule_fn(fx, stats_by_team, history)
        if signal is None:
            continue

        log.info("Signal fired: %s on %s (%s')", rule_name, label, minute)

        signal_id = await models.insert_signal(
            sport="football",
            market=signal.market,
            fixture_id=fixture_id,
            fixture_label=label,
            league=league,
            minute=minute,
            rule_name=rule_name,
            criteria=signal.criteria,
            suggested_bet=signal.suggested_bet,
            confidence=signal.confidence,
        )
        await models.record_cooldown(fixture_id, rule_name)
        await dispatch_signal(signal_id, "football", signal.market, label,
                              league, minute, home_goals, away_goals,
                              signal.suggested_bet, signal.confidence)


async def run_forever() -> None:
    while True:
        await poll_once()
        await asyncio.sleep(POLL_INTERVAL_SECONDS)

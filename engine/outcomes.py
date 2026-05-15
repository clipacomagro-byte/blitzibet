"""After a signal fires, check whether the predicted outcome happened
within the window. Runs every ~5 min.
"""
import logging
from data import models, api_football as api

log = logging.getLogger("blitzibet.outcomes")


async def resolve_pending() -> None:
    pending = await models.pending_signals_for_resolution()
    if not pending:
        return
    log.info("Resolving %d pending signals", len(pending))

    for sig in pending:
        try:
            await _resolve_one(sig)
        except Exception:
            log.exception("Outcome resolution failed for signal %s", sig["id"])


async def _resolve_one(sig: dict) -> None:
    fixture_id = sig["fixture_id"]
    market = sig["market"]
    criteria = sig.get("criteria") or {}
    fired_minute = criteria.get("minute") or 0

    events = await api.fixture_events(fixture_id)

    if market == "goals":
        goal_after = any(
            ev.get("type") == "Goal"
            and (ev.get("time", {}).get("elapsed") or 0) >= fired_minute
            and (ev.get("time", {}).get("elapsed") or 0) <= fired_minute + 15
            for ev in events
        )
        status = "won" if goal_after else "lost"
        await models.resolve_signal(sig["id"], status,
                                    note=f"goal_within_window={goal_after}")
        return

    if market == "corners":
        await models.resolve_signal(sig["id"], "void",
                                    note="corner outcomes need stats endpoint, deferred")
        return

    await models.resolve_signal(sig["id"], "void", note="market resolver TODO")

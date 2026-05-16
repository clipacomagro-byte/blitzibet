"""Silently resolve pending signals. Marks WON/LOST in DB.
No follow-up messages sent. History menu shows the result."""
import logging

from data import models

log = logging.getLogger("blitzibet.outcomes")


def _safe_int(v):
    try:
        return int(v) if v is not None else 0
    except (ValueError, TypeError):
        return 0


def _total_corners(stats):
    total = 0
    for team_stats in (stats or {}).values():
        total += _safe_int(team_stats.get("Corner Kicks"))
    return total


def _total_shots(stats):
    total = 0
    for team_stats in (stats or {}).values():
        total += _safe_int(team_stats.get("Total Shots"))
    return total


def _total_yellows(stats):
    total = 0
    for team_stats in (stats or {}).values():
        total += _safe_int(team_stats.get("Yellow Cards"))
    return total


async def resolve_pending():
    """Check pending signals - mark as won/lost silently in DB."""
    signals = await models.pending_signals_for_resolution()
    if not signals:
        return
    log.info("Resolving %d pending signals", len(signals))
    for sig in signals:
        try:
            await _resolve_one(sig)
        except Exception:
            log.exception("Resolution failed for signal %s", sig.get("id"))


async def _resolve_one(sig):
    market = sig.get("market") or ""
    criteria = sig.get("criteria") or {}
    fired_minute = _safe_int(criteria.get("minute"))
    fixture_id = sig.get("fixture_id")
    if not fixture_id:
        return

    snapshots = await models.recent_snapshots(fixture_id, limit=30)
    if not snapshots:
        return

    # Find the snapshot closest to fired minute (going forward in time)
    at_fired = None
    sorted_by_minute = sorted(
        [s for s in snapshots if s.get("minute") is not None],
        key=lambda x: x["minute"],
    )
    for s in sorted_by_minute:
        if s["minute"] >= fired_minute:
            at_fired = s
            break
    if not at_fired:
        return

    latest = sorted_by_minute[-1] if sorted_by_minute else None
    if not latest:
        return
    latest_minute = _safe_int(latest.get("minute"))

    if market == "goals":
        await _resolve_goals(sig, at_fired, latest, latest_minute, fired_minute)
    elif market == "corners":
        await _resolve_corners(sig, at_fired, latest, latest_minute, fired_minute)
    elif market == "btts":
        await _resolve_btts(sig, latest, latest_minute)
    elif market == "shots":
        await _resolve_shots(sig, criteria, latest, latest_minute)
    elif market == "cards":
        await _resolve_cards(sig, at_fired, latest, latest_minute, fired_minute)


async def _resolve_goals(sig, at_fired, latest, latest_minute, fired_minute):
    base_total = (
        _safe_int(at_fired.get("home_score"))
        + _safe_int(at_fired.get("away_score"))
    )
    now_total = (
        _safe_int(latest.get("home_score"))
        + _safe_int(latest.get("away_score"))
    )
    # 12 min window for goals signals
    if latest_minute - fired_minute >= 12 or latest_minute >= 92:
        if now_total > base_total:
            await models.resolve_signal(
                sig["id"], "won", "Goal scored within window",
            )
            log.info("Signal %s WON (goals)", sig["id"])
        elif latest_minute >= 92 or latest_minute - fired_minute >= 15:
            await models.resolve_signal(
                sig["id"], "lost", "No goal in window",
            )
            log.info("Signal %s LOST (goals)", sig["id"])


async def _resolve_corners(sig, at_fired, latest, latest_minute, fired_minute):
    base_c = _total_corners(at_fired.get("stats"))
    now_c = _total_corners(latest.get("stats"))
    if latest_minute - fired_minute >= 8 or latest_minute >= 92:
        if now_c > base_c:
            await models.resolve_signal(
                sig["id"], "won", f"Corner within window ({base_c} -> {now_c})",
            )
            log.info("Signal %s WON (corners)", sig["id"])
        elif latest_minute >= 92 or latest_minute - fired_minute >= 10:
            await models.resolve_signal(
                sig["id"], "lost", "No corner in window",
            )
            log.info("Signal %s LOST (corners)", sig["id"])


async def _resolve_btts(sig, latest, latest_minute):
    if latest_minute < 90:
        return
    h = _safe_int(latest.get("home_score"))
    a = _safe_int(latest.get("away_score"))
    if h > 0 and a > 0:
        await models.resolve_signal(sig["id"], "won", "BTTS hit")
        log.info("Signal %s WON (btts)", sig["id"])
    else:
        await models.resolve_signal(sig["id"], "lost", "BTTS missed")
        log.info("Signal %s LOST (btts)", sig["id"])


async def _resolve_shots(sig, criteria, latest, latest_minute):
    if latest_minute < 90:
        return
    now_shots = _total_shots(latest.get("stats"))
    # Signal said "over X.5" where X = total_shots at fire + 6
    base = _safe_int(criteria.get("total_shots"))
    target = base + 6
    if now_shots > target:
        await models.resolve_signal(
            sig["id"], "won", f"Total shots {now_shots} > {target}",
        )
        log.info("Signal %s WON (shots)", sig["id"])
    else:
        await models.resolve_signal(
            sig["id"], "lost", f"Only {now_shots} shots, needed > {target}",
        )
        log.info("Signal %s LOST (shots)", sig["id"])


async def _resolve_cards(sig, at_fired, latest, latest_minute, fired_minute):
    base_y = _total_yellows(at_fired.get("stats"))
    now_y = _total_yellows(latest.get("stats"))
    if latest_minute - fired_minute >= 10 or latest_minute >= 92:
        if now_y >= base_y + 2 or now_y >= 5:
            await models.resolve_signal(
                sig["id"], "won", f"Cards continued: {base_y} -> {now_y}",
            )
            log.info("Signal %s WON (cards)", sig["id"])
        elif latest_minute >= 92:
            await models.resolve_signal(
                sig["id"], "lost", f"Cards stayed at {now_y}",
            )
            log.info("Signal %s LOST (cards)", sig["id"])

"""Background worker: runs the poller + outcome resolver on a schedule.
Also runs demo-signal firing when DEMO_MODE=true."""
import asyncio
import logging
import os

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from config import POLL_INTERVAL_SECONDS
from data import db
from data import api_football as api
from engine.poller import poll_once
from engine.outcomes import resolve_pending
from engine.demo import fire_demo_signal


DEMO_MODE = os.getenv("DEMO_MODE", "").lower() in ("1", "true", "yes")
DEMO_INTERVAL_SECONDS = int(os.getenv("DEMO_INTERVAL_SECONDS", "120"))


async def main():
    logging.basicConfig(
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        level=logging.INFO,
    )
    log = logging.getLogger("blitzibet.worker")
    log.info("Blitzibet worker starting")

    await db.init_pool()

    # Real data probe — non-fatal if it fails (demo mode doesn't need it)
    try:
        status = await api.probe()
        log.info("API-Football reachable: %s", status.get("response", "ok"))
    except Exception as e:
        log.warning("API-Football probe failed (ok if in demo mode): %s", e)

    scheduler = AsyncIOScheduler()
    scheduler.add_job(poll_once, "interval", seconds=POLL_INTERVAL_SECONDS)
    scheduler.add_job(resolve_pending, "interval", minutes=5)

    if DEMO_MODE:
        log.info("DEMO MODE ENABLED — firing synthetic signals every %ds",
                 DEMO_INTERVAL_SECONDS)
        scheduler.add_job(fire_demo_signal, "interval",
                          seconds=DEMO_INTERVAL_SECONDS,
                          next_run_time=None)  # fires after first interval
        # Also fire one immediately so demo isn't gated on the first interval
        asyncio.create_task(_initial_demo_fire())

    scheduler.start()

    try:
        while True:
            await asyncio.sleep(3600)
    finally:
        scheduler.shutdown()


async def _initial_demo_fire():
    """Fire one demo signal ~10 seconds after boot for instant testing."""
    await asyncio.sleep(10)
    try:
        await fire_demo_signal()
    except Exception:
        logging.getLogger("blitzibet.worker").exception("Initial demo fire failed")


if __name__ == "__main__":
    asyncio.run(main())

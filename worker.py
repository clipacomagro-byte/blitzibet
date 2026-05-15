"""Worker process. Runs:
  - Poller every POLL_INTERVAL_SECONDS
  - Outcome resolver every 5 minutes

Railway: 'worker' process in Procfile.
"""
import asyncio
import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from config import POLL_INTERVAL_SECONDS, API_FOOTBALL_KEY
from data import api_football as api
from engine.poller import poll_once
from engine.outcomes import resolve_pending


logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    level=logging.INFO,
)
log = logging.getLogger("blitzibet.worker")


async def main() -> None:
    log.info("Blitzibet worker starting")

    if not API_FOOTBALL_KEY:
        log.error("API_FOOTBALL_KEY not set — engine cannot run. Exiting.")
        return

    try:
        status = await api.probe()
        log.info("API-Football reachable: %s", status.get("response", {}).get("subscription", {}))
    except Exception as e:
        log.error("API-Football probe failed: %s", e)

    scheduler = AsyncIOScheduler()
    scheduler.add_job(poll_once, "interval", seconds=POLL_INTERVAL_SECONDS,
                      max_instances=1, coalesce=True)
    scheduler.add_job(resolve_pending, "interval", minutes=5,
                      max_instances=1, coalesce=True)
    scheduler.start()

    stop = asyncio.Event()
    try:
        await stop.wait()
    except (KeyboardInterrupt, SystemExit):
        log.info("Worker shutting down")


if __name__ == "__main__":
    asyncio.run(main())

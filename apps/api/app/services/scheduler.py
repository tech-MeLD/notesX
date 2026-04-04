from __future__ import annotations

import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler
import asyncpg

from app.core.config import settings
from app.services.rss_service import run_ingestion_job

logger = logging.getLogger(__name__)


async def run_scheduled_ingestion(pool: asyncpg.Pool) -> None:
    result = await run_ingestion_job(pool, force=False)
    logger.info("Scheduled RSS ingestion finished: %s", result)


def create_scheduler(pool: asyncpg.Pool) -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler(timezone="UTC")
    scheduler.add_job(
        run_scheduled_ingestion,
        "interval",
        minutes=settings.rss_scheduler_interval_minutes,
        kwargs={"pool": pool},
        id="rss-ingestion",
        max_instances=1,
        coalesce=True,
        replace_existing=True,
    )
    return scheduler

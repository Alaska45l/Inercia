from __future__ import annotations

import asyncio
import logging
import random
from pathlib import Path
from typing import Awaitable, Callable, Optional

from inercia.ai.graph import process_unprocessed_jobs
from inercia.config import get_settings
from inercia.core.orchestrator import scrape_query

logger = logging.getLogger("inercia.core.scheduler")

SchedulerStatusCallback = Callable[[int], Awaitable[None]]


async def run_periodic_scan(
    query: str,
    interval_seconds: float,
    db_path: Optional[Path] = None,
    stop_event: Optional[asyncio.Event] = None,
    allow_network: bool = False,
) -> None:
    if interval_seconds <= 0:
        raise ValueError("interval_seconds must be positive")
    while stop_event is None or not stop_event.is_set():
        await scrape_query(query=query, db_path=db_path, allow_network=allow_network)
        logger.info("Periodic scan completed for query=%s", query)
        try:
            if stop_event is None:
                await asyncio.sleep(interval_seconds)
            else:
                await asyncio.wait_for(stop_event.wait(), timeout=interval_seconds)
        except asyncio.TimeoutError:
            continue


async def run_scheduler_loop(
    db_path: Optional[Path] = None,
    stop_event: Optional[asyncio.Event] = None,
    status_callback: Optional[SchedulerStatusCallback] = None,
) -> None:
    while stop_event is None or not stop_event.is_set():
        settings = get_settings(db_path=db_path)
        await scrape_query(query="", db_path=db_path, allow_network=settings.allow_upwork_network)
        summary = await process_unprocessed_jobs(limit=20, db_path=db_path)
        logger.info("Scheduler cycle completed | summary=%s", summary)

        min_seconds = max(settings.scheduler_interval_min_minutes, 1) * 60
        max_seconds = max(settings.scheduler_interval_max_minutes, settings.scheduler_interval_min_minutes) * 60
        wait_seconds = random.randint(min_seconds, max_seconds)
        if status_callback is not None:
            await status_callback(wait_seconds)
        try:
            if stop_event is None:
                await asyncio.sleep(wait_seconds)
            else:
                await asyncio.wait_for(stop_event.wait(), timeout=wait_seconds)
        except asyncio.TimeoutError:
            continue


__all__ = ["SchedulerStatusCallback", "run_periodic_scan", "run_scheduler_loop"]

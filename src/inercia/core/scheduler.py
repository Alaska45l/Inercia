from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Optional

from inercia.core.orchestrator import scrape_query

logger = logging.getLogger("inercia.core.scheduler")


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


__all__ = ["run_periodic_scan"]

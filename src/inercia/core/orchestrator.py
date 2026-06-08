from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Any, Optional, Union

from inercia.config import get_settings
from inercia.core.state import EstadoBot
from inercia.db.manager import init_db, set_session_value, upsert_job
from inercia.scraper.feed import FeedDownloadError, FeedJob, fetch_jobs
from inercia.scraper.engine import browser_context
from inercia.scraper.filter_scraper import FilteredJobCard, LAST_SCRAPED_UPWORK_ID_KEY, discover_filtered_jobs
from inercia.scraper.job_detail import extract_job_markdown

logger = logging.getLogger("inercia.core.orchestrator")

QUEUE_MAXSIZE: int = 50
CONSUMER_COUNT: int = 1
_QUEUE_SENTINEL: object = object()


def _job_payload(feed_job: FeedJob | FilteredJobCard, raw_markdown: str) -> dict[str, object]:
    return {
        "upwork_id": feed_job.upwork_id,
        "title": feed_job.title,
        "description": feed_job.description or raw_markdown[:500],
        "job_type": feed_job.job_type,
        "raw_markdown": raw_markdown,
        "status": "new",
    }


async def _producer(
    query: str,
    queue: asyncio.Queue[Union[FeedJob, FilteredJobCard, object]],
    state: EstadoBot,
    feed_xml: Optional[str],
    allow_network: bool,
    db_path: Optional[Path],
    first_seen_upwork_ids: list[str],
    consumer_count: int,
) -> None:
    state.set_phase("fetching_filtered_search" if allow_network else "fetching_feed")
    try:
        if allow_network:
            jobs = await discover_filtered_jobs(query=query, db_path=db_path)
        else:
            jobs = await fetch_jobs(query=query, feed_xml=feed_xml, allow_network=False)
        if jobs:
            first_seen_upwork_ids.append(jobs[0].upwork_id)
        state.record_queued(len(jobs))
        logger.info("Producer queued %d jobs for query=%s", len(jobs), query or "configured filters")
        for job in jobs:
            await queue.put(job)
    except FeedDownloadError as exc:
        message = f"{type(exc).__name__}: {exc}"
        logger.warning("Producer failed to fetch feed: %s", exc)
        state.record_error(message)
    finally:
        for _ in range(consumer_count):
            await queue.put(_QUEUE_SENTINEL)


async def _consumer(
    queue: asyncio.Queue[Union[FeedJob, FilteredJobCard, object]],
    state: EstadoBot,
    db_path: Optional[Path],
    allow_network: bool,
    browser_lock: asyncio.Lock,
) -> None:
    state.set_phase("consuming_details")
    settings = get_settings(db_path=db_path)
    context_manager: Any = None
    context: Any = None
    try:
        while True:
            item = await queue.get()
            try:
                if item is _QUEUE_SENTINEL:
                    return
                if not isinstance(item, (FeedJob, FilteredJobCard)):
                    raise TypeError("Unexpected queue item")
                if allow_network and context is None:
                    async with browser_lock:
                        context_manager = browser_context(str(settings.upwork_session_dir))
                        context = await context_manager.__aenter__()
                detail = await extract_job_markdown(
                    item.url,
                    allow_network=allow_network,
                    user_data_dir=settings.upwork_session_dir if allow_network else None,
                    context=context,
                )
                payload = _job_payload(item, detail.markdown)
                await asyncio.to_thread(upsert_job, payload, db_path)
                state.record_processed(inserted=True)
            except Exception as exc:
                message = f"{type(exc).__name__}: {exc}"
                logger.exception("Consumer failed")
                state.record_error(message)
                state.record_processed(inserted=False)
            finally:
                queue.task_done()
    finally:
        if context_manager is not None:
            await context_manager.__aexit__(None, None, None)


async def scrape_query(
    query: str,
    db_path: Optional[Path] = None,
    feed_xml: Optional[str] = None,
    allow_network: bool = False,
) -> dict[str, object]:
    state = EstadoBot(current_query=query)
    await asyncio.to_thread(init_db, db_path)
    queue: asyncio.Queue[Union[FeedJob, FilteredJobCard, object]] = asyncio.Queue(maxsize=QUEUE_MAXSIZE)
    first_seen_upwork_ids: list[str] = []
    consumer_count = 1
    browser_lock = asyncio.Lock()
    producer_task = asyncio.create_task(
        _producer(
            query=query,
            queue=queue,
            state=state,
            feed_xml=feed_xml,
            allow_network=allow_network,
            db_path=db_path,
            first_seen_upwork_ids=first_seen_upwork_ids,
            consumer_count=consumer_count,
        )
    )
    consumer_tasks = [
        asyncio.create_task(
            _consumer(
                queue=queue,
                state=state,
                db_path=db_path,
                allow_network=allow_network,
                browser_lock=browser_lock,
            )
        )
        for _ in range(consumer_count)
    ]
    try:
        await producer_task
        await queue.join()
    finally:
        for task in consumer_tasks:
            if not task.done():
                task.cancel()
        await asyncio.gather(*consumer_tasks, return_exceptions=True)
    if allow_network and first_seen_upwork_ids and state.snapshot()["failed"] == 0:
        await asyncio.to_thread(set_session_value, LAST_SCRAPED_UPWORK_ID_KEY, first_seen_upwork_ids[0], db_path)
    state.set_phase("done")
    return state.snapshot()


def scrape_query_sync(
    query: str,
    db_path: Optional[Path] = None,
    feed_xml: Optional[str] = None,
    allow_network: bool = False,
) -> dict[str, object]:
    return asyncio.run(
        scrape_query(
            query=query,
            db_path=db_path,
            feed_xml=feed_xml,
            allow_network=allow_network,
        )
    )


__all__ = ["CONSUMER_COUNT", "QUEUE_MAXSIZE", "scrape_query", "scrape_query_sync"]

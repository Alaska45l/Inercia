from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Optional, Union

from inercia.core.state import EstadoBot
from inercia.db.manager import init_db, upsert_job
from inercia.scraper.feed import FeedDownloadError, FeedJob, fetch_jobs
from inercia.scraper.job_detail import extract_job_markdown

logger = logging.getLogger("inercia.core.orchestrator")

QUEUE_MAXSIZE: int = 50
CONSUMER_COUNT: int = 2
_QUEUE_SENTINEL: object = object()


def _job_payload(feed_job: FeedJob, raw_markdown: str) -> dict[str, object]:
    return {
        "upwork_id": feed_job.upwork_id,
        "title": feed_job.title,
        "description": feed_job.description or raw_markdown[:500],
        "job_type": "hourly",
        "raw_markdown": raw_markdown,
        "status": "new",
    }


async def _producer(
    query: str,
    queue: asyncio.Queue[Union[FeedJob, object]],
    state: EstadoBot,
    feed_xml: Optional[str],
    allow_network: bool,
) -> None:
    state.set_phase("fetching_feed")
    try:
        jobs = await fetch_jobs(query=query, feed_xml=feed_xml, allow_network=allow_network)
        state.record_queued(len(jobs))
        logger.info("Producer queued %d feed jobs for query=%s", len(jobs), query)
        for job in jobs:
            await queue.put(job)
    except FeedDownloadError as exc:
        message = f"{type(exc).__name__}: {exc}"
        logger.warning("Producer failed to fetch feed: %s", exc)
        state.record_error(message)
    finally:
        for _ in range(CONSUMER_COUNT):
            await queue.put(_QUEUE_SENTINEL)


async def _consumer(
    queue: asyncio.Queue[Union[FeedJob, object]],
    state: EstadoBot,
    db_path: Optional[Path],
    allow_network: bool,
) -> None:
    state.set_phase("consuming_details")
    while True:
        item = await queue.get()
        try:
            if item is _QUEUE_SENTINEL:
                return
            if not isinstance(item, FeedJob):
                raise TypeError("Unexpected queue item")
            detail = await extract_job_markdown(item.url, allow_network=allow_network)
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


async def scrape_query(
    query: str,
    db_path: Optional[Path] = None,
    feed_xml: Optional[str] = None,
    allow_network: bool = False,
) -> dict[str, object]:
    state = EstadoBot(current_query=query)
    await asyncio.to_thread(init_db, db_path)
    queue: asyncio.Queue[Union[FeedJob, object]] = asyncio.Queue(maxsize=QUEUE_MAXSIZE)
    producer_task = asyncio.create_task(
        _producer(
            query=query,
            queue=queue,
            state=state,
            feed_xml=feed_xml,
            allow_network=allow_network,
        )
    )
    consumer_tasks = [
        asyncio.create_task(
            _consumer(queue=queue, state=state, db_path=db_path, allow_network=allow_network)
        )
        for _ in range(CONSUMER_COUNT)
    ]
    try:
        await producer_task
        await queue.join()
    finally:
        for task in consumer_tasks:
            if not task.done():
                task.cancel()
        await asyncio.gather(*consumer_tasks, return_exceptions=True)
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

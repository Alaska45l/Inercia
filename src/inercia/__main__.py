from __future__ import annotations

import argparse
import asyncio
import contextvars
import functools
import logging
import sys
import threading
from collections.abc import Coroutine
from typing import Any, Optional, Sequence, TypeVar

from inercia import __version__
from inercia.config import get_settings

logger = logging.getLogger("inercia.__main__")

T = TypeVar("T")


async def _polling_to_thread(func: Any, /, *args: Any, **kwargs: Any) -> Any:
    context = contextvars.copy_context()
    call = functools.partial(context.run, func, *args, **kwargs)
    done = threading.Event()
    result: dict[str, Any] = {}

    def runner() -> None:
        try:
            result["value"] = call()
        except BaseException as exc:
            result["error"] = exc
        finally:
            done.set()

    threading.Thread(target=runner, daemon=True).start()
    while not done.is_set():
        await asyncio.sleep(0.01)
    if "error" in result:
        raise result["error"]
    return result.get("value")


def _install_asyncio_thread_compat() -> None:
    if sys.version_info >= (3, 14):
        asyncio.to_thread = _polling_to_thread


async def _with_asyncio_compat(coro: Coroutine[Any, Any, T]) -> T:
    _install_asyncio_thread_compat()
    return await coro


def _run_async(coro: Coroutine[Any, Any, T]) -> T:
    return asyncio.run(_with_asyncio_compat(coro))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m inercia")
    parser.add_argument("--version", action="version", version=f"inercia {__version__}")
    subparsers = parser.add_subparsers(dest="command")
    subparsers.add_parser("init-db", help="Initialize the configured SQLite database.")
    scrape_parser = subparsers.add_parser("scrape", help="Scrape Upwork RSS jobs for a query.")
    scrape_parser.add_argument("query", help="Upwork search query.")
    scrape_parser.add_argument(
        "--allow-network",
        action="store_true",
        help="Allow live Upwork RSS and job detail requests.",
    )
    process_parser = subparsers.add_parser("process", help="Run AI proposal pipeline for new jobs.")
    process_parser.add_argument("--limit", type=int, default=20, help="Maximum new jobs to process.")
    api_parser = subparsers.add_parser("api", help="Run the WebSocket API server.")
    api_parser.add_argument("--host", default="127.0.0.1", help="WebSocket bind host.")
    api_parser.add_argument("--port", type=int, default=None, help="WebSocket bind port.")
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
    )
    parser = build_parser()
    args = parser.parse_args(argv)
    settings = get_settings()

    if args.command == "init-db":
        from inercia.db.manager import init_db

        init_db(settings.db_path)
        logger.info("Database initialized at %s", settings.db_path)
        return 0
    if args.command == "scrape":
        from inercia.core.orchestrator import scrape_query

        summary = _run_async(
            scrape_query(
                query=args.query,
                db_path=settings.db_path,
                allow_network=args.allow_network,
            )
        )
        logger.info(
            "Scrape completed | queued=%s | processed=%s | inserted=%s | failed=%s",
            summary["queued"],
            summary["processed"],
            summary["inserted"],
            summary["failed"],
        )
        return 0
    if args.command == "process":
        from inercia.ai.graph import process_unprocessed_jobs

        summary = _run_async(process_unprocessed_jobs(limit=args.limit, db_path=settings.db_path))
        logger.info(
            "Process completed | processed=%s | ready=%s | blacklisted=%s | failed=%s",
            summary["processed"],
            summary["ready"],
            summary["blacklisted"],
            summary["failed"],
        )
        return 0
    if args.command == "api":
        from inercia.api.server import serve

        try:
            _run_async(serve(db_path=settings.db_path, host=args.host, port=args.port))
        except KeyboardInterrupt:
            logger.info("WebSocket API stopped")
        return 0

    logger.info("Inercia %s configured with DB at %s", __version__, settings.db_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

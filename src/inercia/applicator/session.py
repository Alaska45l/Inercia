from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, Optional

from inercia.config import get_settings
from inercia.scraper.engine import CHROMIUM_ARGS, random_viewport, resolve_chromium_executable

if TYPE_CHECKING:
    from playwright.async_api import BrowserContext, Playwright

logger = logging.getLogger("inercia.applicator.session")


@dataclass(frozen=True)
class UpworkSession:
    playwright: "Playwright"
    context: "BrowserContext"


async def open_persistent_upwork_session(
    user_data_dir: Optional[Path] = None,
    headless: bool = True,
    system_browser: bool = False,
) -> UpworkSession:
    from playwright.async_api import async_playwright

    settings = get_settings()
    profile_dir = user_data_dir or settings.upwork_session_dir
    profile_dir.mkdir(parents=True, exist_ok=True)
    playwright = await async_playwright().start()
    try:
        executable_path = resolve_chromium_executable(playwright, prefer_system=system_browser)
        using_system_browser = executable_path is not None
        context_kwargs: dict[str, Any] = {
            "user_data_dir": str(profile_dir),
            "headless": headless,
            "viewport": random_viewport(),
            "locale": "en-US",
            "accept_downloads": False,
            "args": CHROMIUM_ARGS,
        }
        if executable_path is not None:
            context_kwargs["executable_path"] = executable_path
        context = await playwright.chromium.launch_persistent_context(
            **context_kwargs,
        )
    except Exception:
        await playwright.stop()
        raise
    logger.info(
        "Persistent Upwork session opened | dir=%s | headless=%s | system_browser=%s",
        profile_dir,
        headless,
        using_system_browser,
    )
    return UpworkSession(playwright=playwright, context=context)


@asynccontextmanager
async def persistent_upwork_session(
    user_data_dir: Optional[Path] = None,
    headless: bool = True,
) -> AsyncIterator["BrowserContext"]:
    session = await open_persistent_upwork_session(user_data_dir=user_data_dir, headless=headless)
    try:
        yield session.context
    finally:
        await session.context.close()
        await session.playwright.stop()
        logger.info("Persistent Upwork session closed")


__all__ = ["UpworkSession", "open_persistent_upwork_session", "persistent_upwork_session"]

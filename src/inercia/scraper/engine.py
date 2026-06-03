from __future__ import annotations

import asyncio
import logging
import random
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING, Any, Optional

from inercia.scraper.selectors import RESOURCE_ROUTE_PATTERN

if TYPE_CHECKING:
    from playwright.async_api import BrowserContext, Page, Playwright

logger = logging.getLogger("inercia.scraper.engine")

NAV_TIMEOUT_MS: int = 25_000

CHROMIUM_ARGS: list[str] = [
    "--disable-blink-features=AutomationControlled",
    "--disable-infobars",
    "--no-sandbox",
    "--disable-dev-shm-usage",
    "--disable-features=IsolateOrigins,site-per-process",
    "--lang=en-US,en;q=0.9",
    "--disable-gpu",
]

BLOCKED_RESOURCE_TYPES: frozenset[str] = frozenset(
    {"image", "media", "font", "websocket", "eventsource", "manifest"}
)

USER_AGENTS: tuple[str, ...] = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_4_1) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
)


def random_viewport() -> dict[str, int]:
    return {
        "width": random.randint(1366, 1920),
        "height": random.randint(768, 1080),
    }


async def apply_stealth(context: "BrowserContext") -> None:
    await context.add_init_script(
        """
        Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
        window.chrome = window.chrome || { runtime: {} };
        Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3] });
        Object.defineProperty(navigator, 'languages', { get: () => ['en-US', 'en'] });
        """
    )


async def create_context(playwright: "Playwright", user_data_dir: Optional[str] = None) -> "BrowserContext":
    context_kwargs = {
        "headless": True,
        "args": CHROMIUM_ARGS,
        "viewport": random_viewport(),
        "user_agent": random.choice(USER_AGENTS),
        "locale": "en-US",
        "timezone_id": "America/Argentina/Buenos_Aires",
        "accept_downloads": False,
    }
    if user_data_dir is not None:
        context = await playwright.chromium.launch_persistent_context(
            user_data_dir=user_data_dir,
            **context_kwargs,
        )
    else:
        browser = await playwright.chromium.launch(
            headless=True,
            args=CHROMIUM_ARGS,
        )
        context = await browser.new_context(
            viewport=context_kwargs["viewport"],
            user_agent=str(context_kwargs["user_agent"]),
            locale=str(context_kwargs["locale"]),
            timezone_id=str(context_kwargs["timezone_id"]),
            accept_downloads=False,
        )
    await apply_stealth(context)
    return context


async def block_heavy_resources(page: "Page") -> None:
    async def _interceptor(route: Any, request: Any) -> None:
        resource_type = request.resource_type
        if resource_type in BLOCKED_RESOURCE_TYPES:
            await route.abort()
            return
        await route.continue_()

    await page.route(RESOURCE_ROUTE_PATTERN, _interceptor)


async def human_mouse_jitter(page: "Page") -> None:
    try:
        await page.mouse.move(random.randint(120, 700), random.randint(120, 500))
        await asyncio.sleep(random.uniform(0.2, 0.6))
        await page.mouse.move(random.randint(240, 900), random.randint(180, 650), steps=random.randint(4, 10))
    except Exception as exc:
        logger.debug("Mouse jitter skipped: %s", exc)


@asynccontextmanager
async def stealth_context(user_data_dir: Optional[str] = None) -> AsyncIterator["BrowserContext"]:
    from playwright.async_api import async_playwright

    async with async_playwright() as playwright:
        context = await create_context(playwright, user_data_dir)
        try:
            yield context
        finally:
            await context.close()


__all__ = [
    "BLOCKED_RESOURCE_TYPES",
    "CHROMIUM_ARGS",
    "NAV_TIMEOUT_MS",
    "USER_AGENTS",
    "apply_stealth",
    "block_heavy_resources",
    "create_context",
    "human_mouse_jitter",
    "random_viewport",
    "stealth_context",
]

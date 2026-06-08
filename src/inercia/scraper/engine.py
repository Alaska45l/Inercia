from __future__ import annotations

import logging
import shutil
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import TYPE_CHECKING, Any, Optional

from inercia.scraper.selectors import RESOURCE_ROUTE_PATTERN

if TYPE_CHECKING:
    from playwright.async_api import BrowserContext, Page, Playwright

logger = logging.getLogger("inercia.scraper.engine")

NAV_TIMEOUT_MS: int = 25_000

SAFE_CHROMIUM_ARGS: list[str] = [
    "--no-sandbox",
    "--disable-dev-shm-usage",
    "--lang=en-US,en;q=0.9",
]

# Compatibility alias. These flags are runtime/sandbox flags only; fingerprint
# overrides and anti-detection flags are intentionally not used.
CHROMIUM_ARGS: list[str] = SAFE_CHROMIUM_ARGS

BLOCKED_RESOURCE_TYPES: frozenset[str] = frozenset({"image", "media", "font"})

USER_AGENTS: tuple[str, ...] = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
)


def random_viewport() -> dict[str, int]:
    return {"width": 1440, "height": 900}


def resolve_chromium_executable(playwright: "Playwright", prefer_system: bool = False) -> Optional[str]:
    system_browser = shutil.which("chromium") or shutil.which("google-chrome") or shutil.which("google-chrome-stable")
    if prefer_system:
        return system_browser
    managed_browser = str(getattr(playwright.chromium, "executable_path", "") or "")
    if managed_browser and Path(managed_browser).exists():
        return None
    if system_browser is not None:
        logger.info("Playwright Chromium executable missing; using system browser at %s", system_browser)
    return system_browser


async def create_context(playwright: "Playwright", user_data_dir: Optional[str] = None) -> "BrowserContext":
    executable_path = resolve_chromium_executable(playwright)
    context_kwargs = {
        "headless": True,
        "args": CHROMIUM_ARGS,
        "viewport": random_viewport(),
        "locale": "en-US",
        "accept_downloads": False,
    }
    if executable_path is not None:
        context_kwargs["executable_path"] = executable_path
    if user_data_dir is not None:
        context = await playwright.chromium.launch_persistent_context(
            user_data_dir=user_data_dir,
            **context_kwargs,
        )
    else:
        launch_kwargs: dict[str, Any] = {
            "headless": True,
            "args": CHROMIUM_ARGS,
        }
        if executable_path is not None:
            launch_kwargs["executable_path"] = executable_path
        browser = await playwright.chromium.launch(
            **launch_kwargs,
        )
        context = await browser.new_context(
            viewport=context_kwargs["viewport"],
            locale=str(context_kwargs["locale"]),
            accept_downloads=False,
        )
    return context


async def block_heavy_resources(page: "Page") -> None:
    async def _interceptor(route: Any, request: Any) -> None:
        resource_type = request.resource_type
        if resource_type in BLOCKED_RESOURCE_TYPES:
            await route.abort()
            return
        await route.continue_()

    await page.route(RESOURCE_ROUTE_PATTERN, _interceptor)


@asynccontextmanager
async def browser_context(user_data_dir: Optional[str] = None) -> AsyncIterator["BrowserContext"]:
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
    "SAFE_CHROMIUM_ARGS",
    "USER_AGENTS",
    "block_heavy_resources",
    "browser_context",
    "create_context",
    "random_viewport",
    "resolve_chromium_executable",
]

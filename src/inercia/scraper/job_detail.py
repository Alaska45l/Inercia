from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Optional

from inercia.config import get_settings
from inercia.scraper.feed import extract_upwork_id
from inercia.scraper.selectors import UPWORK_MAIN

if TYPE_CHECKING:
    from playwright.async_api import BrowserContext

logger = logging.getLogger("inercia.scraper.job_detail")

MOCK_JOB_MARKDOWN: str = """# Python Playwright automation developer

Build an async browser automation workflow with Python 3.11, Playwright, and SQLite.
The workflow should parse job listings, deduplicate records, and prepare proposal data.

Job type: hourly
Hourly range: $25-$45/hr
Duration: 1 to 3 months
Experience level: Intermediate
Skills: Python, Playwright, SQLite, asyncio, web scraping
Client country: United States
Client total spent: $12,400
Client hire rate: 0.72
Client reviews: 18
Connects required: 8
Allows attachments: yes

Screening questions:
- Describe a Playwright scraper you built.
- How do you avoid blocking the event loop?
"""


@dataclass(frozen=True)
class JobMarkdown:
    upwork_id: str
    url: str
    markdown: str


def is_mock_url(url: str) -> bool:
    return "upwork.com/freelance-jobs/apply/1876543210" in url or url.startswith("mock://")


def text_to_markdown(text: str) -> str:
    lines = [line.strip() for line in text.splitlines()]
    compact_lines = [line for line in lines if line]
    if not compact_lines:
        return ""
    return "\n\n".join(compact_lines)


async def extract_job_markdown(
    url: str,
    allow_network: bool = False,
    user_data_dir: Optional[Path] = None,
    context: Optional["BrowserContext"] = None,
) -> JobMarkdown:
    upwork_id = extract_upwork_id(url)
    if not allow_network or is_mock_url(url):
        await asyncio.sleep(0)
        return JobMarkdown(upwork_id=upwork_id, url=url, markdown=MOCK_JOB_MARKDOWN)

    from playwright.async_api import TimeoutError as PlaywrightTimeoutError

    from inercia.scraper.engine import NAV_TIMEOUT_MS, block_heavy_resources, human_mouse_jitter, stealth_context

    async def _extract_from_context(active_context: "BrowserContext") -> str:
        page = await active_context.new_page()
        await block_heavy_resources(page)
        try:
            response = await page.goto(url, wait_until="domcontentloaded", timeout=NAV_TIMEOUT_MS)
            if response is not None and response.status >= 400:
                raise RuntimeError(f"Upwork returned HTTP {response.status} for {url}")
            await human_mouse_jitter(page)
            main = page.locator(UPWORK_MAIN)
            await main.wait_for(state="visible", timeout=NAV_TIMEOUT_MS)
            return await main.inner_text(timeout=NAV_TIMEOUT_MS)
        except PlaywrightTimeoutError as exc:
            raise RuntimeError(f"Timed out extracting Upwork job detail: {url}") from exc
        finally:
            await page.close()

    if context is not None:
        text = await _extract_from_context(context)
        return JobMarkdown(upwork_id=upwork_id, url=url, markdown=text_to_markdown(text))

    selected_user_data_dir = user_data_dir or get_settings().upwork_session_dir
    async with stealth_context(str(selected_user_data_dir)) as owned_context:
        text = await _extract_from_context(owned_context)
    return JobMarkdown(upwork_id=upwork_id, url=url, markdown=text_to_markdown(text))


__all__ = ["JobMarkdown", "MOCK_JOB_MARKDOWN", "extract_job_markdown", "is_mock_url", "text_to_markdown"]

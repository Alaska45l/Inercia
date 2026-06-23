from __future__ import annotations

import asyncio
import logging
import re
import urllib.parse
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

from inercia.applicator.auth import UpworkAuthenticationError, ensure_upwork_authenticated_page, page_body_text
from inercia.applicator.session import persistent_upwork_session
from inercia.config import UpworkSearchFilters, get_settings
from inercia.db.manager import get_blacklist_keywords, get_job_by_upwork_id, get_session_value
from inercia.scraper.engine import NAV_TIMEOUT_MS, block_heavy_resources
from inercia.scraper.feed import extract_upwork_id
from inercia.scraper.selectors import (
    UPWORK_BUTTON_BY_TEXT,
    UPWORK_CHECKBOX_BY_LABEL,
    UPWORK_FILTER_NUMBER_INPUT,
    UPWORK_FILTER_TEXT_INPUT,
    UPWORK_JOB_CARD,
    UPWORK_JOB_CARD_AGE,
    UPWORK_JOB_CARD_DESCRIPTION,
    UPWORK_JOB_CARD_PROPOSALS,
    UPWORK_JOB_CARD_TITLE_LINK,
    UPWORK_LABEL_BY_TEXT,
    UPWORK_PAYMENT_VERIFIED_LABEL,
    UPWORK_SEARCH_JOBS_URL,
    UPWORK_SEARCH_RESULTS_READY,
    UPWORK_SORT_LABEL,
)

logger = logging.getLogger("inercia.scraper.filter_scraper")

LAST_SCRAPED_UPWORK_ID_KEY: str = "last_scraped_upwork_id"
MAX_JOB_AGE_DAYS: int = 14
SCROLL_ROUNDS: int = 8
NO_RESULTS_MARKERS: tuple[str, ...] = (
    "no jobs found",
    "no results found",
    "try removing some filters",
)


@dataclass(frozen=True)
class FilteredJobCard:
    upwork_id: str
    title: str
    url: str
    description: str
    posted_age_text: str
    connects_required: int
    proposals_count_text: str = ""
    client_payment_verified: bool = False
    job_type: str = "hourly"


def _safe_text_selector(template: str, text: str) -> str:
    escaped = text.replace("\\", "\\\\").replace("'", "\\'")
    return template.format(text=escaped)


def _build_search_url(query: str) -> str:
    params = {
        "sort": "recency",
        "page": "1",
        "per_page": "50",
    }
    cleaned_query = query.strip()
    if cleaned_query:
        params["q"] = cleaned_query
    return f"{UPWORK_SEARCH_JOBS_URL}?{urllib.parse.urlencode(params)}"


def _has_no_results_marker(text: str) -> bool:
    lowered = text.lower()
    return any(marker in lowered for marker in NO_RESULTS_MARKERS)


async def _click_text(page: object, text: str, timeout: int = 2_500) -> bool:
    for template in (UPWORK_BUTTON_BY_TEXT, UPWORK_LABEL_BY_TEXT):
        locator = page.locator(_safe_text_selector(template, text)).first
        try:
            if await locator.count() > 0:
                await locator.click(timeout=timeout)
                await asyncio.sleep(0.25)
                return True
        except Exception as exc:
            logger.debug("Click skipped for %s: %s", text, exc)
    return False


async def _check_label(page: object, text: str) -> bool:
    try:
        labelled = page.get_by_label(text, exact=False).first
        if await labelled.count() > 0:
            checked = await labelled.is_checked(timeout=1_500)
            if not checked:
                await labelled.check(timeout=2_500)
            await asyncio.sleep(0.2)
            return True
    except Exception as exc:
        logger.debug("Labelled checkbox skipped for %s: %s", text, exc)

    checkbox = page.locator(_safe_text_selector(UPWORK_CHECKBOX_BY_LABEL, text)).first
    try:
        if await checkbox.count() > 0:
            checked = await checkbox.is_checked(timeout=1_500)
            if not checked:
                await checkbox.check(timeout=2_500)
            await asyncio.sleep(0.2)
            return True
    except Exception as exc:
        logger.debug("Checkbox skipped for %s: %s", text, exc)
    return await _click_text(page, text)


async def _open_filter_group(page: object, label: str) -> None:
    await _click_text(page, label, timeout=1_500)


async def _fill_visible_inputs(page: object, selector: str, values: list[str]) -> None:
    inputs = page.locator(selector)
    value_index = 0
    for index in range(await inputs.count()):
        if value_index >= len(values):
            break
        if not values[value_index]:
            value_index += 1
            continue
        field = inputs.nth(index)
        try:
            if await field.is_visible(timeout=1_000):
                await field.fill(values[value_index], timeout=2_500)
                value_index += 1
        except Exception as exc:
            logger.debug("Filter input fill skipped: %s", exc)


async def _apply_required_filters(page: object) -> None:
    await _click_text(page, "Sort")
    await _click_text(page, UPWORK_SORT_LABEL)
    await _open_filter_group(page, "Client info")
    await _check_label(page, UPWORK_PAYMENT_VERIFIED_LABEL)


async def _apply_configured_filters(page: object, filters: UpworkSearchFilters) -> None:
    groups: tuple[tuple[str, list[str]], ...] = (
        ("Category", filters.categories),
        ("Experience level", filters.experience_levels),
        ("Job type", filters.job_types),
        ("Hours per week", filters.hours_per_week),
        ("Project length", filters.project_lengths),
        ("Client history", filters.client_history),
        ("Number of proposals", filters.proposals),
    )
    for group, values in groups:
        if not values:
            continue
        await _open_filter_group(page, group)
        for value in values:
            await _check_label(page, value)
    if filters.client_location:
        await _open_filter_group(page, "Client location")
        await _fill_visible_inputs(page, UPWORK_FILTER_TEXT_INPUT, [filters.client_location])
        await _click_text(page, filters.client_location)
    if filters.budget_min is not None or filters.budget_max is not None:
        await _open_filter_group(page, "Fixed-price budget")
        await _fill_visible_inputs(
            page,
            UPWORK_FILTER_NUMBER_INPUT,
            [
                "" if filters.budget_min is None else str(filters.budget_min),
                "" if filters.budget_max is None else str(filters.budget_max),
            ],
        )
    if filters.hourly_rate_min is not None or filters.hourly_rate_max is not None:
        await _open_filter_group(page, "Hourly rate")
        await _fill_visible_inputs(
            page,
            UPWORK_FILTER_NUMBER_INPUT,
            [
                "" if filters.hourly_rate_min is None else str(filters.hourly_rate_min),
                "" if filters.hourly_rate_max is None else str(filters.hourly_rate_max),
            ],
        )


def _posting_age(text: str) -> Optional[timedelta]:
    lowered = text.lower()
    if any(marker in lowered for marker in ("just now", "moments ago", "today")):
        return timedelta()
    if "yesterday" in lowered:
        return timedelta(days=1)
    match = re.search(r"(\d+)\+?\s*(minute|minutes|min|mins|hour|hours|hr|hrs|day|days|week|weeks)\s+ago", lowered)
    if match is None:
        match = re.search(r"posted\s+(\d+)\+?\s*(minute|minutes|min|mins|hour|hours|hr|hrs|day|days|week|weeks)", lowered)
    if match is None:
        return None
    amount = int(match.group(1))
    unit = match.group(2)
    if unit.startswith("min"):
        return timedelta(minutes=amount)
    if unit.startswith(("hour", "hr")):
        return timedelta(hours=amount)
    if unit.startswith("day"):
        return timedelta(days=amount)
    if unit.startswith("week"):
        return timedelta(weeks=amount)
    return None


def _is_older_than_max_age(text: str, now: Optional[datetime] = None) -> bool:
    age = _posting_age(text)
    if age is None:
        return False
    return age > timedelta(days=MAX_JOB_AGE_DAYS)


def _extract_connects(text: str) -> int:
    patterns = (
        r"connects?\s*(?:required|needed|to\s+(?:submit|apply)|for\s+this\s+job)\D{0,40}(\d{1,3})",
        r"required\s+connects?\D{0,40}(\d{1,3})",
        r"(?:requires?|required)\D{0,40}(\d{1,3})\s+connects?",
        r"(\d{1,3})\s+connects?\s+(?:required|needed|to\s+(?:submit|apply)|for\s+this\s+job|are\s+required)",
    )
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match is not None:
            return int(match.group(1))
    return 0


def _extract_proposals_text(text: str) -> str:
    patterns = (
        r"proposals?\s*:\s*([^\n\r]+)",
        r"proposals?\s+(?:tier|count)\s*:\s*([^\n\r]+)",
        r"([<>]?\s*\d+\s*(?:to|-)\s*\d+|less than\s+\d+|\d+\+?)\s+proposals?",
    )
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match is not None:
            return re.sub(r"\s+", " ", match.group(1)).strip(" .")
    return ""


def _extract_job_type(text: str) -> str:
    lowered = text.lower()
    if "fixed-price" in lowered or "fixed price" in lowered:
        return "fixed"
    return "hourly"


def _contains_ignored_keyword(job: FilteredJobCard, ignored_keywords: list[str]) -> bool:
    haystack = f"{job.title}\n{job.description}".lower()
    return any(keyword.lower() in haystack for keyword in ignored_keywords)


def _absolute_upwork_url(href: str) -> str:
    return urllib.parse.urljoin("https://www.upwork.com", href)


async def _card_to_job(card: object) -> Optional[FilteredJobCard]:
    link = card.locator(UPWORK_JOB_CARD_TITLE_LINK).first
    href = ""
    title = ""
    if await link.count() > 0:
        href = (await link.get_attribute("href")) or ""
        try:
            title = (await link.inner_text(timeout=2_500)).strip()
        except Exception:
            title = ""
    if not href:
        data_uid = await card.get_attribute("data-ev-job-uid")
        if data_uid:
            href = f"/jobs/{data_uid}"
    if not href:
        return None
    url = _absolute_upwork_url(href)
    if not title:
        try:
            title_locator = card.locator("h2, [data-test='job-title'], .job-tile-title").first
            title = (await title_locator.inner_text(timeout=1_500)).strip()
        except Exception:
            title = "Untitled Upwork job"
    description = ""
    description_locator = card.locator(UPWORK_JOB_CARD_DESCRIPTION).first
    if await description_locator.count() > 0:
        try:
            description = (await description_locator.inner_text(timeout=1_500)).strip()
        except Exception:
            description = ""
    text = await card.inner_text(timeout=2_500)
    posted_age_text = ""
    age_locator = card.locator(UPWORK_JOB_CARD_AGE)
    for index in range(await age_locator.count()):
        candidate = (await age_locator.nth(index).inner_text(timeout=1_000)).strip()
        if _posting_age(candidate) is not None or "yesterday" in candidate.lower():
            posted_age_text = candidate
            break
    if not posted_age_text:
        posted_age_text = text
    proposals_count_text = ""
    proposals_locator = card.locator(UPWORK_JOB_CARD_PROPOSALS).first
    if await proposals_locator.count() > 0:
        try:
            proposals_count_text = _extract_proposals_text(await proposals_locator.inner_text(timeout=1_500))
        except Exception:
            proposals_count_text = ""
    if not proposals_count_text:
        proposals_count_text = _extract_proposals_text(text)
    return FilteredJobCard(
        upwork_id=extract_upwork_id(url),
        title=title,
        url=url,
        description=description,
        posted_age_text=posted_age_text,
        connects_required=_extract_connects(text),
        proposals_count_text=proposals_count_text,
        client_payment_verified="payment verified" in text.lower(),
        job_type=_extract_job_type(text),
    )


async def _ensure_authenticated_search_page(page: object) -> None:
    await ensure_upwork_authenticated_page(page, "Upwork search")


async def _wait_for_search_results(page: object) -> bool:
    try:
        await page.wait_for_selector(UPWORK_SEARCH_RESULTS_READY, timeout=NAV_TIMEOUT_MS)
        return True
    except Exception as exc:
        await _ensure_authenticated_search_page(page)
        body_text = await page_body_text(page)
        if _has_no_results_marker(body_text):
            logger.info("Upwork search returned no results for the configured query and filters")
            return False
        raise RuntimeError(
            "Upwork search result cards were not found; selectors may need maintenance"
        ) from exc


async def discover_filtered_jobs(
    query: str = "",
    db_path: Optional[Path] = None,
    user_data_dir: Optional[Path] = None,
    filters: Optional[UpworkSearchFilters] = None,
) -> list[FilteredJobCard]:
    settings = get_settings(db_path=db_path)
    selected_filters = filters or settings.upwork_search_filters
    profile_dir = user_data_dir or settings.upwork_session_dir
    last_scraped_upwork_id = get_session_value(LAST_SCRAPED_UPWORK_ID_KEY, db_path)
    ignored_keywords = get_blacklist_keywords(db_path)

    async def _discover_once(headless: bool) -> list[FilteredJobCard]:
        jobs: list[FilteredJobCard] = []
        seen: set[str] = set()
        stop_scan = False
        async with persistent_upwork_session(user_data_dir=profile_dir, headless=headless) as context:
            page = await context.new_page()
            await block_heavy_resources(page)
            try:
                search_url = _build_search_url(query)
                response = await page.goto(search_url, wait_until="domcontentloaded", timeout=NAV_TIMEOUT_MS)
                if response is not None and response.status >= 400:
                    raise RuntimeError(f"Upwork returned HTTP {response.status} for {search_url}")
                await _ensure_authenticated_search_page(page)
                await _apply_required_filters(page)
                await _apply_configured_filters(page, selected_filters)
                if not await _wait_for_search_results(page):
                    return jobs

                for _ in range(SCROLL_ROUNDS):
                    cards = page.locator(UPWORK_JOB_CARD)
                    count = await cards.count()
                    for index in range(count):
                        card = await _card_to_job(cards.nth(index))
                        if card is None or card.upwork_id in seen:
                            continue
                        seen.add(card.upwork_id)
                        if card.upwork_id == last_scraped_upwork_id or get_job_by_upwork_id(card.upwork_id, db_path):
                            stop_scan = True
                            break
                        if _is_older_than_max_age(card.posted_age_text):
                            continue
                        if selected_filters.max_connects and card.connects_required > selected_filters.max_connects:
                            continue
                        if _contains_ignored_keyword(card, ignored_keywords):
                            logger.info("Ignored Upwork job by keyword | upwork_id=%s | title=%s", card.upwork_id, card.title)
                            continue
                        jobs.append(card)
                    if stop_scan:
                        break
                    await page.mouse.wheel(0, 1800)
                    await asyncio.sleep(1.0)
            finally:
                await page.close()
        return jobs

    jobs = await _discover_once(headless=True)

    logger.info("Discovered %d filtered Upwork jobs", len(jobs))
    return jobs


__all__ = [
    "FilteredJobCard",
    "LAST_SCRAPED_UPWORK_ID_KEY",
    "MAX_JOB_AGE_DAYS",
    "SCROLL_ROUNDS",
    "UpworkAuthenticationError",
    "discover_filtered_jobs",
]

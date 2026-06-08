from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

from inercia.applicator.session import open_persistent_upwork_session
from inercia.scraper.engine import NAV_TIMEOUT_MS, block_heavy_resources

logger = logging.getLogger("inercia.applicator.auth")

UPWORK_SESSION_PROBE_URL: str = "https://www.upwork.com/nx/find-work/"
UPWORK_AUTHENTICATED_URL_PATTERNS: tuple[str, ...] = (
    "upwork.com/nx/find-work",
    "upwork.com/ab/find-work",
    "upwork.com/nx/search",
    "upwork.com/freelancer/dashboard",
    "upwork.com/ab/jobs/search",
    "upwork.com/nx/jobs",
    "upwork.com/ab/proposals",
    "upwork.com/nx/proposals",
    "upwork.com/messages",
    "upwork.com/freelancers/settings",
)
UPWORK_IN_PROGRESS_URL_FRAGMENTS: tuple[str, ...] = (
    "account-security",
    "login",
    "signup",
    "create-profile",
    "complete-profile",
    "google/callback",
    "apple/callback",
    "/oauth",
    "/sso/",
    "accounts.google.com",
    "appleid.apple.com",
)
UPWORK_LOGIN_RESPONSE_MARKERS: tuple[str, ...] = (
    "account-security/login",
    "/login",
    "log in to upwork",
    "sign in to upwork",
    "login with",
    "please log in",
)


@dataclass(frozen=True)
class UpworkAuthStatus:
    authenticated: bool
    message: str
    current_url: str = ""


def is_upwork_login_url(url: str) -> bool:
    lowered = url.lower()
    return any(fragment in lowered for fragment in UPWORK_IN_PROGRESS_URL_FRAGMENTS)


def is_upwork_authenticated_url(url: str) -> bool:
    lowered = url.lower()
    return any(pattern in lowered for pattern in UPWORK_AUTHENTICATED_URL_PATTERNS)


def contains_login_marker(text: str) -> bool:
    lowered = text.lower()
    return any(marker in lowered for marker in UPWORK_LOGIN_RESPONSE_MARKERS)


def _profile_lock_message(exc: Exception) -> str | None:
    text = str(exc).lower()
    if "lock" in text or "another browser" in text or "process singleton" in text:
        return "Upwork session profile is already in use. Close the login or scraping browser and try again."
    return None


async def verify_upwork_session(profile_dir: Path, timeout_ms: int = NAV_TIMEOUT_MS) -> UpworkAuthStatus:
    if not profile_dir.exists():
        return UpworkAuthStatus(False, "Upwork session profile does not exist", "")

    session = None
    page = None
    try:
        session = await open_persistent_upwork_session(
            user_data_dir=profile_dir,
            headless=True,
        )
        page = await session.context.new_page()
        await block_heavy_resources(page)
        response = await page.goto(UPWORK_SESSION_PROBE_URL, wait_until="domcontentloaded", timeout=timeout_ms)
        current_url = page.url
        if response is not None and response.status >= 400:
            return UpworkAuthStatus(False, f"Upwork session probe returned HTTP {response.status}", current_url)
        if is_upwork_login_url(current_url):
            return UpworkAuthStatus(False, "Upwork redirected to login", current_url)
        try:
            body_text = await page.locator("body").inner_text(timeout=5_000)
        except Exception:
            body_text = ""
        if contains_login_marker(f"{current_url}\n{body_text}"):
            return UpworkAuthStatus(False, "Upwork session probe reached a login page", current_url)
        if is_upwork_authenticated_url(current_url):
            return UpworkAuthStatus(True, "Upwork session verified", current_url)
        return UpworkAuthStatus(False, "Could not confirm authenticated Upwork session", current_url)
    except Exception as exc:
        lock_message = _profile_lock_message(exc)
        if lock_message is not None:
            return UpworkAuthStatus(False, lock_message, "")
        logger.warning("Upwork session probe failed: %s", exc)
        return UpworkAuthStatus(False, f"Upwork session probe failed: {exc}", "")
    finally:
        if page is not None:
            try:
                await page.close()
            except Exception:
                logger.debug("Upwork auth probe page close failed", exc_info=True)
        if session is not None:
            try:
                await session.context.close()
                await session.playwright.stop()
            except Exception:
                logger.debug("Upwork auth probe session close failed", exc_info=True)


__all__ = [
    "UPWORK_AUTHENTICATED_URL_PATTERNS",
    "UPWORK_IN_PROGRESS_URL_FRAGMENTS",
    "UPWORK_LOGIN_RESPONSE_MARKERS",
    "UPWORK_SESSION_PROBE_URL",
    "UpworkAuthStatus",
    "contains_login_marker",
    "is_upwork_authenticated_url",
    "is_upwork_login_url",
    "verify_upwork_session",
]

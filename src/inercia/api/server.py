from __future__ import annotations

import asyncio
import json
import logging
import os
import signal
import sqlite3
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable
from dataclasses import asdict
from pathlib import Path
from typing import Any, Optional

from inercia.api.protocol import (
    ProposalReadyData,
    connects_balance,
    error_message,
    jobs_list,
    login_browser_closed,
    login_browser_opened,
    login_status,
    proposal_ready,
    process_done,
    process_progress,
    scrape_done,
    scrape_error,
    scrape_progress,
    scheduler_status,
    settings_state,
    stats_update,
)
from inercia.applicator.apply_flow import ApplyPayload, close_apply_session, prepare_application
from inercia.config import get_settings
from inercia.db.manager import (
    count_submitted_today,
    get_connection,
    get_connects_spent_today,
    get_proposal,
    get_session_value,
    init_db,
    log_connects,
    set_session_value,
    update_job_status,
    update_proposal_status,
)
from inercia.scraper.selectors import UPWORK_APPLY_URL_PREFIX

logger = logging.getLogger("inercia.api.server")

DEFAULT_CONNECTS_TOTAL: int = 211
POLL_INTERVAL_S: float = 2.0
LOGIN_STATUS_POLL_INTERVAL_S: float = 2.0
LOGIN_AUTH_GRACE_S: float = 10.0
LOGIN_AUTH_STABILITY_S: float = LOGIN_STATUS_POLL_INTERVAL_S * 2
LOGIN_PROFILE_FLUSH_GRACE_S: float = 3.0
SESSION_KEY_CONNECTS_TOTAL: str = "connects_total"
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
UPWORK_SESSION_COOKIE_NAMES: frozenset[str] = frozenset(
    {
        "oauth2_global_js_token",
        "XSRF-TOKEN",
        "visitor_id",
    }
)
UPWORK_LOGIN_RESPONSE_MARKERS: tuple[str, ...] = (
    "account-security/login",
    "/login",
    "log in to upwork",
    "sign in to upwork",
    "login with",
    "please log in",
)
HandlerAfterSend = Optional[Callable[[], None]]
HandlerResult = tuple[dict[str, Any], HandlerAfterSend]
_login_process: Optional[subprocess.Popen[Any]] = None
_login_profile_dir: Optional[Path] = None
_login_poll_task: Optional[asyncio.Task[None]] = None
_login_auth_confirmed_at: float = 0.0
_login_auth_confirmed_url: str = ""
_login_status_state: dict[str, Any] = {
    "browser_open": False,
    "authenticated": False,
    "message": "Not checked",
    "current_url": "",
}
_scheduler_task: Optional[asyncio.Task[None]] = None
_scheduler_stop_event: Optional[asyncio.Event] = None
_scheduler_next_run_at: float = 0.0
_scheduler_error_seq: int = 0
_scheduler_last_error: Optional[str] = None
_background_tasks: set[asyncio.Task[None]] = set()


def _get_connects_total(db_path: Optional[Path] = None) -> int:
    """Read total connects from DB sessions table, fallback to default."""
    stored = get_session_value(SESSION_KEY_CONNECTS_TOTAL, db_path)
    if stored is not None:
        try:
            return int(stored)
        except ValueError:
            pass
    return DEFAULT_CONNECTS_TOTAL


def set_connects_total(total: int, db_path: Optional[Path] = None) -> None:
    """Update the stored total connects balance."""
    set_session_value(SESSION_KEY_CONNECTS_TOTAL, str(total), db_path)


def _json_loads_object(value: Optional[str]) -> dict[str, str]:
    if value is None or not value.strip():
        return {}
    parsed = json.loads(value)
    if not isinstance(parsed, dict):
        return {}
    return {str(key): str(item) for key, item in parsed.items()}


def _bool_from_override(value: str, fallback: bool) -> bool:
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    return fallback


def _settings_payload(db_path: Optional[Path]) -> dict[str, Any]:
    settings = get_settings(db_path=db_path)
    return {
        "gemini_api_key": settings.gemini_api_key,
        "opencode_api_key": settings.opencode_api_key,
        "opencode_base_url": settings.opencode_base_url,
        "opencode_copywriter_model": settings.opencode_copywriter_model,
        "opencode_user_agent": settings.opencode_user_agent,
        "daily_proposal_cap": settings.daily_proposal_cap,
        "floor_hourly_rate": settings.floor_hourly_rate,
        "floor_fixed_rate": settings.floor_fixed_rate,
        "allow_upwork_network": settings.allow_upwork_network,
        "db_path": str(settings.db_path),
        "upwork_session_dir": str(settings.upwork_session_dir),
        "ws_port": settings.ws_port,
        "login_debug_port": settings.login_debug_port,
        "has_gemini_key": bool(settings.gemini_api_key),
        "has_opencode_key": bool(settings.opencode_api_key),
        "scheduler_interval_min_minutes": settings.scheduler_interval_min_minutes,
        "scheduler_interval_max_minutes": settings.scheduler_interval_max_minutes,
        "blacklist_keywords": settings.blacklist_keywords,
        "upwork_search_filters": asdict(settings.upwork_search_filters),
        "portfolio_attachments": [str(path) for path in settings.portfolio_attachments],
    }


def _login_browser_pids(profile_dir: Path) -> list[int]:
    if not sys.platform.startswith("linux"):
        if (
            _login_process is not None
            and _login_process.poll() is None
            and (_login_profile_dir is None or _login_profile_dir == profile_dir)
            and _login_process.pid is not None
        ):
            return [int(_login_process.pid)]
        return []

    needle = f"--user-data-dir={profile_dir}"
    pids: list[int] = []
    proc_root = Path("/proc")
    if not proc_root.exists():
        return []
    for proc_dir in proc_root.iterdir():
        if not proc_dir.name.isdecimal():
            continue
        try:
            cmdline = proc_dir.joinpath("cmdline").read_bytes().decode(errors="ignore")
        except OSError:
            continue
        if needle in cmdline:
            pids.append(int(proc_dir.name))
    return pids


def _login_debug_pages(debug_port: int) -> list[dict[str, Any]]:
    request = urllib.request.Request(
        f"http://127.0.0.1:{debug_port}/json",
        headers={"Accept": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=1.5) as response:
            parsed = json.loads(response.read().decode("utf-8", errors="replace"))
    except (OSError, urllib.error.URLError, json.JSONDecodeError):
        return []
    if not isinstance(parsed, list):
        return []
    return [item for item in parsed if isinstance(item, dict)]


def _set_login_status_state(status: dict[str, Any]) -> None:
    _login_status_state.clear()
    _login_status_state.update(
        {
            "browser_open": bool(status.get("browser_open", False)),
            "authenticated": bool(status.get("authenticated", False)),
            "message": str(status.get("message", "")),
            "current_url": str(status.get("current_url", "")),
        }
    )


def _login_status_from_debug(profile_dir: Path, debug_port: int) -> dict[str, Any]:
    browser_open = bool(_login_browser_pids(profile_dir))
    current_url = ""
    authenticated = False
    message = "Waiting for login..." if browser_open else "Login browser closed"
    for page in _login_debug_pages(debug_port):
        url = str(page.get("url", ""))
        if not url or url.startswith("devtools://"):
            continue
        current_url = url
        lowered = url.lower()
        if any(fragment in lowered for fragment in UPWORK_IN_PROGRESS_URL_FRAGMENTS):
            message = "Waiting for login..."
            continue
        if any(pattern in lowered for pattern in UPWORK_AUTHENTICATED_URL_PATTERNS):
            authenticated = True
            message = "Login detected. Confirming session..."
            break
    return {
        "browser_open": browser_open,
        "authenticated": authenticated,
        "message": message,
        "current_url": current_url,
    }


def _chrome_cookie_now() -> int:
    return int((time.time() + 11_644_473_600) * 1_000_000)


def _upwork_cookie_session_status(profile_dir: Path) -> tuple[bool, str]:
    cookies_path = profile_dir / "Default" / "Cookies"
    if not cookies_path.exists():
        return False, "No stored Upwork session cookies found"
    quoted_path = urllib.parse.quote(str(cookies_path), safe="/:")
    cookie_names = tuple(UPWORK_SESSION_COOKIE_NAMES)
    placeholders = ", ".join("?" for _ in cookie_names)
    sql = f"""
        SELECT
          COUNT(*) AS upwork_count,
          SUM(
            CASE
              WHEN name IN ({placeholders})
                OR lower(name) LIKE '%oauth%'
                OR lower(name) LIKE '%token%'
                OR lower(name) LIKE '%session%'
              THEN 1
              ELSE 0
            END
          ) AS session_count
        FROM cookies
        WHERE (host_key = ? OR host_key LIKE ?)
          AND (expires_utc = 0 OR expires_utc > ?)
    """
    try:
        with sqlite3.connect(f"file:{quoted_path}?mode=ro", uri=True, timeout=1.0) as conn:
            row = conn.execute(sql, (*cookie_names, "upwork.com", "%.upwork.com", _chrome_cookie_now())).fetchone()
    except sqlite3.Error as exc:
        logger.warning("Could not read Upwork cookie store: %s", exc)
        return False, "Could not read stored Upwork session cookies"
    upwork_count = int(row[0]) if row is not None and row[0] is not None else 0
    session_count = int(row[1]) if row is not None and row[1] is not None else 0
    if session_count > 0:
        return True, "Stored Upwork session cookies found"
    if upwork_count > 0:
        return True, "Stored Upwork cookies found"
    return False, "No stored Upwork session cookies found"


def _read_upwork_cookie_header(profile_dir: Path) -> tuple[Optional[str], str]:
    cookies_path = profile_dir / "Default" / "Cookies"
    if not cookies_path.exists():
        return None, "No stored Upwork session cookies found"
    quoted_path = urllib.parse.quote(str(cookies_path), safe="/:")
    sql = """
        SELECT name, value
        FROM cookies
        WHERE (host_key = ? OR host_key LIKE ?)
          AND (expires_utc = 0 OR expires_utc > ?)
          AND value != ''
        ORDER BY name;
    """
    try:
        with sqlite3.connect(f"file:{quoted_path}?mode=ro", uri=True, timeout=1.0) as conn:
            rows = conn.execute(sql, ("upwork.com", "%.upwork.com", _chrome_cookie_now())).fetchall()
    except sqlite3.Error as exc:
        logger.warning("Could not read Upwork cookie store for HTTP probe: %s", exc)
        return None, "Could not read stored Upwork session cookies"
    cookies = [
        f"{urllib.parse.quote(str(name), safe='')}={urllib.parse.quote(str(value), safe='')}"
        for name, value in rows
        if str(name) and str(value)
    ]
    if not cookies:
        return None, "No readable Upwork session cookies found"
    return "; ".join(cookies), "Readable Upwork session cookies found"


def _verify_upwork_http_session(profile_dir: Path) -> tuple[bool, str]:
    cookie_header, cookie_message = _read_upwork_cookie_header(profile_dir)
    if cookie_header is None:
        return False, cookie_message
    request = urllib.request.Request(
        UPWORK_SESSION_PROBE_URL,
        headers={
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Cookie": cookie_header,
            "User-Agent": (
                "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
            ),
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=8.0) as response:
            status = int(response.status)
            final_url = response.geturl().lower()
            body = response.read(128_000).decode("utf-8", errors="replace").lower()
    except urllib.error.HTTPError as exc:
        return False, f"Upwork session probe returned HTTP {exc.code}"
    except (OSError, urllib.error.URLError) as exc:
        return False, f"Upwork session probe failed: {exc}"
    if status != 200:
        return False, f"Upwork session probe returned HTTP {status}"
    if any(marker in final_url or marker in body for marker in UPWORK_LOGIN_RESPONSE_MARKERS):
        return False, "Upwork session probe reached a login page"
    return True, "Upwork session verified"


def _cookie_login_status_payload(profile_dir: Path) -> dict[str, Any]:
    authenticated, message = _upwork_cookie_session_status(profile_dir)
    return {
        "browser_open": False,
        "authenticated": authenticated,
        "message": message,
        "current_url": "",
    }


def _login_status_payload(db_path: Optional[Path]) -> dict[str, Any]:
    settings = get_settings(db_path=db_path)
    profile_dir = _login_profile_dir or settings.upwork_session_dir
    if not _login_browser_pids(profile_dir):
        return _cookie_login_status_payload(settings.upwork_session_dir)
    return _login_status_from_debug(profile_dir, settings.login_debug_port)


def _scheduler_status_payload() -> dict[str, Any]:
    running = _scheduler_task is not None and not _scheduler_task.done()
    next_run_in_seconds = 0
    if running and _scheduler_next_run_at > 0:
        next_run_in_seconds = max(0, int(_scheduler_next_run_at - time.monotonic()))
    return {"running": running, "next_run_in_seconds": next_run_in_seconds}


async def _scheduler_status_callback(wait_seconds: int) -> None:
    global _scheduler_next_run_at
    _scheduler_next_run_at = time.monotonic() + wait_seconds


async def _scheduler_error_callback(message: str) -> None:
    global _scheduler_error_seq, _scheduler_last_error
    _scheduler_error_seq += 1
    _scheduler_last_error = message


async def _run_scheduler(db_path: Optional[Path], stop_event: asyncio.Event) -> None:
    from inercia.core.scheduler import run_scheduler_loop

    global _scheduler_next_run_at
    _scheduler_next_run_at = 0.0
    try:
        await run_scheduler_loop(
            db_path=db_path,
            stop_event=stop_event,
            status_callback=_scheduler_status_callback,
            error_callback=_scheduler_error_callback,
        )
    finally:
        _scheduler_next_run_at = 0.0


async def _terminate_login_browser(profile_dir: Path) -> None:
    pids = _login_browser_pids(profile_dir)
    for pid in pids:
        try:
            os.kill(pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
    if pids:
        await asyncio.sleep(1)
    for pid in _login_browser_pids(profile_dir):
        try:
            os.kill(pid, signal.SIGKILL)
        except ProcessLookupError:
            pass


async def _close_login_browser_process(profile_dir: Path) -> None:
    global _login_process, _login_profile_dir
    await _terminate_login_browser(profile_dir)
    if _login_process is not None and _login_process.poll() is None:
        try:
            _login_process.terminate()
            await asyncio.to_thread(_login_process.wait, 5)
        except subprocess.TimeoutExpired:
            _login_process.kill()
            await asyncio.to_thread(_login_process.wait)
    await asyncio.sleep(LOGIN_PROFILE_FLUSH_GRACE_S)
    _login_process = None
    _login_profile_dir = None


async def _stop_login_poll_task() -> None:
    global _login_poll_task
    task = _login_poll_task
    if task is not None and not task.done() and task is not asyncio.current_task():
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
    _login_poll_task = None


async def _send_background_json(websocket: Any, message: dict[str, Any], label: str) -> None:
    try:
        await _send_json(websocket, message)
    except Exception as exc:
        logger.debug("%s push skipped: %s", label, exc)


def _track_background_task(task: asyncio.Task[None]) -> None:
    _background_tasks.add(task)

    def _discard(done_task: asyncio.Task[None]) -> None:
        _background_tasks.discard(done_task)
        try:
            done_task.result()
        except asyncio.CancelledError:
            pass
        except Exception:
            logger.exception("Background task failed")

    task.add_done_callback(_discard)


async def _poll_login_status(profile_dir: Path, debug_port: int) -> None:
    global _login_auth_confirmed_at, _login_auth_confirmed_url, _login_process, _login_profile_dir, _login_poll_task
    try:
        while True:
            status = _login_status_from_debug(profile_dir, debug_port)
            if status["authenticated"]:
                current_url = str(status.get("current_url", ""))
                now = time.monotonic()
                if _login_auth_confirmed_url != current_url or _login_auth_confirmed_at <= 0:
                    _login_auth_confirmed_url = current_url
                    _login_auth_confirmed_at = now
                    status["message"] = "Login detected. Confirming session..."
                    _set_login_status_state(status)
                    await asyncio.sleep(LOGIN_STATUS_POLL_INTERVAL_S)
                    continue
                if now - _login_auth_confirmed_at < LOGIN_AUTH_STABILITY_S:
                    status["message"] = "Login detected. Confirming session..."
                    _set_login_status_state(status)
                    await asyncio.sleep(LOGIN_STATUS_POLL_INTERVAL_S)
                    continue
                status["message"] = "Login detected. Verifying session cookies..."
                _set_login_status_state(status)
                await asyncio.sleep(LOGIN_AUTH_GRACE_S)
                verified, message = await asyncio.to_thread(_verify_upwork_http_session, profile_dir)
                if verified:
                    status["message"] = "Login confirmed. Closing browser..."
                    _set_login_status_state(status)
                    await _close_login_browser_process(profile_dir)
                    _login_auth_confirmed_at = 0.0
                    _login_auth_confirmed_url = ""
                    _set_login_status_state(
                        {
                            "browser_open": False,
                            "authenticated": True,
                            "message": "Session confirmed ✓",
                            "current_url": "",
                        }
                    )
                    return
                _login_auth_confirmed_at = 0.0
                _login_auth_confirmed_url = ""
                status["authenticated"] = False
                status["message"] = f"{message}. Continue login in the browser..."
                _set_login_status_state(status)
                await asyncio.sleep(LOGIN_STATUS_POLL_INTERVAL_S)
                continue
            _login_auth_confirmed_at = 0.0
            _login_auth_confirmed_url = ""
            if not status["browser_open"]:
                await asyncio.sleep(LOGIN_PROFILE_FLUSH_GRACE_S)
                _login_process = None
                _login_profile_dir = None
                _set_login_status_state(
                    {
                        "browser_open": False,
                        "authenticated": False,
                        "message": "Login failed - browser was closed before login completed",
                        "current_url": "",
                    }
                )
                return
            _set_login_status_state(status)
            await asyncio.sleep(LOGIN_STATUS_POLL_INTERVAL_S)
    except asyncio.CancelledError:
        raise
    finally:
        _login_auth_confirmed_at = 0.0
        _login_auth_confirmed_url = ""
        if _login_poll_task is asyncio.current_task():
            _login_poll_task = None


def _row_to_proposal_ready(row: sqlite3.Row) -> ProposalReadyData:
    return {
        "proposal_id": int(row["proposal_id"]),
        "job_id": int(row["job_id"]),
        "upwork_id": str(row["upwork_id"]),
        "title": str(row["title"]),
        "client_country": row["client_country"],
        "roi_score": float(row["roi_score"]),
        "connects_cost": int(row["connects_cost"]),
        "bid_rate": float(row["bid_rate"]),
        "bid_type": str(row["bid_type"]),
        "cover_letter": str(row["cover_letter"]),
        "screening_answers": _json_loads_object(row["screening_answers"]),
        "cv_pdf_path": row["cv_pdf_path"],
        "status": str(row["proposal_status"]),
    }


def list_ready_proposals(db_path: Optional[Path] = None) -> list[ProposalReadyData]:
    sql = """
        SELECT
            proposals.id AS proposal_id,
            proposals.job_id,
            proposals.cover_letter,
            proposals.screening_answers,
            proposals.bid_rate,
            proposals.bid_type,
            proposals.cv_pdf_path,
            proposals.connects_cost,
            proposals.roi_score,
            proposals.status AS proposal_status,
            jobs.upwork_id,
            jobs.title,
            jobs.client_country
        FROM proposals
        JOIN jobs ON jobs.id = proposals.job_id
        WHERE proposals.status = 'pending'
          AND jobs.status = 'ready'
        ORDER BY proposals.created_at DESC;
    """
    with get_connection(db_path) as conn:
        rows = conn.execute(sql).fetchall()
    return [_row_to_proposal_ready(row) for row in rows]


def _proposal_with_job(proposal_id: int, db_path: Optional[Path] = None) -> Optional[sqlite3.Row]:
    sql = """
        SELECT
            proposals.*,
            jobs.id AS joined_job_id,
            jobs.upwork_id,
            jobs.title
        FROM proposals
        JOIN jobs ON jobs.id = proposals.job_id
        WHERE proposals.id = ?
        LIMIT 1;
    """
    with get_connection(db_path) as conn:
        return conn.execute(sql, (proposal_id,)).fetchone()


def _update_proposal_cover_letter(proposal_id: int, cover_letter: str, db_path: Optional[Path] = None) -> None:
    with get_connection(db_path) as conn:
        conn.execute("UPDATE proposals SET cover_letter = ? WHERE id = ?;", (cover_letter, proposal_id))


def _count_today_by_status(status: str, db_path: Optional[Path] = None) -> int:
    timestamp_column = "submitted_at" if status == "submitted" else "created_at"
    sql = f"""
        SELECT COUNT(*) AS count
        FROM proposals
        WHERE status = ?
          AND date({timestamp_column}) = date('now');
    """
    with get_connection(db_path) as conn:
        row = conn.execute(sql, (status,)).fetchone()
    return int(row["count"])


def build_stats(db_path: Optional[Path] = None) -> dict[str, Any]:
    spent_today = get_connects_spent_today(db_path)
    total = _get_connects_total(db_path)
    return stats_update(
        {
            "today_submitted": _count_today_by_status("submitted", db_path),
            "today_approved": _count_today_by_status("approved", db_path),
            "today_rejected": _count_today_by_status("rejected", db_path),
            "connects_remaining": max(total - spent_today, 0),
            "connects_spent_today": spent_today,
        }
    )


async def _send_json(websocket: Any, message: dict[str, Any]) -> None:
    await websocket.send(json.dumps(message))


async def _send_initial_state(websocket: Any, db_path: Optional[Path]) -> None:
    total = await asyncio.to_thread(_get_connects_total, db_path)
    spent_today = await asyncio.to_thread(get_connects_spent_today, db_path)
    await _send_json(websocket, connects_balance(total, spent_today))
    await _send_json(websocket, await asyncio.to_thread(build_stats, db_path))
    await _send_json(websocket, settings_state(await asyncio.to_thread(_settings_payload, db_path)))
    ready = await asyncio.to_thread(list_ready_proposals, db_path)
    for proposal in ready:
        await _send_json(websocket, proposal_ready(proposal))
    await _send_json(websocket, scheduler_status(_scheduler_status_payload()))
    current_login_status = _login_status_payload(db_path)
    if current_login_status["browser_open"] and _login_status_state.get("browser_open"):
        current_login_status = dict(_login_status_state)
    else:
        _set_login_status_state(current_login_status)
    await _send_json(websocket, login_status(current_login_status))


async def _handle_user_approved(
    proposal_id: int,
    cover_letter: Optional[str],
    db_path: Optional[Path],
) -> HandlerResult:
    row = await asyncio.to_thread(_proposal_with_job, proposal_id, db_path)
    if row is None:
        return error_message(f"Proposal not found: {proposal_id}"), None

    settings = get_settings(db_path=db_path)
    submitted_today = await asyncio.to_thread(count_submitted_today, db_path)
    if submitted_today >= settings.daily_proposal_cap:
        return error_message(f"Daily proposal cap reached: {submitted_today}/{settings.daily_proposal_cap}"), None

    user_data_dir = settings.upwork_session_dir
    if _login_browser_pids(user_data_dir):
        return error_message("Finish Upwork login, wait for /nx/find-work/, then close the login browser before approving"), None

    selected_cover_letter = str(row["cover_letter"])
    if cover_letter is not None:
        selected_cover_letter = cover_letter
        await asyncio.to_thread(_update_proposal_cover_letter, proposal_id, selected_cover_letter, db_path)

    payload = ApplyPayload(
        apply_url=f"{UPWORK_APPLY_URL_PREFIX}{row['upwork_id']}",
        bid_rate=float(row["bid_rate"]),
        cover_letter=selected_cover_letter,
        screening_answers=_json_loads_object(row["screening_answers"]),
        cv_pdf_path=Path(str(row["cv_pdf_path"])) if row["cv_pdf_path"] else None,
        portfolio_attachment_paths=settings.portfolio_attachments,
    )
    result, _session = await prepare_application(
        payload,
        proposal_id=proposal_id,
        user_data_dir=user_data_dir,
        allow_network=settings.allow_upwork_network,
    )
    if not result.stopped_before_submit:
        await close_apply_session(proposal_id)
        return error_message("Apply flow did not stop before Submit; approval aborted"), None

    await asyncio.to_thread(update_proposal_status, proposal_id, "approved", db_path)
    await asyncio.to_thread(update_job_status, int(row["joined_job_id"]), "approved", db_path)
    await asyncio.to_thread(log_connects, int(row["connects_cost"]), "spent", proposal_id, db_path)

    logger.info(
        "User approved proposal | id=%d | live_apply=%s",
        proposal_id,
        settings.allow_upwork_network,
    )
    return {
        "type": "user_approved_ack",
        "data": {"proposal_id": proposal_id, "prepared": True, "live_apply": settings.allow_upwork_network},
    }, None


async def _handle_user_rejected(proposal_id: int, reason: Optional[str], db_path: Optional[Path]) -> HandlerResult:
    proposal = await asyncio.to_thread(get_proposal, proposal_id, db_path)
    if proposal is None:
        return error_message(f"Proposal not found: {proposal_id}"), None
    await close_apply_session(proposal_id)
    await asyncio.to_thread(update_proposal_status, proposal_id, "rejected", db_path)
    await asyncio.to_thread(update_job_status, int(proposal["job_id"]), "rejected", db_path)
    if reason:
        with get_connection(db_path) as conn:
            conn.execute("UPDATE proposals SET critic_notes = ? WHERE id = ?;", (reason, proposal_id))
    logger.info("User rejected proposal | id=%d | reason=%s", proposal_id, reason)
    return {"type": "user_rejected_ack", "data": {"proposal_id": proposal_id}}, None


async def _handle_confirm_submitted(proposal_id: int, db_path: Optional[Path]) -> HandlerResult:
    row = await asyncio.to_thread(_proposal_with_job, proposal_id, db_path)
    if row is None:
        return error_message(f"Proposal not found: {proposal_id}"), None
    await close_apply_session(proposal_id)
    await asyncio.to_thread(update_proposal_status, proposal_id, "submitted", db_path)
    await asyncio.to_thread(update_job_status, int(row["joined_job_id"]), "submitted", db_path)
    logger.info("User confirmed proposal submitted | id=%d", proposal_id)
    return {"type": "confirm_submitted_ack", "data": {"proposal_id": proposal_id}}, None


async def _handle_run_scrape(payload: dict[str, Any], websocket: Any, db_path: Optional[Path]) -> HandlerResult:
    from inercia.core.orchestrator import scrape_query

    query = str(payload.get("query", "")).strip()
    settings = get_settings(db_path=db_path)
    allow_network_value = payload.get("allow_network")
    allow_network = settings.allow_upwork_network if allow_network_value is None else bool(allow_network_value)

    async def _run() -> None:
        label = query or "configured filters"
        try:
            summary = await scrape_query(query=query, db_path=db_path, allow_network=allow_network)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            message = f"Scrape failed: {exc}"
            logger.exception("Scrape failed | query=%s | allow_network=%s", label, allow_network)
            await _send_background_json(
                websocket,
                scrape_error({"message": message, "query": label, "source": "run_scrape"}),
                "scrape_error",
            )
            await _send_background_json(
                websocket,
                scrape_done({"query": label, "queued": 0, "processed": 0, "inserted": 0, "failed": 1}),
                "scrape_done",
            )
        else:
            await _send_background_json(
                websocket,
                scrape_done(
                    {
                        "query": label,
                        "queued": int(summary["queued"]),
                        "processed": int(summary["processed"]),
                        "inserted": int(summary["inserted"]),
                        "failed": int(summary["failed"]),
                    }
                ),
                "scrape_done",
            )
        finally:
            await _send_background_json(websocket, await asyncio.to_thread(build_stats, db_path), "stats_update")

    return scrape_progress({"phase": "starting", "queued": 0, "processed": 0, "failed": 0}), lambda: _track_background_task(
        asyncio.create_task(_run())
    )


async def _handle_run_process(payload: dict[str, Any], websocket: Any, db_path: Optional[Path]) -> HandlerResult:
    from inercia.ai.graph import process_unprocessed_jobs

    limit = int(payload.get("limit", 20))

    async def _run() -> None:
        try:
            summary = await process_unprocessed_jobs(limit=limit, db_path=db_path)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            message = f"Process failed: {exc}"
            logger.exception("Process failed | limit=%d", limit)
            await _send_background_json(websocket, error_message(message), "process_error")
            await _send_background_json(
                websocket,
                process_done({"processed": 0, "ready": 0, "blacklisted": 0, "failed": 1, "cap_reached": False}),
                "process_done",
            )
        else:
            await _send_background_json(
                websocket,
                process_done(
                    {
                        "processed": int(summary["processed"]),
                        "ready": int(summary["ready"]),
                        "blacklisted": int(summary["blacklisted"]),
                        "failed": int(summary["failed"]),
                        "cap_reached": bool(summary["cap_reached"]),
                    }
                ),
                "process_done",
            )
        finally:
            await _send_background_json(websocket, await asyncio.to_thread(build_stats, db_path), "stats_update")

    return process_progress({"processed": 0, "ready": 0, "blacklisted": 0, "failed": 0}), lambda: _track_background_task(
        asyncio.create_task(_run())
    )


async def _handle_open_upwork_login(payload: dict[str, Any], websocket: Any, db_path: Optional[Path]) -> HandlerResult:
    del payload, websocket
    global _login_process, _login_profile_dir, _login_poll_task
    settings = get_settings(db_path=db_path)
    profile_dir = settings.upwork_session_dir
    if _login_browser_pids(profile_dir):
        return error_message("Login browser already open"), None
    await _stop_login_poll_task()
    profile_dir.mkdir(parents=True, exist_ok=True)
    browser_bin = shutil.which("chromium") or shutil.which("google-chrome") or shutil.which("google-chrome-stable")
    if browser_bin is None:
        return error_message("No system Chromium or Chrome binary found"), None
    _login_process = await asyncio.to_thread(
        subprocess.Popen,
        [
            browser_bin,
            f"--user-data-dir={profile_dir}",
            f"--remote-debugging-port={settings.login_debug_port}",
            "--remote-debugging-address=127.0.0.1",
            "--new-window",
            "https://www.upwork.com/ab/account-security/login",
        ],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    _login_profile_dir = profile_dir
    _set_login_status_state(
        {
            "browser_open": True,
            "authenticated": False,
            "message": "Waiting for login...",
            "current_url": "",
        }
    )
    _login_poll_task = asyncio.create_task(_poll_login_status(profile_dir, settings.login_debug_port))
    return login_browser_opened(), None


async def _handle_close_upwork_login(payload: dict[str, Any], websocket: Any, db_path: Optional[Path]) -> HandlerResult:
    del payload, websocket
    global _login_process, _login_profile_dir
    settings = get_settings(db_path=db_path)
    profile_dir = _login_profile_dir or settings.upwork_session_dir
    await _stop_login_poll_task()
    if not _login_browser_pids(profile_dir):
        _login_process = None
        _login_profile_dir = None
        _set_login_status_state(
            {
                "browser_open": False,
                "authenticated": False,
                "message": "Login browser was already closed",
                "current_url": "",
            }
        )
        return login_browser_closed(authenticated=False, message="Login browser was already closed"), None
    await _close_login_browser_process(profile_dir)
    _set_login_status_state(
        {
            "browser_open": False,
            "authenticated": False,
            "message": "Login canceled",
            "current_url": "",
        }
    )
    return login_browser_closed(authenticated=False, message="Login canceled"), None


async def _handle_check_upwork_session(payload: dict[str, Any], websocket: Any, db_path: Optional[Path]) -> HandlerResult:
    del payload, websocket
    settings = get_settings(db_path=db_path)
    if _login_browser_pids(settings.upwork_session_dir):
        status = _login_status_from_debug(settings.upwork_session_dir, settings.login_debug_port)
        _set_login_status_state(status)
        return login_status(status), None
    status = _cookie_login_status_payload(settings.upwork_session_dir)
    _set_login_status_state(status)
    return login_status(status), None


def _list_all_jobs(limit: int, db_path: Optional[Path]) -> list[sqlite3.Row]:
    sql = "SELECT * FROM jobs ORDER BY scraped_at DESC LIMIT ?;"
    with get_connection(db_path) as conn:
        return conn.execute(sql, (limit,)).fetchall()


async def _handle_get_jobs(payload: dict[str, Any], websocket: Any, db_path: Optional[Path]) -> HandlerResult:
    del websocket
    from inercia.db.manager import list_jobs_by_status

    status = payload.get("status")
    limit = int(payload.get("limit", 50))
    if status:
        rows = await asyncio.to_thread(list_jobs_by_status, str(status), limit, db_path)
    else:
        rows = await asyncio.to_thread(_list_all_jobs, limit, db_path)
    jobs = [
        {
            "id": int(row["id"]),
            "upwork_id": str(row["upwork_id"]),
            "title": str(row["title"]),
            "job_type": str(row["job_type"]),
            "roi_score": float(row["roi_score"]) if row["roi_score"] is not None else None,
            "status": str(row["status"]),
            "scraped_at": str(row["scraped_at"]),
        }
        for row in rows
    ]
    return jobs_list(jobs), None


async def _handle_get_settings(payload: dict[str, Any], websocket: Any, db_path: Optional[Path]) -> HandlerResult:
    del payload, websocket
    return settings_state(await asyncio.to_thread(_settings_payload, db_path)), None


async def _handle_set_setting(payload: dict[str, Any], websocket: Any, db_path: Optional[Path]) -> HandlerResult:
    del websocket
    key = str(payload.get("key", ""))
    value = str(payload.get("value", ""))
    allowed_keys = {
        "GEMINI_API_KEY",
        "OPENCODE_API_KEY",
        "OPENCODE_BASE_URL",
        "OPENCODE_COPYWRITER_MODEL",
        "OPENCODE_USER_AGENT",
        "DAILY_PROPOSAL_CAP",
        "FLOOR_HOURLY_RATE",
        "FLOOR_FIXED_RATE",
        "ALLOW_UPWORK_NETWORK",
        "LOGIN_DEBUG_PORT",
        "SCHEDULER_INTERVAL_MIN_MINUTES",
        "SCHEDULER_INTERVAL_MAX_MINUTES",
        "blacklist_keywords",
        "upwork_search_filters",
        "portfolio_attachments",
    }
    if key not in allowed_keys:
        return error_message(f"Unsupported setting: {key}"), None
    await asyncio.to_thread(set_session_value, key, value, db_path)
    return await _handle_get_settings({}, None, db_path)


async def _handle_set_connects_total(payload: dict[str, Any], websocket: Any, db_path: Optional[Path]) -> HandlerResult:
    del websocket
    total = int(payload.get("total", 0))
    await asyncio.to_thread(set_connects_total, total, db_path)
    spent_today = await asyncio.to_thread(get_connects_spent_today, db_path)
    return connects_balance(total, spent_today), None


async def _handle_start_scheduler(payload: dict[str, Any], websocket: Any, db_path: Optional[Path]) -> HandlerResult:
    del payload, websocket
    global _scheduler_task, _scheduler_stop_event
    if _scheduler_task is not None and not _scheduler_task.done():
        return scheduler_status(_scheduler_status_payload()), None
    _scheduler_stop_event = asyncio.Event()
    _scheduler_task = asyncio.create_task(_run_scheduler(db_path, _scheduler_stop_event))
    return scheduler_status(_scheduler_status_payload()), None


async def _handle_stop_scheduler(payload: dict[str, Any], websocket: Any, db_path: Optional[Path]) -> HandlerResult:
    del payload, websocket, db_path
    global _scheduler_task, _scheduler_stop_event, _scheduler_next_run_at
    if _scheduler_stop_event is not None:
        _scheduler_stop_event.set()
    if _scheduler_task is not None and not _scheduler_task.done():
        _scheduler_task.cancel()
        await asyncio.gather(_scheduler_task, return_exceptions=True)
    _scheduler_task = None
    _scheduler_stop_event = None
    _scheduler_next_run_at = 0.0
    return scheduler_status(_scheduler_status_payload()), None


async def _handle_message(message: str, websocket: Any, db_path: Optional[Path]) -> HandlerResult:
    try:
        payload = json.loads(message)
    except json.JSONDecodeError:
        return error_message("Invalid JSON message"), None
    try:
        message_type = payload.get("type")
        if message_type == "user_approved":
            cover_letter = payload.get("cover_letter") if "cover_letter" in payload else None
            return await _handle_user_approved(
                int(payload["proposal_id"]),
                str(cover_letter) if cover_letter is not None else None,
                db_path,
            )
        if message_type == "user_rejected":
            reason = payload.get("reason")
            return await _handle_user_rejected(
                int(payload["proposal_id"]),
                str(reason) if reason is not None else None,
                db_path,
            )
        if message_type == "confirm_submitted":
            return await _handle_confirm_submitted(int(payload["proposal_id"]), db_path)
        if message_type == "run_scrape":
            return await _handle_run_scrape(payload, websocket, db_path)
        if message_type == "run_process":
            return await _handle_run_process(payload, websocket, db_path)
        if message_type == "open_upwork_login":
            return await _handle_open_upwork_login(payload, websocket, db_path)
        if message_type == "close_upwork_login":
            return await _handle_close_upwork_login(payload, websocket, db_path)
        if message_type == "check_upwork_session":
            return await _handle_check_upwork_session(payload, websocket, db_path)
        if message_type == "get_jobs":
            return await _handle_get_jobs(payload, websocket, db_path)
        if message_type == "get_settings":
            return await _handle_get_settings(payload, websocket, db_path)
        if message_type == "set_setting":
            return await _handle_set_setting(payload, websocket, db_path)
        if message_type == "set_connects_total":
            return await _handle_set_connects_total(payload, websocket, db_path)
        if message_type == "start_scheduler":
            return await _handle_start_scheduler(payload, websocket, db_path)
        if message_type == "stop_scheduler":
            return await _handle_stop_scheduler(payload, websocket, db_path)
        return error_message(f"Unsupported message type: {message_type}"), None
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        logger.exception("Message handler failed")
        return error_message(f"Request failed: {exc}"), None


async def _poll_ready(websocket: Any, db_path: Optional[Path]) -> None:
    sent: set[int] = set()
    last_scheduler_error_seq = _scheduler_error_seq
    while True:
        if _scheduler_last_error is not None and _scheduler_error_seq != last_scheduler_error_seq:
            await _send_json(
                websocket,
                scrape_error(
                    {
                        "message": _scheduler_last_error,
                        "query": "configured filters",
                        "source": "scheduler",
                    }
                ),
            )
            last_scheduler_error_seq = _scheduler_error_seq
        ready = await asyncio.to_thread(list_ready_proposals, db_path)
        for proposal in ready:
            proposal_id = proposal["proposal_id"]
            if proposal_id not in sent:
                await _send_json(websocket, proposal_ready(proposal))
                sent.add(proposal_id)
        await _send_json(websocket, await asyncio.to_thread(build_stats, db_path))
        await _send_json(websocket, scheduler_status(_scheduler_status_payload()))
        await _send_json(websocket, login_status(dict(_login_status_state)))
        await asyncio.sleep(POLL_INTERVAL_S)


async def _client_handler(websocket: Any, db_path: Optional[Path]) -> None:
    await _send_initial_state(websocket, db_path)
    poller = asyncio.create_task(_poll_ready(websocket, db_path))
    try:
        async for message in websocket:
            try:
                response, after_send = await _handle_message(str(message), websocket, db_path)
                await _send_json(websocket, response)
                if after_send is not None:
                    after_send()
                await _send_json(websocket, await asyncio.to_thread(build_stats, db_path))
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.exception("Client message processing failed")
                await _send_json(websocket, error_message(f"Request failed: {exc}"))
    finally:
        poller.cancel()
        await asyncio.gather(poller, return_exceptions=True)


async def serve(db_path: Optional[Path] = None, host: str = "127.0.0.1", port: Optional[int] = None) -> None:
    from websockets.asyncio.server import serve as websocket_serve

    settings = get_settings(db_path=db_path)
    selected_port = port or settings.ws_port
    await asyncio.to_thread(init_db, db_path or settings.db_path)
    session_authenticated, session_message = await asyncio.to_thread(
        _upwork_cookie_session_status,
        settings.upwork_session_dir,
    )
    logger.info(
        "Upwork session cookie status | authenticated=%s | message=%s",
        session_authenticated,
        session_message,
    )
    async with websocket_serve(lambda websocket: _client_handler(websocket, db_path or settings.db_path), host, selected_port):
        logger.info("WebSocket API listening on ws://%s:%d", host, selected_port)
        await asyncio.Future()


__all__ = ["DEFAULT_CONNECTS_TOTAL", "build_stats", "list_ready_proposals", "serve", "set_connects_total"]

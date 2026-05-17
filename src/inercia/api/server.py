from __future__ import annotations

import asyncio
import json
import logging
import os
import signal
import sqlite3
import shutil
import subprocess
from pathlib import Path
from typing import Any, Optional

from inercia.api.protocol import (
    ProposalReadyData,
    connects_balance,
    error_message,
    jobs_list,
    login_browser_closed,
    login_browser_opened,
    proposal_ready,
    process_done,
    process_progress,
    scrape_done,
    scrape_progress,
    settings_state,
    stats_update,
)
from inercia.applicator.apply_flow import ApplyPayload, prepare_application
from inercia.config import get_settings
from inercia.db.manager import (
    count_submitted_today,
    get_connection,
    get_connects_spent_today,
    get_proposal,
    get_runtime_overrides,
    get_session_value,
    init_db,
    set_session_value,
    update_job_status,
    update_proposal_status,
)
from inercia.scraper.selectors import UPWORK_APPLY_URL_PREFIX

logger = logging.getLogger("inercia.api.server")

DEFAULT_CONNECTS_TOTAL: int = 211
POLL_INTERVAL_S: float = 2.0
SESSION_KEY_CONNECTS_TOTAL: str = "connects_total"
_login_process: Optional[subprocess.Popen[Any]] = None
_login_profile_dir: Optional[Path] = None


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


def _login_browser_pids(profile_dir: Path) -> list[int]:
    needle = f"--user-data-dir={profile_dir}"
    pids: list[int] = []
    for proc_dir in Path("/proc").iterdir():
        if not proc_dir.name.isdecimal():
            continue
        try:
            cmdline = proc_dir.joinpath("cmdline").read_bytes().decode(errors="ignore")
        except OSError:
            continue
        if needle in cmdline:
            pids.append(int(proc_dir.name))
    return pids


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
    ready = await asyncio.to_thread(list_ready_proposals, db_path)
    for proposal in ready:
        await _send_json(websocket, proposal_ready(proposal))


async def _handle_user_approved(proposal_id: int, db_path: Optional[Path]) -> dict[str, Any]:
    row = await asyncio.to_thread(_proposal_with_job, proposal_id, db_path)
    if row is None:
        return error_message(f"Proposal not found: {proposal_id}")

    settings = get_settings()
    submitted_today = await asyncio.to_thread(count_submitted_today, db_path)
    if submitted_today >= settings.daily_proposal_cap:
        return error_message(f"Daily proposal cap reached: {submitted_today}/{settings.daily_proposal_cap}")

    user_data_dir = settings.upwork_session_dir
    if _login_browser_pids(user_data_dir):
        return error_message("Finish Upwork login, wait for /nx/find-work/, then close the login browser before approving")

    payload = ApplyPayload(
        apply_url=f"{UPWORK_APPLY_URL_PREFIX}{row['upwork_id']}",
        bid_rate=float(row["bid_rate"]),
        cover_letter=str(row["cover_letter"]),
        screening_answers=_json_loads_object(row["screening_answers"]),
        cv_pdf_path=Path(str(row["cv_pdf_path"])) if row["cv_pdf_path"] else None,
    )
    result = await prepare_application(
        payload,
        user_data_dir=user_data_dir,
        allow_network=settings.allow_upwork_network,
    )
    if not result.stopped_before_submit:
        return error_message("Apply flow did not stop before Submit; approval aborted")

    await asyncio.to_thread(update_proposal_status, proposal_id, "submitted", db_path)
    await asyncio.to_thread(update_job_status, int(row["joined_job_id"]), "submitted", db_path)

    logger.info(
        "User approved proposal | id=%d | live_apply=%s",
        proposal_id,
        settings.allow_upwork_network,
    )
    return {
        "type": "user_approved_ack",
        "data": {"proposal_id": proposal_id, "prepared": True, "live_apply": settings.allow_upwork_network},
    }


async def _handle_user_rejected(proposal_id: int, reason: Optional[str], db_path: Optional[Path]) -> dict[str, Any]:
    proposal = await asyncio.to_thread(get_proposal, proposal_id, db_path)
    if proposal is None:
        return error_message(f"Proposal not found: {proposal_id}")
    await asyncio.to_thread(update_proposal_status, proposal_id, "rejected", db_path)
    await asyncio.to_thread(update_job_status, int(proposal["job_id"]), "rejected", db_path)
    if reason:
        with get_connection(db_path) as conn:
            conn.execute("UPDATE proposals SET critic_notes = ? WHERE id = ?;", (reason, proposal_id))
    logger.info("User rejected proposal | id=%d | reason=%s", proposal_id, reason)
    return {"type": "user_rejected_ack", "data": {"proposal_id": proposal_id}}


async def _handle_run_scrape(payload: dict[str, Any], websocket: Any, db_path: Optional[Path]) -> dict[str, Any]:
    from inercia.core.orchestrator import scrape_query

    query = str(payload.get("query", "")).strip()
    allow_network = bool(payload.get("allow_network", False))
    if not query:
        return error_message("query is required")
    await _send_json(
        websocket,
        scrape_progress({"phase": "starting", "queued": 0, "processed": 0, "failed": 0}),
    )
    summary = await scrape_query(query=query, db_path=db_path, allow_network=allow_network)
    return scrape_done(
        {
            "query": query,
            "queued": int(summary["queued"]),
            "processed": int(summary["processed"]),
            "inserted": int(summary["inserted"]),
            "failed": int(summary["failed"]),
        }
    )


async def _handle_run_process(payload: dict[str, Any], websocket: Any, db_path: Optional[Path]) -> dict[str, Any]:
    from inercia.ai.graph import process_unprocessed_jobs

    limit = int(payload.get("limit", 20))
    await _send_json(
        websocket,
        process_progress({"processed": 0, "ready": 0, "blacklisted": 0, "failed": 0}),
    )
    summary = await process_unprocessed_jobs(limit=limit, db_path=db_path)
    return process_done(
        {
            "processed": int(summary["processed"]),
            "ready": int(summary["ready"]),
            "blacklisted": int(summary["blacklisted"]),
            "failed": int(summary["failed"]),
            "cap_reached": bool(summary["cap_reached"]),
        }
    )


async def _handle_open_upwork_login(payload: dict[str, Any], websocket: Any, db_path: Optional[Path]) -> dict[str, Any]:
    del payload, websocket, db_path
    global _login_process, _login_profile_dir
    settings = get_settings()
    profile_dir = settings.upwork_session_dir
    if _login_browser_pids(profile_dir):
        return error_message("Login browser already open")
    profile_dir.mkdir(parents=True, exist_ok=True)
    browser_bin = shutil.which("chromium") or shutil.which("google-chrome") or shutil.which("google-chrome-stable")
    if browser_bin is None:
        return error_message("No system Chromium or Chrome binary found")
    _login_process = await asyncio.to_thread(
        subprocess.Popen,
        [
            browser_bin,
            f"--user-data-dir={profile_dir}",
            "--new-window",
            "https://www.upwork.com/ab/account-security/login",
        ],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    _login_profile_dir = profile_dir
    return login_browser_opened()


async def _handle_close_upwork_login(payload: dict[str, Any], websocket: Any, db_path: Optional[Path]) -> dict[str, Any]:
    del payload, websocket, db_path
    global _login_process, _login_profile_dir
    settings = get_settings()
    profile_dir = _login_profile_dir or settings.upwork_session_dir
    if not _login_browser_pids(profile_dir):
        _login_process = None
        _login_profile_dir = None
        return error_message("No login browser open")
    await _terminate_login_browser(profile_dir)
    if _login_process is not None and _login_process.poll() is None:
        try:
            _login_process.terminate()
            await asyncio.to_thread(_login_process.wait, 5)
        except subprocess.TimeoutExpired:
            _login_process.kill()
            await asyncio.to_thread(_login_process.wait)
    _login_process = None
    _login_profile_dir = None
    return login_browser_closed()


def _list_all_jobs(limit: int, db_path: Optional[Path]) -> list[sqlite3.Row]:
    sql = "SELECT * FROM jobs ORDER BY scraped_at DESC LIMIT ?;"
    with get_connection(db_path) as conn:
        return conn.execute(sql, (limit,)).fetchall()


async def _handle_get_jobs(payload: dict[str, Any], websocket: Any, db_path: Optional[Path]) -> dict[str, Any]:
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
    return jobs_list(jobs)


async def _handle_get_settings(payload: dict[str, Any], websocket: Any, db_path: Optional[Path]) -> dict[str, Any]:
    del payload, websocket
    settings = await asyncio.to_thread(get_settings)
    overrides = await asyncio.to_thread(get_runtime_overrides, db_path)
    daily_proposal_cap = settings.daily_proposal_cap
    floor_hourly_rate = settings.floor_hourly_rate
    floor_fixed_rate = settings.floor_fixed_rate
    allow_upwork_network = settings.allow_upwork_network
    if "DAILY_PROPOSAL_CAP" in overrides:
        daily_proposal_cap = int(overrides["DAILY_PROPOSAL_CAP"])
    if "FLOOR_HOURLY_RATE" in overrides:
        floor_hourly_rate = float(overrides["FLOOR_HOURLY_RATE"])
    if "FLOOR_FIXED_RATE" in overrides:
        floor_fixed_rate = float(overrides["FLOOR_FIXED_RATE"])
    if "ALLOW_UPWORK_NETWORK" in overrides:
        allow_upwork_network = _bool_from_override(overrides["ALLOW_UPWORK_NETWORK"], allow_upwork_network)
    return settings_state(
        {
            "daily_proposal_cap": daily_proposal_cap,
            "floor_hourly_rate": floor_hourly_rate,
            "floor_fixed_rate": floor_fixed_rate,
            "allow_upwork_network": allow_upwork_network,
            "db_path": str(settings.db_path),
            "upwork_session_dir": str(settings.upwork_session_dir),
            "ws_port": settings.ws_port,
            "has_gemini_key": bool(settings.gemini_api_key),
            "has_opencode_key": bool(settings.opencode_api_key),
        }
    )


async def _handle_set_setting(payload: dict[str, Any], websocket: Any, db_path: Optional[Path]) -> dict[str, Any]:
    del websocket
    key = str(payload.get("key", ""))
    value = str(payload.get("value", ""))
    allowed_keys = {
        "DAILY_PROPOSAL_CAP",
        "FLOOR_HOURLY_RATE",
        "FLOOR_FIXED_RATE",
        "ALLOW_UPWORK_NETWORK",
    }
    if key not in allowed_keys:
        return error_message(f"Unsupported setting: {key}")
    await asyncio.to_thread(set_session_value, key, value, db_path)
    return await _handle_get_settings({}, None, db_path)


async def _handle_set_connects_total(payload: dict[str, Any], websocket: Any, db_path: Optional[Path]) -> dict[str, Any]:
    del websocket
    total = int(payload.get("total", 0))
    await asyncio.to_thread(set_connects_total, total, db_path)
    spent_today = await asyncio.to_thread(get_connects_spent_today, db_path)
    return connects_balance(total, spent_today)


async def _handle_message(message: str, websocket: Any, db_path: Optional[Path]) -> dict[str, Any]:
    try:
        payload = json.loads(message)
    except json.JSONDecodeError:
        return error_message("Invalid JSON message")
    message_type = payload.get("type")
    if message_type == "user_approved":
        return await _handle_user_approved(int(payload["proposal_id"]), db_path)
    if message_type == "user_rejected":
        reason = payload.get("reason")
        return await _handle_user_rejected(
            int(payload["proposal_id"]),
            str(reason) if reason is not None else None,
            db_path,
        )
    if message_type == "run_scrape":
        return await _handle_run_scrape(payload, websocket, db_path)
    if message_type == "run_process":
        return await _handle_run_process(payload, websocket, db_path)
    if message_type == "open_upwork_login":
        return await _handle_open_upwork_login(payload, websocket, db_path)
    if message_type == "close_upwork_login":
        return await _handle_close_upwork_login(payload, websocket, db_path)
    if message_type == "get_jobs":
        return await _handle_get_jobs(payload, websocket, db_path)
    if message_type == "get_settings":
        return await _handle_get_settings(payload, websocket, db_path)
    if message_type == "set_setting":
        return await _handle_set_setting(payload, websocket, db_path)
    if message_type == "set_connects_total":
        return await _handle_set_connects_total(payload, websocket, db_path)
    return error_message(f"Unsupported message type: {message_type}")


async def _poll_ready(websocket: Any, db_path: Optional[Path]) -> None:
    sent: set[int] = set()
    while True:
        ready = await asyncio.to_thread(list_ready_proposals, db_path)
        for proposal in ready:
            proposal_id = proposal["proposal_id"]
            if proposal_id not in sent:
                await _send_json(websocket, proposal_ready(proposal))
                sent.add(proposal_id)
        await _send_json(websocket, await asyncio.to_thread(build_stats, db_path))
        await asyncio.sleep(POLL_INTERVAL_S)


async def _client_handler(websocket: Any, db_path: Optional[Path]) -> None:
    await _send_initial_state(websocket, db_path)
    poller = asyncio.create_task(_poll_ready(websocket, db_path))
    try:
        async for message in websocket:
            response = await _handle_message(str(message), websocket, db_path)
            await _send_json(websocket, response)
            await _send_json(websocket, await asyncio.to_thread(build_stats, db_path))
    finally:
        poller.cancel()
        await asyncio.gather(poller, return_exceptions=True)


async def serve(db_path: Optional[Path] = None, host: str = "127.0.0.1", port: Optional[int] = None) -> None:
    from websockets.asyncio.server import serve as websocket_serve

    settings = get_settings()
    selected_port = port or settings.ws_port
    await asyncio.to_thread(init_db, db_path or settings.db_path)
    async with websocket_serve(lambda websocket: _client_handler(websocket, db_path or settings.db_path), host, selected_port):
        logger.info("WebSocket API listening on ws://%s:%d", host, selected_port)
        await asyncio.Future()


__all__ = ["DEFAULT_CONNECTS_TOTAL", "build_stats", "list_ready_proposals", "serve", "set_connects_total"]

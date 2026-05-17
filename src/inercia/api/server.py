from __future__ import annotations

import asyncio
import json
import logging
import sqlite3
from pathlib import Path
from typing import Any, Optional

from inercia.api.protocol import (
    ProposalReadyData,
    connects_balance,
    error_message,
    proposal_ready,
    stats_update,
)
from inercia.applicator.apply_flow import ApplyPayload, prepare_application
from inercia.config import get_settings
from inercia.db.manager import (
    get_connection,
    get_connects_spent_today,
    get_proposal,
    get_session_value,
    init_db,
    count_submitted_today,
    set_session_value,
    update_job_status,
    update_proposal_status,
)
from inercia.scraper.selectors import UPWORK_APPLY_URL_PREFIX

logger = logging.getLogger("inercia.api.server")

DEFAULT_CONNECTS_TOTAL: int = 211
POLL_INTERVAL_S: float = 2.0
SESSION_KEY_CONNECTS_TOTAL: str = "connects_total"


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

    await asyncio.to_thread(update_proposal_status, proposal_id, "approved", db_path)
    await asyncio.to_thread(update_job_status, int(row["joined_job_id"]), "approved", db_path)

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


async def _handle_message(message: str, db_path: Optional[Path]) -> dict[str, Any]:
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
            response = await _handle_message(str(message), db_path)
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

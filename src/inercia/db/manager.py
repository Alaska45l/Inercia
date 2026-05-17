from __future__ import annotations

import contextlib
import json
import logging
import sqlite3
from collections.abc import Iterator, Mapping, Sequence
from pathlib import Path
from typing import Any, Optional

from inercia.config import get_settings

logger = logging.getLogger("inercia.db.manager")

SCHEMA_PATH = Path(__file__).with_name("schema.sql")

JOB_COLUMNS: tuple[str, ...] = (
    "upwork_id",
    "title",
    "description",
    "job_type",
    "budget_min",
    "budget_max",
    "hourly_rate_min",
    "hourly_rate_max",
    "duration",
    "experience_level",
    "skills",
    "client_country",
    "client_total_spent",
    "client_hire_rate",
    "client_reviews",
    "connects_required",
    "questions",
    "allows_attachments",
    "raw_markdown",
    "roi_score",
    "status",
)

PROPOSAL_COLUMNS: tuple[str, ...] = (
    "job_id",
    "cover_letter",
    "screening_answers",
    "bid_rate",
    "bid_type",
    "cv_pdf_path",
    "connects_cost",
    "roi_score",
    "critic_approved",
    "critic_notes",
    "status",
)

JOB_REQUIRED_COLUMNS: frozenset[str] = frozenset({"upwork_id", "title", "description", "job_type"})
PROPOSAL_REQUIRED_COLUMNS: frozenset[str] = frozenset(
    {"job_id", "cover_letter", "bid_rate", "bid_type", "connects_cost", "roi_score"}
)


def _db_path(db_path: Optional[Path] = None) -> Path:
    return db_path or get_settings().db_path


@contextlib.contextmanager
def get_connection(db_path: Optional[Path] = None) -> Iterator[sqlite3.Connection]:
    conn: Optional[sqlite3.Connection] = None
    try:
        conn = sqlite3.connect(
            database=str(_db_path(db_path)),
            detect_types=sqlite3.PARSE_DECLTYPES | sqlite3.PARSE_COLNAMES,
            timeout=30,
            check_same_thread=False,
        )
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON;")
        yield conn
        conn.commit()
    except sqlite3.Error as exc:
        if conn is not None:
            conn.rollback()
        logger.exception("SQLite error: %s", exc)
        raise
    finally:
        if conn is not None:
            conn.close()


def init_db(db_path: Optional[Path] = None) -> None:
    selected_db_path = _db_path(db_path)
    selected_db_path.parent.mkdir(parents=True, exist_ok=True)
    schema = SCHEMA_PATH.read_text(encoding="utf-8")
    with get_connection(selected_db_path) as conn:
        conn.executescript(schema)
    logger.info("Database initialized at %s", selected_db_path)


def _json_or_none(value: Any) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False)


def _normalize_job_values(job: Mapping[str, Any]) -> dict[str, Any]:
    missing = JOB_REQUIRED_COLUMNS.difference(job)
    if missing:
        raise ValueError(f"Missing required job field(s): {', '.join(sorted(missing))}")

    values = {column: job.get(column) for column in JOB_COLUMNS if column in job}
    if "skills" in values:
        values["skills"] = _json_or_none(values["skills"])
    if "questions" in values:
        values["questions"] = _json_or_none(values["questions"])
    return values


def _normalize_proposal_values(proposal: Mapping[str, Any]) -> dict[str, Any]:
    missing = PROPOSAL_REQUIRED_COLUMNS.difference(proposal)
    if missing:
        raise ValueError(f"Missing required proposal field(s): {', '.join(sorted(missing))}")

    values = {column: proposal.get(column) for column in PROPOSAL_COLUMNS if column in proposal}
    if "screening_answers" in values:
        values["screening_answers"] = _json_or_none(values["screening_answers"])
    return values


def upsert_job(job: Mapping[str, Any], db_path: Optional[Path] = None) -> int:
    values = _normalize_job_values(job)
    columns = tuple(values.keys())
    placeholders = ", ".join(f":{column}" for column in columns)
    column_names = ", ".join(columns)
    update_columns = [column for column in columns if column != "upwork_id"]
    update_clause = ", ".join(f"{column} = excluded.{column}" for column in update_columns)
    sql = f"""
        INSERT INTO jobs ({column_names})
        VALUES ({placeholders})
        ON CONFLICT(upwork_id) DO UPDATE SET {update_clause}
        RETURNING id;
    """
    with get_connection(db_path) as conn:
        row = conn.execute(sql, values).fetchone()
    job_id = int(row["id"])
    logger.info("Job upserted | upwork_id=%s | id=%d", values["upwork_id"], job_id)
    return job_id


def get_job(job_id: int, db_path: Optional[Path] = None) -> Optional[sqlite3.Row]:
    with get_connection(db_path) as conn:
        return conn.execute("SELECT * FROM jobs WHERE id = ? LIMIT 1;", (job_id,)).fetchone()


def get_job_by_upwork_id(upwork_id: str, db_path: Optional[Path] = None) -> Optional[sqlite3.Row]:
    with get_connection(db_path) as conn:
        return conn.execute(
            "SELECT * FROM jobs WHERE upwork_id = ? LIMIT 1;",
            (upwork_id,),
        ).fetchone()


def list_jobs_by_status(
    status: str,
    limit: int = 100,
    db_path: Optional[Path] = None,
) -> list[sqlite3.Row]:
    with get_connection(db_path) as conn:
        return conn.execute(
            "SELECT * FROM jobs WHERE status = ? ORDER BY scraped_at DESC LIMIT ?;",
            (status, limit),
        ).fetchall()


def update_job_status(job_id: int, status: str, db_path: Optional[Path] = None) -> None:
    with get_connection(db_path) as conn:
        conn.execute("UPDATE jobs SET status = ? WHERE id = ?;", (status, job_id))
    logger.debug("Job status updated | id=%d | status=%s", job_id, status)


def update_job_roi(job_id: int, roi_score: float, status: str = "scored", db_path: Optional[Path] = None) -> None:
    with get_connection(db_path) as conn:
        conn.execute(
            "UPDATE jobs SET roi_score = ?, status = ? WHERE id = ?;",
            (roi_score, status, job_id),
        )
    logger.debug("Job ROI updated | id=%d | roi=%f | status=%s", job_id, roi_score, status)


def create_proposal(proposal: Mapping[str, Any], db_path: Optional[Path] = None) -> int:
    values = _normalize_proposal_values(proposal)
    columns = tuple(values.keys())
    placeholders = ", ".join(f":{column}" for column in columns)
    column_names = ", ".join(columns)
    sql = f"""
        INSERT INTO proposals ({column_names})
        VALUES ({placeholders})
        RETURNING id;
    """
    with get_connection(db_path) as conn:
        row = conn.execute(sql, values).fetchone()
    proposal_id = int(row["id"])
    logger.info("Proposal created | id=%d | job_id=%s", proposal_id, values["job_id"])
    return proposal_id


def get_proposal(proposal_id: int, db_path: Optional[Path] = None) -> Optional[sqlite3.Row]:
    with get_connection(db_path) as conn:
        return conn.execute("SELECT * FROM proposals WHERE id = ? LIMIT 1;", (proposal_id,)).fetchone()


def list_proposals_by_status(
    status: str,
    limit: int = 100,
    db_path: Optional[Path] = None,
) -> list[sqlite3.Row]:
    with get_connection(db_path) as conn:
        return conn.execute(
            """
            SELECT proposals.*, jobs.title, jobs.upwork_id
            FROM proposals
            JOIN jobs ON jobs.id = proposals.job_id
            WHERE proposals.status = ?
            ORDER BY proposals.created_at DESC
            LIMIT ?;
            """,
            (status, limit),
        ).fetchall()


def update_proposal_status(
    proposal_id: int,
    status: str,
    db_path: Optional[Path] = None,
) -> None:
    submitted_sql = ""
    params: Sequence[Any]
    if status == "submitted":
        submitted_sql = ", submitted_at = strftime('%Y-%m-%dT%H:%M:%fZ', 'now')"
    sql = f"UPDATE proposals SET status = ?{submitted_sql} WHERE id = ?;"
    params = (status, proposal_id)
    with get_connection(db_path) as conn:
        conn.execute(sql, params)
    logger.debug("Proposal status updated | id=%d | status=%s", proposal_id, status)


def log_connects(
    amount: int,
    action: str,
    proposal_id: Optional[int] = None,
    db_path: Optional[Path] = None,
) -> int:
    sql = """
        INSERT INTO connects_log (proposal_id, amount, action)
        VALUES (?, ?, ?)
        RETURNING id;
    """
    with get_connection(db_path) as conn:
        row = conn.execute(sql, (proposal_id, amount, action)).fetchone()
    log_id = int(row["id"])
    logger.info("Connects logged | id=%d | amount=%d | action=%s", log_id, amount, action)
    return log_id


def count_submitted_today(db_path: Optional[Path] = None) -> int:
    sql = """
        SELECT COUNT(*) AS count
        FROM proposals
        WHERE status = 'submitted'
          AND date(submitted_at) = date('now');
    """
    with get_connection(db_path) as conn:
        row = conn.execute(sql).fetchone()
    return int(row["count"])


def get_connects_spent_today(db_path: Optional[Path] = None) -> int:
    sql = """
        SELECT COALESCE(SUM(amount), 0) AS total
        FROM connects_log
        WHERE action = 'spent'
          AND date(timestamp) = date('now');
    """
    with get_connection(db_path) as conn:
        row = conn.execute(sql).fetchone()
    return int(row["total"])


def set_session_value(key: str, value: str, db_path: Optional[Path] = None) -> None:
    sql = """
        INSERT INTO sessions (key, value)
        VALUES (?, ?)
        ON CONFLICT(key) DO UPDATE SET
            value = excluded.value,
            updated_at = strftime('%Y-%m-%dT%H:%M:%fZ', 'now');
    """
    with get_connection(db_path) as conn:
        conn.execute(sql, (key, value))


def get_session_value(key: str, db_path: Optional[Path] = None) -> Optional[str]:
    with get_connection(db_path) as conn:
        row = conn.execute("SELECT value FROM sessions WHERE key = ? LIMIT 1;", (key,)).fetchone()
    if row is None:
        return None
    return str(row["value"])


__all__ = [
    "create_proposal",
    "count_submitted_today",
    "get_connection",
    "get_connects_spent_today",
    "get_job",
    "get_job_by_upwork_id",
    "get_proposal",
    "get_session_value",
    "init_db",
    "list_jobs_by_status",
    "list_proposals_by_status",
    "log_connects",
    "set_session_value",
    "update_job_roi",
    "update_job_status",
    "update_proposal_status",
    "upsert_job",
]

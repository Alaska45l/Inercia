from __future__ import annotations

import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from inercia.db.manager import (
    SCHEMA_VERSION,
    create_proposal,
    get_connection,
    get_job,
    get_proposal,
    init_db,
    upsert_job,
    update_proposal_status,
)


def _base_job(upwork_id: str = "job-1") -> dict[str, object]:
    return {
        "upwork_id": upwork_id,
        "url": f"https://www.upwork.com/jobs/~{upwork_id}",
        "source": "upwork_search",
        "source_metadata": {"collector": "authenticated_search", "query": "python"},
        "posted_age_text": "Posted 1 hour ago",
        "title": "Python automation",
        "description": "Build a Playwright scraper",
        "job_type": "hourly",
        "client_payment_verified": 1,
        "connects_required": 4,
        "skills": ["Python", "Playwright"],
        "raw_markdown": "# Python automation",
        "status": "new",
    }


def _base_proposal(job_id: int, cover_letter: str = "First letter") -> dict[str, object]:
    return {
        "job_id": job_id,
        "cover_letter": cover_letter,
        "screening_answers": {"one": "answer"},
        "bid_rate": 75.0,
        "bid_type": "hourly",
        "connects_cost": 4,
        "roi_score": 80.0,
        "critic_approved": 1,
        "critic_notes": "",
        "status": "pending",
    }


class DatabaseMigrationTests(unittest.TestCase):
    def test_init_db_migrates_legacy_jobs_table_without_losing_rows(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "legacy.db"
            with sqlite3.connect(db_path) as conn:
                conn.execute(
                    """
                    CREATE TABLE jobs (
                        id              INTEGER PRIMARY KEY AUTOINCREMENT,
                        upwork_id       TEXT    NOT NULL UNIQUE,
                        title           TEXT    NOT NULL,
                        description     TEXT    NOT NULL,
                        job_type        TEXT    NOT NULL CHECK(job_type IN ('hourly', 'fixed')),
                        budget_min      REAL,
                        budget_max      REAL,
                        hourly_rate_min REAL,
                        hourly_rate_max REAL,
                        duration        TEXT,
                        experience_level TEXT,
                        skills          TEXT,
                        client_country  TEXT,
                        client_total_spent REAL DEFAULT 0,
                        client_hire_rate   REAL DEFAULT 0,
                        client_reviews     INTEGER DEFAULT 0,
                        connects_required  INTEGER DEFAULT 0,
                        questions       TEXT,
                        allows_attachments INTEGER DEFAULT 0,
                        raw_markdown    TEXT,
                        scraped_at      TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
                        roi_score       REAL,
                        status          TEXT NOT NULL DEFAULT 'new'
                    ) STRICT;
                    """
                )
                conn.execute(
                    """
                    INSERT INTO jobs (upwork_id, title, description, job_type, raw_markdown, status)
                    VALUES ('legacy-1', 'Legacy job', 'Existing row', 'hourly', '# Existing row', 'new');
                    """
                )
                conn.execute("PRAGMA user_version = 0;")

            init_db(db_path)

            with get_connection(db_path) as conn:
                columns = {str(row["name"]) for row in conn.execute("PRAGMA table_info(jobs);").fetchall()}
                row = conn.execute("SELECT * FROM jobs WHERE upwork_id = 'legacy-1';").fetchone()
                user_version = int(conn.execute("PRAGMA user_version;").fetchone()[0])

        self.assertGreaterEqual(user_version, SCHEMA_VERSION)
        self.assertIn("url", columns)
        self.assertIn("source_metadata", columns)
        self.assertIn("client_payment_verified", columns)
        self.assertIsNotNone(row)
        self.assertEqual(row["source"], "unknown")
        self.assertEqual(row["client_payment_verified"], 0)

    def test_job_metadata_round_trips_through_upsert(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "metadata.db"
            init_db(db_path)
            job_id = upsert_job(_base_job(), db_path)
            row = get_job(job_id, db_path)

        self.assertIsNotNone(row)
        assert row is not None
        self.assertEqual(row["url"], "https://www.upwork.com/jobs/~job-1")
        self.assertEqual(row["source"], "upwork_search")
        self.assertEqual(json.loads(row["source_metadata"])["query"], "python")
        self.assertEqual(json.loads(row["skills"]), ["Python", "Playwright"])
        self.assertEqual(row["client_payment_verified"], 1)

    def test_create_proposal_reuses_existing_active_proposals(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "proposals.db"
            init_db(db_path)
            job_id = upsert_job(_base_job(), db_path)

            first_id = create_proposal(_base_proposal(job_id, "First letter"), db_path)
            second_id = create_proposal(_base_proposal(job_id, "Updated letter"), db_path)
            pending_row = get_proposal(first_id, db_path)
            update_proposal_status(first_id, "approved", db_path)
            third_id = create_proposal(_base_proposal(job_id, "Do not replace approved"), db_path)
            approved_row = get_proposal(first_id, db_path)

            with get_connection(db_path) as conn:
                proposal_count = int(conn.execute("SELECT COUNT(*) FROM proposals;").fetchone()[0])

        self.assertEqual(first_id, second_id)
        self.assertEqual(first_id, third_id)
        self.assertEqual(proposal_count, 1)
        self.assertIsNotNone(pending_row)
        self.assertIsNotNone(approved_row)
        assert pending_row is not None
        assert approved_row is not None
        self.assertEqual(pending_row["cover_letter"], "Updated letter")
        self.assertEqual(approved_row["cover_letter"], "Updated letter")


if __name__ == "__main__":
    unittest.main()

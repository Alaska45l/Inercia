from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from inercia.ai.nodes.extractor import deterministic_extract
from inercia.ai.nodes.investor import score_job
from inercia.api.server import _settings_payload
from inercia.config import DEFAULT_BLACKLIST_KEYWORDS
from inercia.db.manager import init_db, set_session_value
from inercia.scraper.filter_scraper import (
    FilteredJobCard,
    _contains_ignored_keyword,
    _extract_connects,
    _extract_job_type,
    _is_older_than_max_age,
    _posting_age,
)


class ScraperParsingTests(unittest.TestCase):
    def test_extracts_connects_and_job_type(self) -> None:
        self.assertEqual(_extract_connects("Connects required: 12 Connects"), 12)
        self.assertEqual(_extract_connects("No connect cost shown"), 0)
        self.assertEqual(_extract_job_type("Fixed-price project $500"), "fixed")
        self.assertEqual(_extract_job_type("Hourly: $40-$60"), "hourly")

    def test_posting_age_filter(self) -> None:
        self.assertFalse(_is_older_than_max_age("Posted 2 hours ago"))
        self.assertFalse(_is_older_than_max_age("Posted 14 days ago"))
        self.assertTrue(_is_older_than_max_age("Posted 3 weeks ago"))
        self.assertIsNotNone(_posting_age("Posted 12 minutes ago"))

    def test_ignore_keywords_apply_to_collected_cards(self) -> None:
        job = FilteredJobCard(
            upwork_id="123",
            title="Need Wix landing page",
            url="https://www.upwork.com/jobs/~123",
            description="Small website update",
            posted_age_text="Posted 1 hour ago",
            connects_required=4,
        )
        self.assertTrue(_contains_ignored_keyword(job, list(DEFAULT_BLACKLIST_KEYWORDS)))


class PipelineFilteringTests(unittest.TestCase):
    def test_blacklist_keyword_sets_negative_roi(self) -> None:
        detail = deterministic_extract(
            "# Shopify automation\n\nBuild a Shopify theme customization.\n\n"
            "Job type: hourly\nHourly range: $50-$80/hr\nSkills: Python, Playwright\nConnects required: 4",
            upwork_id="blacklisted",
        )
        score = score_job(detail)
        self.assertTrue(score.blacklisted)
        self.assertEqual(score.score, -100)


class SettingsPayloadTests(unittest.TestCase):
    def test_settings_payload_redacts_secret_values(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "inercia.db"
            init_db(db_path)
            set_session_value("GEMINI_API_KEY", "secret-gemini", db_path)
            set_session_value("OPENCODE_API_KEY", "secret-opencode", db_path)

            payload = _settings_payload(db_path)

        self.assertEqual(payload["gemini_api_key"], "")
        self.assertEqual(payload["opencode_api_key"], "")
        self.assertTrue(payload["has_gemini_key"])
        self.assertTrue(payload["has_opencode_key"])


if __name__ == "__main__":
    unittest.main()

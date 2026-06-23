from __future__ import annotations

import tempfile
import unittest
import urllib.parse
from pathlib import Path
from unittest.mock import patch

from inercia.ai.nodes.extractor import deterministic_extract
from inercia.ai.nodes.investor import score_job
from inercia.api.server import _login_status_from_debug, _settings_payload
from inercia.applicator.apply_flow import build_upwork_apply_url
from inercia.config import DEFAULT_BLACKLIST_KEYWORDS
from inercia.db.manager import init_db, set_session_value
from inercia.scraper.feed import extract_upwork_id
from inercia.scraper.filter_scraper import (
    FilteredJobCard,
    _build_search_url,
    _contains_ignored_keyword,
    _extract_connects,
    _extract_job_type,
    _extract_proposals_text,
    _is_older_than_max_age,
    _posting_age,
)


class ScraperParsingTests(unittest.TestCase):
    def test_extracts_connects_and_job_type(self) -> None:
        self.assertEqual(_extract_connects("Connects required: 12 Connects"), 12)
        self.assertEqual(_extract_connects("Required Connects to submit a proposal: 16"), 16)
        self.assertEqual(_extract_connects("This job requires 8 Connects to apply."), 8)
        self.assertEqual(_extract_connects("Available Connects: 120"), 0)
        self.assertEqual(_extract_connects("No connect cost shown"), 0)
        self.assertEqual(_extract_job_type("Fixed-price project $500"), "fixed")
        self.assertEqual(_extract_job_type("Hourly: $40-$60"), "hourly")

    def test_extracts_proposal_tier_text(self) -> None:
        self.assertEqual(_extract_proposals_text("Proposals: 10 to 15"), "10 to 15")
        self.assertEqual(_extract_proposals_text("Less than 5 proposals"), "Less than 5")

    def test_builds_authenticated_search_url(self) -> None:
        url = _build_search_url("python playwright")
        parsed = urllib.parse.urlparse(url)
        query = urllib.parse.parse_qs(parsed.query)

        self.assertEqual(parsed.path, "/nx/search/jobs/")
        self.assertEqual(query["q"], ["python playwright"])
        self.assertEqual(query["sort"], ["recency"])
        self.assertEqual(query["per_page"], ["50"])

    def test_posting_age_filter(self) -> None:
        self.assertFalse(_is_older_than_max_age("Posted 2 hours ago"))
        self.assertFalse(_is_older_than_max_age("Posted 14 days ago"))
        self.assertTrue(_is_older_than_max_age("Posted 3 weeks ago"))
        self.assertIsNotNone(_posting_age("Posted 12 minutes ago"))
        self.assertEqual(_posting_age("Just now").total_seconds(), 0)

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

    def test_extracts_stable_upwork_id_from_slugged_url(self) -> None:
        url = (
            "https://www.upwork.com/jobs/Build-Playwright-Scraper_~012345abcdef/"
            "?referrer_url_path=/nx/search/jobs/"
        )
        self.assertEqual(extract_upwork_id(url), "~012345abcdef")
        self.assertEqual(
            extract_upwork_id("https://www.upwork.com/freelance-jobs/apply/1876543210"),
            "1876543210",
        )

    def test_builds_apply_url_from_original_job_url(self) -> None:
        job_url = (
            "https://www.upwork.com/jobs/Build-Playwright-Scraper_~012345abcdef/"
            "?referrer_url_path=/nx/search/jobs/"
        )
        self.assertEqual(
            build_upwork_apply_url("~012345abcdef", job_url),
            "https://www.upwork.com/freelance-jobs/apply/Build-Playwright-Scraper_~012345abcdef",
        )
        self.assertEqual(
            build_upwork_apply_url("~012345abcdef"),
            "https://www.upwork.com/freelance-jobs/apply/~012345abcdef",
        )


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

            payload = _settings_payload(db_path)

        self.assertEqual(payload["gemini_api_key"], "")
        self.assertTrue(payload["has_gemini_key"])


class LoginStatusTests(unittest.TestCase):
    def test_login_status_ignores_browser_internal_debug_pages(self) -> None:
        with (
            patch("inercia.api.server._login_browser_pids", return_value=[123]),
            patch(
                "inercia.api.server._login_debug_pages",
                return_value=[
                    {"type": "service_worker", "url": "https://www.upwork.com/ab/account-security/sw.js"},
                    {"type": "service_worker", "url": "chrome-extension://extension/background.js"},
                    {"type": "browser_ui", "url": "chrome://newtab/"},
                    {"type": "page", "url": "https://www.upwork.com/ab/account-security/login"},
                ],
            ),
        ):
            status = _login_status_from_debug(Path("."), 9742)

        self.assertTrue(status["browser_open"])
        self.assertFalse(status["authenticated"])
        self.assertEqual(status["current_url"], "https://www.upwork.com/ab/account-security/login")
        self.assertEqual(status["message"], "Waiting for login...")


if __name__ == "__main__":
    unittest.main()

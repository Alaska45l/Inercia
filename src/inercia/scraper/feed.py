from __future__ import annotations

import asyncio
import logging
import urllib.parse
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger("inercia.scraper.feed")

UPWORK_RSS_URL: str = "https://www.upwork.com/ab/feed/jobs/rss?q={query}"

MOCK_RSS_FEED: str = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>Upwork Jobs Feed</title>
    <item>
      <title>Python Playwright automation developer</title>
      <link>https://www.upwork.com/freelance-jobs/apply/1876543210</link>
      <description>Build an async browser automation workflow with Python, Playwright, and SQLite.</description>
      <guid>1876543210</guid>
    </item>
  </channel>
</rss>
"""


@dataclass(frozen=True)
class FeedJob:
    upwork_id: str
    title: str
    url: str
    description: str


class FeedDownloadError(RuntimeError):
    pass


def build_feed_url(query: str) -> str:
    encoded_query = urllib.parse.quote_plus(query.strip())
    return UPWORK_RSS_URL.format(query=encoded_query)


def _text(parent: ET.Element, child_name: str) -> str:
    child = parent.find(child_name)
    if child is None or child.text is None:
        return ""
    return child.text.strip()


def extract_upwork_id(url: str) -> str:
    parsed = urllib.parse.urlparse(url)
    parts = [part for part in parsed.path.split("/") if part]
    if parts:
        return parts[-1].strip()
    return url.rstrip("/").rsplit("/", 1)[-1]


def parse_rss(feed_xml: str) -> list[FeedJob]:
    root = ET.fromstring(feed_xml)
    jobs: list[FeedJob] = []
    for item in root.findall(".//item"):
        url = _text(item, "link")
        if not url:
            continue
        guid = _text(item, "guid")
        jobs.append(
            FeedJob(
                upwork_id=guid or extract_upwork_id(url),
                title=_text(item, "title") or "Untitled Upwork job",
                url=url,
                description=_text(item, "description"),
            )
        )
    return jobs


def parse_job_urls(feed_xml: str) -> list[str]:
    return [job.url for job in parse_rss(feed_xml)]


def _download_feed(query: str, timeout: float) -> str:
    url = build_feed_url(query)
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "Inercia/1.0.0 (+offline-first scraper)"},
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        raise FeedDownloadError(
            f"Upwork RSS request failed with HTTP {exc.code}: {exc.reason} ({url})"
        ) from exc
    except urllib.error.URLError as exc:
        raise FeedDownloadError(f"Upwork RSS request failed: {exc.reason} ({url})") from exc
    except OSError as exc:
        raise FeedDownloadError(f"Upwork RSS request failed: {exc} ({url})") from exc


async def fetch_feed_xml(
    query: str,
    feed_xml: Optional[str] = None,
    allow_network: bool = False,
    timeout: float = 20.0,
) -> str:
    if feed_xml is not None:
        return feed_xml
    if not allow_network:
        logger.info("Using offline RSS sample for query=%s", query)
        return MOCK_RSS_FEED
    return await asyncio.to_thread(_download_feed, query, timeout)


async def fetch_jobs(
    query: str,
    feed_xml: Optional[str] = None,
    allow_network: bool = False,
) -> list[FeedJob]:
    xml = await fetch_feed_xml(query=query, feed_xml=feed_xml, allow_network=allow_network)
    return parse_rss(xml)


async def fetch_job_urls(
    query: str,
    feed_xml: Optional[str] = None,
    allow_network: bool = False,
) -> list[str]:
    jobs = await fetch_jobs(query=query, feed_xml=feed_xml, allow_network=allow_network)
    return [job.url for job in jobs]


__all__ = [
    "FeedJob",
    "FeedDownloadError",
    "MOCK_RSS_FEED",
    "UPWORK_RSS_URL",
    "build_feed_url",
    "extract_upwork_id",
    "fetch_feed_xml",
    "fetch_jobs",
    "fetch_job_urls",
    "parse_job_urls",
    "parse_rss",
]

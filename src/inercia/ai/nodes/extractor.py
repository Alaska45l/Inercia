from __future__ import annotations

import logging
import re
from typing import Optional

from inercia.ai.llm import GEMINI_FLASH_MODEL, StructuredLLM
from inercia.ai.prompts import EXTRACTOR_SYSTEM_PROMPT
from inercia.ai.schemas import JobDetail

logger = logging.getLogger("inercia.ai.nodes.extractor")


def _first_match(pattern: str, text: str) -> Optional[str]:
    match = re.search(pattern, text, flags=re.IGNORECASE | re.MULTILINE)
    if match is None:
        return None
    return match.group(1).strip()


def _parse_money(value: Optional[str]) -> Optional[float]:
    if value is None:
        return None
    cleaned = re.sub(r"[^0-9.]", "", value)
    if not cleaned:
        return None
    return float(cleaned)


def _parse_float(value: Optional[str]) -> float:
    if value is None:
        return 0.0
    cleaned = value.strip().replace("%", "")
    if not cleaned:
        return 0.0
    parsed = float(cleaned)
    if parsed > 1:
        return parsed / 100
    return parsed


def _parse_int(value: Optional[str]) -> int:
    if value is None:
        return 0
    cleaned = re.sub(r"[^0-9]", "", value)
    if not cleaned:
        return 0
    return int(cleaned)


def _parse_title(raw_markdown: str, fallback_title: str) -> str:
    heading = _first_match(r"^#\s+(.+)$", raw_markdown)
    return heading or fallback_title or "Untitled Upwork job"


def _parse_skills(raw_markdown: str) -> list[str]:
    raw_skills = _first_match(r"^Skills:\s*(.+)$", raw_markdown)
    if raw_skills is None:
        return []
    return [skill.strip() for skill in raw_skills.split(",") if skill.strip()]


def _parse_questions(raw_markdown: str) -> list[str]:
    marker = re.search(r"Screening questions:\s*(.+)$", raw_markdown, flags=re.IGNORECASE | re.DOTALL)
    if marker is None:
        return []
    questions: list[str] = []
    for line in marker.group(1).splitlines():
        cleaned = line.strip().lstrip("-").strip()
        if cleaned:
            questions.append(cleaned)
    return questions


def deterministic_extract(
    raw_markdown: str,
    upwork_id: Optional[str] = None,
    fallback_title: str = "",
    fallback_description: str = "",
) -> JobDetail:
    title = _parse_title(raw_markdown, fallback_title)
    hourly_min = _parse_money(_first_match(r"Hourly range:\s*\$?([0-9.]+)", raw_markdown))
    hourly_max = _parse_money(_first_match(r"Hourly range:\s*\$?[0-9.]+\s*-\s*\$?([0-9.]+)", raw_markdown))
    budget_min = _parse_money(_first_match(r"Budget:\s*\$?([0-9.]+)", raw_markdown))
    budget_max = _parse_money(_first_match(r"Budget:\s*\$?[0-9.]+\s*-\s*\$?([0-9.]+)", raw_markdown))
    job_type_raw = (_first_match(r"Job type:\s*(hourly|fixed)", raw_markdown) or "hourly").lower()
    job_type = "fixed" if job_type_raw == "fixed" else "hourly"
    description_lines = [
        line.strip()
        for line in raw_markdown.splitlines()
        if line.strip() and not line.strip().startswith("#") and ":" not in line[:30]
    ]
    description = " ".join(description_lines[:3]) or fallback_description or title
    return JobDetail(
        upwork_id=upwork_id,
        title=title,
        description=description,
        job_type=job_type,
        budget_min=budget_min,
        budget_max=budget_max,
        hourly_rate_min=hourly_min,
        hourly_rate_max=hourly_max,
        duration=_first_match(r"^Duration:\s*(.+)$", raw_markdown),
        experience_level=_first_match(r"^Experience level:\s*(.+)$", raw_markdown),
        skills=_parse_skills(raw_markdown),
        client_country=_first_match(r"^Client country:\s*(.+)$", raw_markdown),
        client_total_spent=_parse_money(_first_match(r"^Client total spent:\s*(.+)$", raw_markdown)) or 0.0,
        client_hire_rate=_parse_float(_first_match(r"^Client hire rate:\s*(.+)$", raw_markdown)),
        client_reviews=_parse_int(_first_match(r"^Client reviews:\s*(.+)$", raw_markdown)),
        connects_required=_parse_int(_first_match(r"^Connects required:\s*(.+)$", raw_markdown)),
        questions=_parse_questions(raw_markdown),
        allows_attachments=bool(re.search(r"Allows attachments:\s*yes", raw_markdown, flags=re.IGNORECASE)),
        raw_markdown=raw_markdown,
    )


async def extract_job_detail(
    raw_markdown: str,
    upwork_id: Optional[str] = None,
    fallback_title: str = "",
    fallback_description: str = "",
) -> JobDetail:
    fallback = lambda: deterministic_extract(raw_markdown, upwork_id, fallback_title, fallback_description)
    llm = StructuredLLM[JobDetail]()
    user_prompt = f"Upwork job id: {upwork_id or ''}\n\nMarkdown:\n{raw_markdown}"
    detail = await llm.generate_structured(
        model=GEMINI_FLASH_MODEL,
        system_prompt=EXTRACTOR_SYSTEM_PROMPT,
        user_prompt=user_prompt,
        response_model=JobDetail,
        fallback_factory=fallback,
    )
    updates: dict[str, object] = {}
    if detail.upwork_id is None:
        updates["upwork_id"] = upwork_id
    if detail.raw_markdown is None:
        updates["raw_markdown"] = raw_markdown
    if updates:
        detail = detail.model_copy(update=updates)
    logger.info("Extracted job detail | upwork_id=%s | title=%s", detail.upwork_id, detail.title)
    return detail


__all__ = ["deterministic_extract", "extract_job_detail"]

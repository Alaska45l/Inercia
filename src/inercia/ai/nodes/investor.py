from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Optional

from inercia.ai.llm import GEMINI_FLASH_MODEL, StructuredLLM
from inercia.ai.prompts import INVESTOR_SYSTEM_PROMPT
from inercia.ai.schemas import JobDetail, ROIScore
from inercia.config import DEFAULT_BLACKLIST_KEYWORDS, get_settings
from inercia.cv.profiles import get_upwork_profile
from inercia.db.manager import get_blacklist_keywords

logger = logging.getLogger("inercia.ai.nodes.investor")

ROI_THRESHOLD: float = 6.0

BLACKLIST_KEYWORDS: frozenset[str] = frozenset(DEFAULT_BLACKLIST_KEYWORDS)


def _normalize_skill(value: str) -> str:
    return re.sub(r"[^a-z0-9+#.]+", " ", value.lower()).strip()


def _profile_skills() -> set[str]:
    return {_normalize_skill(skill) for skill in get_upwork_profile().skills}


def _job_skills(job_detail: JobDetail) -> set[str]:
    explicit = {_normalize_skill(skill) for skill in job_detail.skills}
    title_words = {_normalize_skill(word) for word in job_detail.title.split()}
    return {skill for skill in explicit.union(title_words) if skill}


def _contains_blacklist(job_detail: JobDetail, db_path: Optional[Path] = None) -> bool:
    title = job_detail.title.lower()
    description = job_detail.description.lower()
    keywords = get_blacklist_keywords(db_path)
    return any(keyword in title or keyword in description for keyword in keywords)


def score_job(job_detail: JobDetail, db_path: Optional[Path] = None) -> ROIScore:
    settings = get_settings(db_path=db_path)
    my_skills = _profile_skills()
    job_skills = _job_skills(job_detail)
    union = job_skills.union(my_skills)
    skill_overlap_ratio = len(job_skills.intersection(my_skills)) / len(union) if union else 0.0

    roi = 0.0
    reasons: list[str] = []
    roi += 40 * skill_overlap_ratio
    roi -= 20 * (job_detail.connects_required / 16)
    roi += 20 * min(job_detail.client_total_spent / 10000, 1.0)
    roi += 10 * job_detail.client_hire_rate
    roi += 10 * min(job_detail.client_reviews / 20, 1.0)

    blacklisted = _contains_blacklist(job_detail, db_path)
    if blacklisted:
        roi = -100
        reasons.append("blacklist_keyword")

    if job_detail.job_type == "fixed" and (job_detail.budget_max or 0) < settings.floor_fixed_rate:
        roi -= 50
        reasons.append("fixed_budget_below_floor")
    if job_detail.job_type == "hourly" and (job_detail.hourly_rate_max or 0) < settings.floor_hourly_rate:
        roi -= 50
        reasons.append("hourly_rate_below_floor")

    passed = roi >= ROI_THRESHOLD
    if passed:
        reasons.append("roi_passed")
    else:
        reasons.append("roi_below_threshold")
    score = ROIScore(
        score=round(roi, 2),
        passed=passed,
        skill_overlap_ratio=round(skill_overlap_ratio, 4),
        blacklisted=blacklisted,
        reasons=reasons,
    )
    logger.info("ROI scored | title=%s | roi=%.2f | passed=%s", job_detail.title, score.score, score.passed)
    return score


def _enforce_hard_rejections(baseline: ROIScore, candidate: ROIScore) -> ROIScore:
    hard_rejection_reasons = {
        "blacklist_keyword",
        "fixed_budget_below_floor",
        "hourly_rate_below_floor",
    }
    if baseline.blacklisted or hard_rejection_reasons.intersection(baseline.reasons):
        reasons = list(dict.fromkeys([*candidate.reasons, *baseline.reasons]))
        if "roi_below_threshold" not in reasons:
            reasons.append("roi_below_threshold")
        return candidate.model_copy(
            update={
                "score": min(candidate.score, baseline.score),
                "passed": False,
                "blacklisted": baseline.blacklisted,
                "reasons": reasons,
            }
        )
    if candidate.score < ROI_THRESHOLD and candidate.passed:
        reasons = [reason for reason in candidate.reasons if reason != "roi_passed"]
        reasons.append("roi_below_threshold")
        return candidate.model_copy(update={"passed": False, "reasons": list(dict.fromkeys(reasons))})
    return candidate


async def score_job_with_llm(job_detail: JobDetail, db_path: Optional[Path] = None) -> ROIScore:
    baseline = score_job(job_detail, db_path=db_path)
    settings = get_settings(db_path=db_path)
    fallback = lambda: baseline
    user_prompt = (
        f"Configured hourly floor: {settings.floor_hourly_rate}\n"
        f"Configured fixed floor: {settings.floor_fixed_rate}\n"
        f"ROI pass threshold: {ROI_THRESHOLD}\n"
        f"Deterministic baseline:\n{baseline.model_dump_json()}\n\n"
        f"Job detail:\n{job_detail.model_dump_json()}"
    )
    llm = StructuredLLM[ROIScore]()
    candidate = await llm.generate_structured(
        model=GEMINI_FLASH_MODEL,
        system_prompt=INVESTOR_SYSTEM_PROMPT,
        user_prompt=user_prompt,
        response_model=ROIScore,
        fallback_factory=fallback,
    )
    score = _enforce_hard_rejections(baseline, candidate)
    logger.info("Gemini ROI scored | title=%s | roi=%.2f | passed=%s", job_detail.title, score.score, score.passed)
    return score


__all__ = ["BLACKLIST_KEYWORDS", "ROI_THRESHOLD", "score_job", "score_job_with_llm"]

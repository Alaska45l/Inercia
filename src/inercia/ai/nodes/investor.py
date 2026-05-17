from __future__ import annotations

import logging
import re

from inercia.ai.schemas import JobDetail, ROIScore
from inercia.cv.profiles import get_upwork_profile

logger = logging.getLogger("inercia.ai.nodes.investor")

ROI_THRESHOLD: float = 6.0

BLACKLIST_KEYWORDS: frozenset[str] = frozenset(
    {
        "wordpress",
        "wix",
        "shopify",
        "squarespace",
        "bigcommerce",
        "elementor",
        "divi",
        "webflow",
        "woocommerce",
        "magento",
        "prestashop",
        "joomla",
        "drupal",
        "php developer",
        "theme customization",
        "plugin development",
    }
)


def _normalize_skill(value: str) -> str:
    return re.sub(r"[^a-z0-9+#.]+", " ", value.lower()).strip()


def _profile_skills() -> set[str]:
    return {_normalize_skill(skill) for skill in get_upwork_profile().skills}


def _job_skills(job_detail: JobDetail) -> set[str]:
    explicit = {_normalize_skill(skill) for skill in job_detail.skills}
    title_words = {_normalize_skill(word) for word in job_detail.title.split()}
    return {skill for skill in explicit.union(title_words) if skill}


def _contains_blacklist(job_detail: JobDetail) -> bool:
    title = job_detail.title.lower()
    description = job_detail.description.lower()
    return any(keyword in title or keyword in description for keyword in BLACKLIST_KEYWORDS)


def score_job(job_detail: JobDetail) -> ROIScore:
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

    blacklisted = _contains_blacklist(job_detail)
    if blacklisted:
        roi = -100
        reasons.append("blacklist_keyword")

    if job_detail.job_type == "fixed" and (job_detail.budget_max or 0) < 50:
        roi -= 50
        reasons.append("fixed_budget_below_floor")
    if job_detail.job_type == "hourly" and (job_detail.hourly_rate_max or 0) < 15:
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


__all__ = ["BLACKLIST_KEYWORDS", "ROI_THRESHOLD", "score_job"]

from __future__ import annotations

from inercia.ai.nodes.copywriter import deterministic_cover_letter, write_cover_letter
from inercia.ai.nodes.critic import deterministic_review, review_cover_letter
from inercia.ai.nodes.extractor import deterministic_extract, extract_job_detail
from inercia.ai.nodes.investor import BLACKLIST_KEYWORDS, ROI_THRESHOLD, score_job

__all__ = [
    "BLACKLIST_KEYWORDS",
    "ROI_THRESHOLD",
    "deterministic_cover_letter",
    "deterministic_extract",
    "deterministic_review",
    "extract_job_detail",
    "review_cover_letter",
    "score_job",
    "write_cover_letter",
]

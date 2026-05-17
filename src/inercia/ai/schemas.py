from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field


class JobDetail(BaseModel):
    upwork_id: Optional[str] = None
    title: str
    description: str
    job_type: Literal["hourly", "fixed"]
    budget_min: Optional[float] = None
    budget_max: Optional[float] = None
    hourly_rate_min: Optional[float] = None
    hourly_rate_max: Optional[float] = None
    duration: Optional[str] = None
    experience_level: Optional[str] = None
    skills: list[str] = Field(default_factory=list)
    client_country: Optional[str] = None
    client_total_spent: float = 0.0
    client_hire_rate: float = 0.0
    client_reviews: int = 0
    connects_required: int = 0
    questions: list[str] = Field(default_factory=list)
    allows_attachments: bool = False
    raw_markdown: Optional[str] = None


class ROIScore(BaseModel):
    score: float
    passed: bool
    skill_overlap_ratio: float
    blacklisted: bool = False
    reasons: list[str] = Field(default_factory=list)


class CoverLetter(BaseModel):
    letter: str
    screening_answers: dict[str, str] = Field(default_factory=dict)


class CriticReview(BaseModel):
    approved: bool
    issues: list[str] = Field(default_factory=list)
    rewritten_opening: Optional[str] = None


class ProposalPackage(BaseModel):
    job_detail: JobDetail
    roi_score: ROIScore
    cover_letter: CoverLetter
    critic_review: CriticReview
    bid_rate: float
    bid_type: Literal["hourly", "fixed"]
    connects_cost: int


__all__ = ["CoverLetter", "CriticReview", "JobDetail", "ProposalPackage", "ROIScore"]

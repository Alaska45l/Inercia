from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class JobRow:
    id: int
    upwork_id: str
    url: Optional[str]
    source: str
    source_metadata: Optional[str]
    posted_age_text: Optional[str]
    title: str
    description: str
    job_type: str
    budget_min: Optional[float]
    budget_max: Optional[float]
    hourly_rate_min: Optional[float]
    hourly_rate_max: Optional[float]
    duration: Optional[str]
    experience_level: Optional[str]
    skills: Optional[str]
    client_country: Optional[str]
    client_total_spent: float
    client_hire_rate: float
    client_reviews: int
    client_payment_verified: int
    connects_required: int
    questions: Optional[str]
    allows_attachments: int
    raw_markdown: Optional[str]
    scraped_at: str
    roi_score: Optional[float]
    status: str


@dataclass(frozen=True)
class ProposalRow:
    id: int
    job_id: int
    cover_letter: str
    screening_answers: Optional[str]
    bid_rate: float
    bid_type: str
    cv_pdf_path: Optional[str]
    connects_cost: int
    roi_score: float
    critic_approved: int
    critic_notes: Optional[str]
    status: str
    created_at: str
    submitted_at: Optional[str]


@dataclass(frozen=True)
class ConnectsLogRow:
    id: int
    proposal_id: Optional[int]
    amount: int
    action: str
    timestamp: str


@dataclass(frozen=True)
class SessionRow:
    id: int
    key: str
    value: str
    updated_at: str


__all__ = ["ConnectsLogRow", "JobRow", "ProposalRow", "SessionRow"]

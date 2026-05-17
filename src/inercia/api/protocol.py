from __future__ import annotations

from typing import Any, Literal, Optional, TypedDict


class ProposalReadyData(TypedDict):
    proposal_id: int
    job_id: int
    upwork_id: str
    title: str
    client_country: Optional[str]
    roi_score: float
    connects_cost: int
    bid_rate: float
    bid_type: str
    cover_letter: str
    screening_answers: dict[str, str]
    cv_pdf_path: Optional[str]
    status: str


class ProposalReady(TypedDict):
    type: Literal["proposal_ready"]
    data: ProposalReadyData


class StatsData(TypedDict):
    today_submitted: int
    today_approved: int
    today_rejected: int
    connects_remaining: int
    connects_spent_today: int


class StatsUpdate(TypedDict):
    type: Literal["stats_update"]
    data: StatsData


class ConnectsBalanceData(TypedDict):
    total: int
    spent_today: int
    remaining: int


class ConnectsBalance(TypedDict):
    type: Literal["connects_balance"]
    data: ConnectsBalanceData


class UserApproved(TypedDict):
    type: Literal["user_approved"]
    proposal_id: int


class UserRejected(TypedDict):
    type: Literal["user_rejected"]
    proposal_id: int
    reason: Optional[str]


def proposal_ready(data: ProposalReadyData) -> ProposalReady:
    return {"type": "proposal_ready", "data": data}


def stats_update(data: StatsData) -> StatsUpdate:
    return {"type": "stats_update", "data": data}


def connects_balance(total: int, spent_today: int) -> ConnectsBalance:
    return {
        "type": "connects_balance",
        "data": {"total": total, "spent_today": spent_today, "remaining": max(total - spent_today, 0)},
    }


def error_message(message: str) -> dict[str, Any]:
    return {"type": "error", "data": {"message": message}}


__all__ = [
    "ConnectsBalance",
    "ConnectsBalanceData",
    "ProposalReady",
    "ProposalReadyData",
    "StatsData",
    "StatsUpdate",
    "UserApproved",
    "UserRejected",
    "connects_balance",
    "error_message",
    "proposal_ready",
    "stats_update",
]

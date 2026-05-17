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


class RunScrape(TypedDict):
    type: Literal["run_scrape"]
    query: str
    allow_network: bool


class RunProcess(TypedDict):
    type: Literal["run_process"]
    limit: int


class OpenUpworkLogin(TypedDict):
    type: Literal["open_upwork_login"]


class CloseUpworkLogin(TypedDict):
    type: Literal["close_upwork_login"]


class LoginStatusData(TypedDict):
    browser_open: bool
    authenticated: bool
    message: str
    current_url: str


class LoginStatus(TypedDict):
    type: Literal["login_status"]
    data: LoginStatusData


class GetJobs(TypedDict):
    type: Literal["get_jobs"]
    status: Optional[str]
    limit: int


class GetSettings(TypedDict):
    type: Literal["get_settings"]


class SetSetting(TypedDict):
    type: Literal["set_setting"]
    key: str
    value: str


class SetConnectsTotal(TypedDict):
    type: Literal["set_connects_total"]
    total: int


class StartScheduler(TypedDict):
    type: Literal["start_scheduler"]


class StopScheduler(TypedDict):
    type: Literal["stop_scheduler"]


class ScrapeProgressData(TypedDict):
    phase: str
    queued: int
    processed: int
    failed: int


class ScrapeDoneData(TypedDict):
    query: str
    queued: int
    processed: int
    inserted: int
    failed: int


class ProcessProgressData(TypedDict):
    processed: int
    ready: int
    blacklisted: int
    failed: int


class ProcessDoneData(TypedDict):
    processed: int
    ready: int
    blacklisted: int
    failed: int
    cap_reached: bool


class JobRow(TypedDict):
    id: int
    upwork_id: str
    title: str
    job_type: str
    roi_score: Optional[float]
    status: str
    scraped_at: str


class UpworkSearchFiltersData(TypedDict):
    categories: list[str]
    experience_levels: list[str]
    job_types: list[str]
    budget_min: Optional[float]
    budget_max: Optional[float]
    hourly_rate_min: Optional[float]
    hourly_rate_max: Optional[float]
    hours_per_week: list[str]
    project_lengths: list[str]
    client_history: list[str]
    client_location: str
    proposals: list[str]
    max_connects: int


class SettingsData(TypedDict):
    gemini_api_key: str
    opencode_api_key: str
    opencode_base_url: str
    opencode_copywriter_model: str
    opencode_user_agent: str
    daily_proposal_cap: int
    floor_hourly_rate: float
    floor_fixed_rate: float
    allow_upwork_network: bool
    db_path: str
    upwork_session_dir: str
    ws_port: int
    has_gemini_key: bool
    has_opencode_key: bool
    scheduler_interval_min_minutes: int
    scheduler_interval_max_minutes: int
    blacklist_keywords: list[str]
    upwork_search_filters: UpworkSearchFiltersData
    portfolio_attachments: list[str]


class SchedulerStatusData(TypedDict):
    running: bool
    next_run_in_seconds: int


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


def scrape_progress(data: ScrapeProgressData) -> dict[str, Any]:
    return {"type": "scrape_progress", "data": data}


def scrape_done(data: ScrapeDoneData) -> dict[str, Any]:
    return {"type": "scrape_done", "data": data}


def process_progress(data: ProcessProgressData) -> dict[str, Any]:
    return {"type": "process_progress", "data": data}


def process_done(data: ProcessDoneData) -> dict[str, Any]:
    return {"type": "process_done", "data": data}


def jobs_list(jobs: list[JobRow]) -> dict[str, Any]:
    return {"type": "jobs_list", "data": {"jobs": jobs}}


def settings_state(data: SettingsData) -> dict[str, Any]:
    return {"type": "settings_state", "data": data}


def scheduler_status(data: SchedulerStatusData) -> dict[str, Any]:
    return {"type": "scheduler_status", "data": data}


def login_browser_opened() -> dict[str, Any]:
    return {"type": "login_browser_opened"}


def login_browser_closed(authenticated: bool = False, message: str = "") -> dict[str, Any]:
    return {
        "type": "login_browser_closed",
        "data": {"authenticated": authenticated, "message": message},
    }


def login_status(data: LoginStatusData) -> LoginStatus:
    return {"type": "login_status", "data": data}


__all__ = [
    "CloseUpworkLogin",
    "ConnectsBalance",
    "ConnectsBalanceData",
    "GetJobs",
    "GetSettings",
    "JobRow",
    "LoginStatus",
    "LoginStatusData",
    "OpenUpworkLogin",
    "ProcessDoneData",
    "ProcessProgressData",
    "ProposalReady",
    "ProposalReadyData",
    "RunProcess",
    "RunScrape",
    "ScrapeDoneData",
    "ScrapeProgressData",
    "SetConnectsTotal",
    "SetSetting",
    "StartScheduler",
    "StopScheduler",
    "SchedulerStatusData",
    "SettingsData",
    "StatsData",
    "StatsUpdate",
    "UpworkSearchFiltersData",
    "UserApproved",
    "UserRejected",
    "connects_balance",
    "error_message",
    "jobs_list",
    "login_browser_closed",
    "login_browser_opened",
    "login_status",
    "proposal_ready",
    "process_done",
    "process_progress",
    "scrape_done",
    "scrape_progress",
    "scheduler_status",
    "settings_state",
    "stats_update",
]

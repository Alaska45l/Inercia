from __future__ import annotations

import asyncio
import logging
import sqlite3
from pathlib import Path
from typing import Any, Optional, TypedDict

from inercia.ai.nodes.copywriter import write_cover_letter
from inercia.ai.nodes.critic import review_cover_letter
from inercia.ai.nodes.extractor import extract_job_detail
from inercia.ai.nodes.investor import score_job
from inercia.ai.schemas import CoverLetter, CriticReview, JobDetail, ProposalPackage, ROIScore
from inercia.applicator.rate_calculator import compute_bid_rate
from inercia.config import get_settings
from inercia.db.manager import count_submitted_today, create_proposal, list_jobs_by_status, update_job_roi, upsert_job

logger = logging.getLogger("inercia.ai.graph")

MAX_COPYWRITER_ATTEMPTS: int = 2


class PipelineState(TypedDict, total=False):
    job_id: int
    upwork_id: str
    raw_markdown: str
    fallback_title: str
    fallback_description: str
    job_detail: JobDetail
    roi_score: ROIScore
    cover_letter: CoverLetter
    critic_review: CriticReview
    critic_issues: list[str]
    copywriter_attempts: int
    proposal_package: ProposalPackage
    status: str


class _FallbackCompiledGraph:
    async def ainvoke(self, state: PipelineState) -> PipelineState:
        current = await _extractor_node(state)
        current = await _investor_node(current)
        if _route_after_investor(current) == "blacklisted":
            return current
        while True:
            current = await _copywriter_node(current)
            current = await _critic_node(current)
            route = _route_after_critic(current)
            if route == "copywriter":
                continue
            return current


def _compute_bid_rate(job_detail: JobDetail) -> float:
    return compute_bid_rate(job_detail).amount


async def _extractor_node(state: PipelineState) -> PipelineState:
    detail = await extract_job_detail(
        raw_markdown=state["raw_markdown"],
        upwork_id=state.get("upwork_id"),
        fallback_title=state.get("fallback_title", ""),
        fallback_description=state.get("fallback_description", ""),
    )
    state["job_detail"] = detail
    return state


async def _investor_node(state: PipelineState) -> PipelineState:
    roi = score_job(state["job_detail"])
    state["roi_score"] = roi
    state["status"] = "scored" if roi.passed else "blacklisted"
    return state


async def _copywriter_node(state: PipelineState) -> PipelineState:
    attempts = int(state.get("copywriter_attempts", 0)) + 1
    state["copywriter_attempts"] = attempts
    state["cover_letter"] = await write_cover_letter(
        job_detail=state["job_detail"],
        critic_issues=state.get("critic_issues"),
    )
    return state


async def _critic_node(state: PipelineState) -> PipelineState:
    review = await review_cover_letter(state["cover_letter"], state["job_detail"])
    state["critic_review"] = review
    state["critic_issues"] = review.issues
    attempts = int(state.get("copywriter_attempts", 0))
    if review.approved or attempts >= MAX_COPYWRITER_ATTEMPTS:
        _attach_proposal_package(state)
    return state


def _attach_proposal_package(state: PipelineState) -> None:
    job_detail = state["job_detail"]
    roi_score = state["roi_score"]
    package = ProposalPackage(
        job_detail=job_detail,
        roi_score=roi_score,
        cover_letter=state["cover_letter"],
        critic_review=state["critic_review"],
        bid_rate=_compute_bid_rate(job_detail),
        bid_type=job_detail.job_type,
        connects_cost=job_detail.connects_required,
    )
    state["proposal_package"] = package
    state["status"] = "ready"


def _route_after_investor(state: PipelineState) -> str:
    return "copywriter" if state["roi_score"].passed else "blacklisted"


def _route_after_critic(state: PipelineState) -> str:
    review = state["critic_review"]
    attempts = int(state.get("copywriter_attempts", 0))
    if not review.approved and attempts < MAX_COPYWRITER_ATTEMPTS:
        return "copywriter"
    return "done"


def build_graph() -> Any:
    try:
        from langgraph.graph import END, StateGraph
    except ModuleNotFoundError:
        logger.warning("langgraph is not installed; using local fallback graph runner")
        return _FallbackCompiledGraph()

    graph = StateGraph(PipelineState)
    graph.add_node("extractor", _extractor_node)
    graph.add_node("investor", _investor_node)
    graph.add_node("copywriter", _copywriter_node)
    graph.add_node("critic", _critic_node)
    graph.set_entry_point("extractor")
    graph.add_edge("extractor", "investor")
    graph.add_conditional_edges(
        "investor",
        _route_after_investor,
        {"copywriter": "copywriter", "blacklisted": END},
    )
    graph.add_edge("copywriter", "critic")
    graph.add_conditional_edges(
        "critic",
        _route_after_critic,
        {"copywriter": "copywriter", "done": END},
    )
    return graph.compile()


async def run_pipeline_for_markdown(
    raw_markdown: str,
    upwork_id: Optional[str] = None,
    fallback_title: str = "",
    fallback_description: str = "",
) -> PipelineState:
    graph = build_graph()
    initial_state: PipelineState = {
        "raw_markdown": raw_markdown,
        "fallback_title": fallback_title,
        "fallback_description": fallback_description,
        "copywriter_attempts": 0,
    }
    if upwork_id is not None:
        initial_state["upwork_id"] = upwork_id
    return await graph.ainvoke(initial_state)


def _job_update_payload(row: sqlite3.Row, detail: JobDetail, roi: ROIScore, status: str) -> dict[str, object]:
    return {
        "upwork_id": str(row["upwork_id"]),
        "title": detail.title,
        "description": detail.description,
        "job_type": detail.job_type,
        "budget_min": detail.budget_min,
        "budget_max": detail.budget_max,
        "hourly_rate_min": detail.hourly_rate_min,
        "hourly_rate_max": detail.hourly_rate_max,
        "duration": detail.duration,
        "experience_level": detail.experience_level,
        "skills": detail.skills,
        "client_country": detail.client_country,
        "client_total_spent": detail.client_total_spent,
        "client_hire_rate": detail.client_hire_rate,
        "client_reviews": detail.client_reviews,
        "connects_required": detail.connects_required,
        "questions": detail.questions,
        "allows_attachments": 1 if detail.allows_attachments else 0,
        "raw_markdown": detail.raw_markdown or str(row["raw_markdown"] or ""),
        "roi_score": roi.score,
        "status": status,
    }


async def _save_pipeline_result(row: sqlite3.Row, state: PipelineState, db_path: Optional[Path]) -> Optional[int]:
    detail = state["job_detail"]
    roi = state["roi_score"]
    status = str(state["status"])
    await asyncio.to_thread(upsert_job, _job_update_payload(row, detail, roi, status), db_path)
    if status == "blacklisted":
        await asyncio.to_thread(update_job_roi, int(row["id"]), roi.score, "blacklisted", db_path)
        return None
    package = state["proposal_package"]
    proposal_id = await asyncio.to_thread(
        create_proposal,
        {
            "job_id": int(row["id"]),
            "cover_letter": package.cover_letter.letter,
            "screening_answers": package.cover_letter.screening_answers,
            "bid_rate": package.bid_rate,
            "bid_type": package.bid_type,
            "connects_cost": package.connects_cost,
            "roi_score": package.roi_score.score,
            "critic_approved": 1 if package.critic_review.approved else 0,
            "critic_notes": "\n".join(package.critic_review.issues),
            "status": "pending",
        },
        db_path,
    )
    return int(proposal_id)


async def process_unprocessed_jobs(limit: int = 20, db_path: Optional[Path] = None) -> dict[str, object]:
    settings = get_settings()
    cap = settings.daily_proposal_cap
    submitted_today = await asyncio.to_thread(count_submitted_today, db_path)
    if submitted_today >= cap:
        logger.warning("Daily proposal cap reached (%d/%d) — skipping pipeline", submitted_today, cap)
        return {"processed": 0, "ready": 0, "blacklisted": 0, "failed": 0, "cap_reached": True}

    rows = await asyncio.to_thread(list_jobs_by_status, "new", limit, db_path)
    processed = 0
    ready = 0
    blacklisted = 0
    failed = 0
    for row in rows:
        current_submitted = await asyncio.to_thread(count_submitted_today, db_path)
        if current_submitted >= cap:
            logger.info("Daily cap reached mid-run (%d/%d) — stopping pipeline", current_submitted, cap)
            break
        try:
            state = await run_pipeline_for_markdown(
                raw_markdown=str(row["raw_markdown"] or row["description"]),
                upwork_id=str(row["upwork_id"]),
                fallback_title=str(row["title"]),
                fallback_description=str(row["description"]),
            )
            proposal_id = await _save_pipeline_result(row, state, db_path)
            processed += 1
            if proposal_id is None:
                blacklisted += 1
            else:
                ready += 1
        except Exception as exc:
            failed += 1
            logger.exception("Failed processing job id=%s | error=%s", row["id"], exc)
    return {"processed": processed, "ready": ready, "blacklisted": blacklisted, "failed": failed, "cap_reached": False}


__all__ = [
    "MAX_COPYWRITER_ATTEMPTS",
    "PipelineState",
    "build_graph",
    "process_unprocessed_jobs",
    "run_pipeline_for_markdown",
]

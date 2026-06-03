from __future__ import annotations

import asyncio
import difflib
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from inercia.applicator.session import UpworkSession, open_persistent_upwork_session
from inercia.scraper.engine import NAV_TIMEOUT_MS, block_heavy_resources, human_mouse_jitter
from inercia.scraper.selectors import (
    UPWORK_ATTACHMENT_INPUT,
    UPWORK_COVER_LETTER,
    UPWORK_RATE_INPUT,
    UPWORK_SCREENING_QUESTIONS,
    UPWORK_SUBMIT_BUTTON,
)

logger = logging.getLogger("inercia.applicator.apply_flow")

MOCK_APPLY_URL: str = "mock://upwork/apply"
_APPLY_SESSIONS: dict[int, UpworkSession] = {}


@dataclass(frozen=True)
class ApplyPayload:
    apply_url: str
    bid_rate: float
    cover_letter: str
    screening_answers: dict[str, str] = field(default_factory=dict)
    cv_pdf_path: Optional[Path] = None
    portfolio_attachment_paths: list[Path] = field(default_factory=list)


@dataclass(frozen=True)
class ApplyFlowResult:
    apply_url: str
    rate_set: bool
    cover_letter_set: bool
    screening_answers_set: int
    attachment_set: bool
    submit_button_found: bool
    stopped_before_submit: bool


def _mock_result(payload: ApplyPayload) -> ApplyFlowResult:
    return ApplyFlowResult(
        apply_url=payload.apply_url,
        rate_set=True,
        cover_letter_set=bool(payload.cover_letter.strip()),
        screening_answers_set=len(payload.screening_answers),
        attachment_set=payload.cv_pdf_path is not None or bool(payload.portfolio_attachment_paths),
        submit_button_found=True,
        stopped_before_submit=True,
    )


async def close_apply_session(proposal_id: int) -> None:
    session = _APPLY_SESSIONS.pop(proposal_id, None)
    if session is None:
        return
    await session.context.close()
    await session.playwright.stop()
    logger.info("Closed Upwork apply session | proposal_id=%d", proposal_id)


def _normalize_question(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", value.lower()).strip()


def _question_tokens(value: str) -> set[str]:
    return {token for token in _normalize_question(value).split() if len(token) > 2}


def _context_lines(value: str) -> list[str]:
    return [_normalize_question(line) for line in value.splitlines() if _normalize_question(line)]


def _question_match_score(question: str, context: str) -> float:
    normalized_question = _normalize_question(question)
    normalized_context = _normalize_question(context)
    if not normalized_question or not normalized_context:
        return 0.0
    question_tokens = _question_tokens(question)
    context_tokens = _question_tokens(context)
    token_score = len(question_tokens.intersection(context_tokens)) / len(question_tokens) if question_tokens else 0.0
    ratio_score = difflib.SequenceMatcher(None, normalized_question, normalized_context).ratio()
    return max(token_score, ratio_score)


def _select_screening_question(
    answers: list[tuple[str, str]],
    used_indexes: set[int],
    context: str,
    input_index: int,
) -> Optional[int]:
    normalized_lines = set(_context_lines(context))
    for answer_index, (question, _answer) in enumerate(answers):
        if answer_index in used_indexes:
            continue
        normalized_question = _normalize_question(question)
        if normalized_question and normalized_question in normalized_lines:
            return answer_index

    best_index: Optional[int] = None
    best_score = 0.0
    for answer_index, (question, _answer) in enumerate(answers):
        if answer_index in used_indexes:
            continue
        score = _question_match_score(question, context)
        if score > best_score:
            best_index = answer_index
            best_score = score
    if best_index is not None and best_score >= 0.55:
        return best_index

    unused_indexes = [index for index in range(len(answers)) if index not in used_indexes]
    if not unused_indexes:
        return None
    if input_index < len(unused_indexes):
        return unused_indexes[input_index]
    return unused_indexes[0]


async def _fill_screening_answers(page: object, answers: dict[str, str]) -> int:
    if not answers:
        return 0
    question_inputs = page.locator(UPWORK_SCREENING_QUESTIONS)
    input_count = await question_inputs.count()
    answer_items = list(answers.items())
    used_indexes: set[int] = set()
    answer_count = 0
    for index in range(input_count):
        input_locator = question_inputs.nth(index)
        context = ""
        try:
            context = await input_locator.locator("xpath=ancestor::*[self::section or self::div][1]").inner_text(
                timeout=2_000
            )
        except Exception:
            context = ""

        selected_index = _select_screening_question(answer_items, used_indexes, context, index)
        if selected_index is None:
            break

        await input_locator.fill(answer_items[selected_index][1], timeout=NAV_TIMEOUT_MS)
        used_indexes.add(selected_index)
        answer_count += 1
    return answer_count


async def prepare_application(
    payload: ApplyPayload,
    proposal_id: Optional[int] = None,
    user_data_dir: Optional[Path] = None,
    allow_network: bool = False,
) -> tuple[ApplyFlowResult, Optional[UpworkSession]]:
    if not allow_network or payload.apply_url.startswith("mock://"):
        await asyncio.sleep(0)
        logger.info("Prepared mock apply flow | url=%s", payload.apply_url)
        return _mock_result(payload), None

    if proposal_id is not None:
        await close_apply_session(proposal_id)
    session = await open_persistent_upwork_session(user_data_dir=user_data_dir, headless=False)
    page = await session.context.new_page()
    await block_heavy_resources(page)
    try:
        response = await page.goto(payload.apply_url, wait_until="domcontentloaded", timeout=NAV_TIMEOUT_MS)
        if response is not None and response.status >= 400:
            raise RuntimeError(f"Upwork returned HTTP {response.status} for {payload.apply_url}")
        await human_mouse_jitter(page)

        rate_set = False
        rate_inputs = page.locator(UPWORK_RATE_INPUT)
        if await rate_inputs.count() > 0:
            await rate_inputs.first.fill(str(payload.bid_rate), timeout=NAV_TIMEOUT_MS)
            rate_set = True

        cover_letter_set = False
        cover_inputs = page.locator(UPWORK_COVER_LETTER)
        if await cover_inputs.count() > 0:
            await cover_inputs.first.fill(payload.cover_letter, timeout=NAV_TIMEOUT_MS)
            cover_letter_set = True

        answer_count = await _fill_screening_answers(page, payload.screening_answers)

        attachment_set = False
        attachment_paths = [
            path
            for path in ([payload.cv_pdf_path] if payload.cv_pdf_path is not None else []) + payload.portfolio_attachment_paths
            if path.exists()
        ]
        if attachment_paths:
            uploads = page.locator(UPWORK_ATTACHMENT_INPUT)
            if await uploads.count() > 0:
                await uploads.first.set_input_files([str(path) for path in attachment_paths], timeout=NAV_TIMEOUT_MS)
                attachment_set = True

        submit_button_found = await page.locator(UPWORK_SUBMIT_BUTTON).count() > 0
        # Browser intentionally left open for human review; Playwright holds the reference.
        logger.info("Prepared visible Upwork apply form and stopped before Submit | url=%s", payload.apply_url)
        result = ApplyFlowResult(
            apply_url=payload.apply_url,
            rate_set=rate_set,
            cover_letter_set=cover_letter_set,
            screening_answers_set=answer_count,
            attachment_set=attachment_set,
            submit_button_found=submit_button_found,
            stopped_before_submit=True,
        )
        if proposal_id is not None:
            _APPLY_SESSIONS[proposal_id] = session
        return result, session
    except Exception:
        await page.close()
        await session.context.close()
        await session.playwright.stop()
        raise


__all__ = ["ApplyFlowResult", "ApplyPayload", "MOCK_APPLY_URL", "close_apply_session", "prepare_application"]

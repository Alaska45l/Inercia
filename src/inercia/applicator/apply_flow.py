from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from inercia.applicator.session import open_persistent_upwork_session
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


@dataclass(frozen=True)
class ApplyPayload:
    apply_url: str
    bid_rate: float
    cover_letter: str
    screening_answers: dict[str, str] = field(default_factory=dict)
    cv_pdf_path: Optional[Path] = None


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
        attachment_set=payload.cv_pdf_path is not None,
        submit_button_found=True,
        stopped_before_submit=True,
    )


async def _fill_screening_answers(page: object, answers: dict[str, str]) -> int:
    if not answers:
        return 0
    question_inputs = page.locator(UPWORK_SCREENING_QUESTIONS)
    input_count = await question_inputs.count()
    used_questions: set[str] = set()
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

        selected_question: Optional[str] = None
        context_lower = context.lower()
        for question in answers:
            if question in used_questions:
                continue
            if question.lower() in context_lower:
                selected_question = question
                break

        if selected_question is None:
            for question in answers:
                if question not in used_questions:
                    selected_question = question
                    break

        if selected_question is None:
            break

        await input_locator.fill(answers[selected_question], timeout=NAV_TIMEOUT_MS)
        used_questions.add(selected_question)
        answer_count += 1
    return answer_count


async def prepare_application(
    payload: ApplyPayload,
    user_data_dir: Optional[Path] = None,
    allow_network: bool = False,
) -> ApplyFlowResult:
    if not allow_network or payload.apply_url.startswith("mock://"):
        await asyncio.sleep(0)
        logger.info("Prepared mock apply flow | url=%s", payload.apply_url)
        return _mock_result(payload)

    session = await open_persistent_upwork_session(user_data_dir=user_data_dir, headless=False)
    page = await session.context.new_page()
    await block_heavy_resources(page)
    try:
        response = await page.goto(payload.apply_url, wait_until="domcontentloaded", timeout=NAV_TIMEOUT_MS)
        if response is not None and response.status >= 400:
            raise RuntimeError(f"Upwork returned HTTP {response.status} for {payload.apply_url}")
        await human_mouse_jitter(page)

        rate_set = False
        rate_input = page.locator(UPWORK_RATE_INPUT).first
        if await rate_input.count() > 0:
            await rate_input.fill(str(payload.bid_rate), timeout=NAV_TIMEOUT_MS)
            rate_set = True

        cover_letter_set = False
        cover = page.locator(UPWORK_COVER_LETTER).first
        if await cover.count() > 0:
            await cover.fill(payload.cover_letter, timeout=NAV_TIMEOUT_MS)
            cover_letter_set = True

        answer_count = await _fill_screening_answers(page, payload.screening_answers)

        attachment_set = False
        if payload.cv_pdf_path is not None and payload.cv_pdf_path.exists():
            upload = page.locator(UPWORK_ATTACHMENT_INPUT).first
            if await upload.count() > 0:
                await upload.set_input_files(str(payload.cv_pdf_path), timeout=NAV_TIMEOUT_MS)
                attachment_set = True

        submit_button_found = await page.locator(UPWORK_SUBMIT_BUTTON).count() > 0
        # Browser intentionally left open for human review; Playwright holds the reference.
        logger.info("Prepared visible Upwork apply form and stopped before Submit | url=%s", payload.apply_url)
        return ApplyFlowResult(
            apply_url=payload.apply_url,
            rate_set=rate_set,
            cover_letter_set=cover_letter_set,
            screening_answers_set=answer_count,
            attachment_set=attachment_set,
            submit_button_found=submit_button_found,
            stopped_before_submit=True,
        )
    except Exception:
        await page.close()
        await session.context.close()
        await session.playwright.stop()
        raise


__all__ = ["ApplyFlowResult", "ApplyPayload", "MOCK_APPLY_URL", "prepare_application"]

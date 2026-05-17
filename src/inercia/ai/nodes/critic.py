from __future__ import annotations

import logging

from inercia.ai.llm import GEMINI_FLASH_MODEL, StructuredLLM
from inercia.ai.prompts import CRITIC_SYSTEM_PROMPT, FORBIDDEN_COPY_TERMS, FORBIDDEN_OPENINGS
from inercia.ai.schemas import CoverLetter, CriticReview, JobDetail

logger = logging.getLogger("inercia.ai.nodes.critic")


def _word_count(text: str) -> int:
    return len([word for word in text.split() if word.strip()])


def deterministic_review(cover_letter: CoverLetter, job_detail: JobDetail) -> CriticReview:
    issues: list[str] = []
    letter = cover_letter.letter.strip()
    lowered = letter.lower()
    if any(lowered.startswith(opening) for opening in FORBIDDEN_OPENINGS):
        issues.append("opening_is_greeting_or_ai_template")
    if _word_count(letter) > 150:
        issues.append("letter_over_150_words")
    if "alaska" not in lowered:
        issues.append("missing_name_alaska")
    if any(term in lowered for term in FORBIDDEN_COPY_TERMS):
        issues.append("contains_forbidden_ai_speak")
    for question in job_detail.questions:
        answer = cover_letter.screening_answers.get(question, "")
        if len(answer.split()) < 8:
            issues.append(f"generic_screening_answer:{question}")
    rewritten_opening = None
    if issues:
        primary = job_detail.skills[0] if job_detail.skills else "technical"
        rewritten_opening = f"I would start this {primary} work with a small typed pipeline and a reproducible fixture."
    review = CriticReview(approved=not issues, issues=issues, rewritten_opening=rewritten_opening)
    logger.info("Critic reviewed letter | title=%s | approved=%s", job_detail.title, review.approved)
    return review


async def review_cover_letter(cover_letter: CoverLetter, job_detail: JobDetail) -> CriticReview:
    fallback = lambda: deterministic_review(cover_letter, job_detail)
    user_prompt = f"Job:\n{job_detail.model_dump_json()}\n\nCover letter:\n{cover_letter.model_dump_json()}"
    llm = StructuredLLM[CriticReview]()
    return await llm.generate_structured(
        model=GEMINI_FLASH_MODEL,
        system_prompt=CRITIC_SYSTEM_PROMPT,
        user_prompt=user_prompt,
        response_model=CriticReview,
        fallback_factory=fallback,
    )


__all__ = ["deterministic_review", "review_cover_letter"]

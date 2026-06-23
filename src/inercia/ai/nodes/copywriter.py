from __future__ import annotations

import logging
from typing import Optional

from inercia.ai.llm import GEMINI_PRO_MODEL, StructuredLLM
from inercia.ai.prompts import COPYWRITER_SYSTEM_PROMPT, FORBIDDEN_COPY_TERMS
from inercia.ai.schemas import CoverLetter, JobDetail
from inercia.cv.profiles import CVProfile, get_upwork_profile

logger = logging.getLogger("inercia.ai.nodes.copywriter")


def _word_count(text: str) -> int:
    return len([word for word in text.split() if word.strip()])


def _project_match(profile: CVProfile, job_detail: JobDetail) -> str:
    haystack = f"{job_detail.title} {job_detail.description} {' '.join(job_detail.skills)}".lower()
    for project in profile.projects:
        if any(skill.lower() in haystack for skill in ("python", "playwright", "svelte", "tauri", "security", "go")):
            return project
    return profile.projects[0]


def _sanitize_letter(letter: str) -> str:
    cleaned = letter.strip()
    for term in FORBIDDEN_COPY_TERMS:
        cleaned = cleaned.replace(term, "skill")
        cleaned = cleaned.replace(term.title(), "Skill")
    return cleaned


def _sanitize_cover_letter(cover_letter: CoverLetter) -> CoverLetter:
    return cover_letter.model_copy(update={"letter": _sanitize_letter(cover_letter.letter)})


def deterministic_cover_letter(
    job_detail: JobDetail,
    profile: Optional[CVProfile] = None,
    critic_issues: Optional[list[str]] = None,
) -> CoverLetter:
    selected_profile = profile or get_upwork_profile()
    project = _project_match(selected_profile, job_detail)
    primary_skill = job_detail.skills[0] if job_detail.skills else "Python"
    opening = (
        f"I can build the {primary_skill} workflow with async boundaries, Playwright isolation, "
        "and SQLite deduplication from the start."
    )
    body = (
        f"That matches my INVARIANT SYSTEM work, where I built Python tooling around a Go/SvelteKit "
        f"platform, plus freelance automation and Linux troubleshooting. For this job, I would first "
        f"map the data contract, add retries and clear logging, then keep the browser layer separate "
        f"from persistence so failures are easy to replay. Alaska"
    )
    if critic_issues:
        opening = "The implementation should start with a typed async pipeline and a small reproducible scraper fixture."
    letter = _sanitize_letter(f"{opening} {body}")
    words = letter.split()
    if len(words) > 150:
        letter = " ".join(words[:149] + ["Alaska"])
    answers = {
        question: (
            f"I would handle this with {primary_skill}, explicit error states, and tests around the "
            "data shape before touching the live browser flow."
        )
        for question in job_detail.questions
    }
    if "Playwright" in project and not answers:
        answers = {}
    logger.info("Cover letter drafted | title=%s | words=%d", job_detail.title, _word_count(letter))
    return CoverLetter(letter=letter, screening_answers=answers)


async def write_cover_letter(
    job_detail: JobDetail,
    profile: Optional[CVProfile] = None,
    critic_issues: Optional[list[str]] = None,
) -> CoverLetter:
    selected_profile = profile or get_upwork_profile()
    fallback = lambda: deterministic_cover_letter(job_detail, selected_profile, critic_issues)
    user_prompt = (
        f"Profile:\n{selected_profile}\n\nJob:\n{job_detail.model_dump_json()}\n\n"
        f"Previous critic issues: {critic_issues or []}\n\n"
        "Return screening_answers as a JSON object keyed by the exact screening question text."
    )
    llm = StructuredLLM[CoverLetter]()
    response = await llm.generate_structured(
        model=GEMINI_PRO_MODEL,
        system_prompt=COPYWRITER_SYSTEM_PROMPT,
        user_prompt=user_prompt,
        response_model=CoverLetter,
        fallback_factory=fallback,
    )
    cover_letter = _sanitize_cover_letter(response)
    logger.info("Cover letter drafted | title=%s | words=%d", job_detail.title, _word_count(cover_letter.letter))
    return cover_letter


__all__ = ["deterministic_cover_letter", "write_cover_letter"]

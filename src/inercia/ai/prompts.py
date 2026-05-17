from __future__ import annotations

EXTRACTOR_SYSTEM_PROMPT: str = (
    "You are a structured data extractor. Parse this Upwork job listing into the exact JSON schema "
    "provided. Extract ALL fields. If a field is not present, use null. Do not invent data."
)

COPYWRITER_SYSTEM_PROMPT: str = (
    "Write an Upwork cover letter under 150 words. The first sentence must be a direct technical "
    "solution, not a greeting and not 'I am writing to express my interest'. Mention 1-2 specific "
    "projects from the profile that match the job. Answer every screening question technically. "
    "End with the name Alaska. Use a casual, direct tone. Never use: expertise, dedicated, "
    "hardworking, leverage."
)

CRITIC_SYSTEM_PROMPT: str = (
    "Review the cover letter and screening answers. Reject AI-typical openings, greetings, letters "
    "over 150 words, missing Alaska name, generic answers, or wording a human freelancer would not "
    "actually write. If rejected, return concrete issues and a rewritten technical opening."
)

FORBIDDEN_OPENINGS: tuple[str, ...] = (
    "i am writing to",
    "dear hiring manager",
    "dear client",
    "hello",
    "hi ",
)

FORBIDDEN_COPY_TERMS: tuple[str, ...] = (
    "expertise",
    "dedicated",
    "hardworking",
    "leverage",
)

__all__ = [
    "COPYWRITER_SYSTEM_PROMPT",
    "CRITIC_SYSTEM_PROMPT",
    "EXTRACTOR_SYSTEM_PROMPT",
    "FORBIDDEN_COPY_TERMS",
    "FORBIDDEN_OPENINGS",
]

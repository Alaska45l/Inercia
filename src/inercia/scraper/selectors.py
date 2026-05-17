from __future__ import annotations

UPWORK_MAIN: str = "main#main"
UPWORK_JOB_TITLE: str = "[data-test='job-title'], h1"
UPWORK_APPLY_URL_PREFIX: str = "https://www.upwork.com/freelance-jobs/apply/"
UPWORK_RATE_INPUT: str = "input[name*='rate'], input[data-test*='rate'], input[aria-label*='rate' i]"
UPWORK_COVER_LETTER: str = "textarea[name*='cover'], textarea[data-test*='cover'], textarea"
UPWORK_SCREENING_QUESTIONS: str = "textarea[name*='question'], textarea[data-test*='question']"
UPWORK_ATTACHMENT_INPUT: str = "input[type='file']"
UPWORK_SUBMIT_BUTTON: str = "button[type='submit'], button:has-text('Submit'), button:has-text('Send proposal')"

RESOURCE_ROUTE_PATTERN: str = "**/*"

__all__ = [
    "RESOURCE_ROUTE_PATTERN",
    "UPWORK_APPLY_URL_PREFIX",
    "UPWORK_ATTACHMENT_INPUT",
    "UPWORK_COVER_LETTER",
    "UPWORK_JOB_TITLE",
    "UPWORK_MAIN",
    "UPWORK_RATE_INPUT",
    "UPWORK_SCREENING_QUESTIONS",
    "UPWORK_SUBMIT_BUTTON",
]

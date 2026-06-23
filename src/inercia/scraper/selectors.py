from __future__ import annotations

UPWORK_MAIN: str = "main#main"
UPWORK_FIND_WORK_URL: str = "https://www.upwork.com/nx/find-work/"
UPWORK_SEARCH_JOBS_URL: str = "https://www.upwork.com/nx/search/jobs/"
UPWORK_JOB_TITLE: str = "[data-test='job-title'], h1"
UPWORK_JOB_CARD: str = (
    "article[data-ev-job-uid], [data-test='job-tile'], "
    "section[data-test*='job-tile'], article[data-test*='job']"
)
UPWORK_JOB_CARD_TITLE_LINK: str = (
    "[data-test='job-tile-title-link'], a[data-test*='job-title'], "
    "a[href*='/jobs/'], h2.job-tile-title a, h2 a"
)
UPWORK_JOB_CARD_DESCRIPTION: str = (
    ".air3-line-clamp-wrapper.clamp p, [data-test*='description'], "
    "[data-test*='Description'], p"
)
UPWORK_JOB_CARD_AGE: str = "[data-test='job-pubilshed-date'], [data-test*='posted'], [data-test*='date'], small, span"
UPWORK_JOB_CARD_PROPOSALS: str = "[data-test='proposals-tier'], [data-test*='proposals']"
UPWORK_JOB_CARD_METADATA: str = "[data-test*='metadata'], [data-test*='attrs'], small, span"
UPWORK_SEARCH_RESULTS_READY: str = UPWORK_JOB_CARD
UPWORK_SEARCH_INPUT: str = "input[type='search'], input[placeholder*='Search' i]"
UPWORK_BUTTON_BY_TEXT: str = "button:has-text('{text}'), [role='button']:has-text('{text}')"
UPWORK_LABEL_BY_TEXT: str = "label:has-text('{text}'), button:has-text('{text}'), span:has-text('{text}')"
UPWORK_CHECKBOX_BY_LABEL: str = "label:has-text('{text}') input[type='checkbox'], input[aria-label*='{text}' i]"
UPWORK_FILTER_NUMBER_INPUT: str = "input[type='number'], input[inputmode='numeric']"
UPWORK_FILTER_TEXT_INPUT: str = "input[type='text'], input[type='search']"
UPWORK_SORT_LABEL: str = "Most Recent"
UPWORK_PAYMENT_VERIFIED_LABEL: str = "Payment verified"
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
    "UPWORK_BUTTON_BY_TEXT",
    "UPWORK_CHECKBOX_BY_LABEL",
    "UPWORK_COVER_LETTER",
    "UPWORK_FIND_WORK_URL",
    "UPWORK_FILTER_NUMBER_INPUT",
    "UPWORK_FILTER_TEXT_INPUT",
    "UPWORK_JOB_CARD",
    "UPWORK_JOB_CARD_AGE",
    "UPWORK_JOB_CARD_DESCRIPTION",
    "UPWORK_JOB_CARD_METADATA",
    "UPWORK_JOB_CARD_PROPOSALS",
    "UPWORK_JOB_CARD_TITLE_LINK",
    "UPWORK_JOB_TITLE",
    "UPWORK_LABEL_BY_TEXT",
    "UPWORK_MAIN",
    "UPWORK_PAYMENT_VERIFIED_LABEL",
    "UPWORK_RATE_INPUT",
    "UPWORK_SEARCH_INPUT",
    "UPWORK_SEARCH_JOBS_URL",
    "UPWORK_SEARCH_RESULTS_READY",
    "UPWORK_SCREENING_QUESTIONS",
    "UPWORK_SORT_LABEL",
    "UPWORK_SUBMIT_BUTTON",
]

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, ClassVar, Generic, TypeVar

from google.api_core.exceptions import ResourceExhausted
from pydantic import BaseModel
from tenacity import before_sleep_log, retry, retry_if_exception_type, stop_after_attempt, wait_exponential, wait_random

from inercia.ai.schemas import CoverLetter, CriticReview, JobDetail, ProposalPackage, ROIScore
from inercia.config import get_settings

logger = logging.getLogger("inercia.ai.llm")

T = TypeVar("T", bound=BaseModel)

GEMINI_FLASH_MODEL: str = "gemini-2.0-flash"
GEMINI_PRO_MODEL: str = "gemini-1.5-pro"
GEMINI_RETRY_ATTEMPTS: int = 6
GEMINI_RETRY_MAX_SECONDS: int = 90
NATIVE_GEMINI_SCHEMAS: tuple[type[BaseModel], ...] = (
    JobDetail,
    ROIScore,
    CoverLetter,
    CriticReview,
    ProposalPackage,
)


@dataclass
class TokenUsage:
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


class UnsupportedGeminiSchemaError(ValueError):
    """Raised when a caller tries to bypass the shared native Gemini schemas."""


def _looks_like_resource_exhausted(exc: Exception) -> bool:
    code = getattr(exc, "code", None)
    status = getattr(exc, "status", None)
    message = str(exc)
    return (
        code == 429
        or status == "RESOURCE_EXHAUSTED"
        or "RESOURCE_EXHAUSTED" in message
        or "429" in message
        or "quota" in message.lower()
        or "rate limit" in message.lower()
    )


@retry(
    retry=retry_if_exception_type(ResourceExhausted),
    wait=wait_exponential(multiplier=4, min=8, max=GEMINI_RETRY_MAX_SECONDS) + wait_random(0, 4),
    stop=stop_after_attempt(GEMINI_RETRY_ATTEMPTS),
    before_sleep=before_sleep_log(logger, logging.WARNING),
    reraise=True,
)
def _execute_gemini_request(
    client: Any,
    model: str,
    system_prompt: str,
    user_prompt: str,
    response_model: type[T],
) -> Any:
    try:
        return client.models.generate_content(
            model=model,
            contents=user_prompt,
            config={
                "system_instruction": system_prompt,
                "response_mime_type": "application/json",
                "response_schema": response_model,
                "temperature": 0.2,
            },
        )
    except ResourceExhausted:
        raise
    except Exception as exc:
        if _looks_like_resource_exhausted(exc):
            raise ResourceExhausted(str(exc)) from exc
        raise


class StructuredLLM(Generic[T]):
    _gemini_clients: ClassVar[dict[str, Any]] = {}

    def __init__(self) -> None:
        self.usage = TokenUsage()

    def _has_gemini(self) -> bool:
        return bool(get_settings().gemini_api_key)

    @classmethod
    def _get_gemini_client(cls, api_key: str) -> Any:
        client = cls._gemini_clients.get(api_key)
        if client is not None:
            return client
        from google import genai

        client = genai.Client(api_key=api_key)
        cls._gemini_clients[api_key] = client
        return client

    def _validate_response_model(self, response_model: type[T]) -> None:
        if response_model not in NATIVE_GEMINI_SCHEMAS:
            schema_names = ", ".join(schema.__name__ for schema in NATIVE_GEMINI_SCHEMAS)
            raise UnsupportedGeminiSchemaError(
                f"{response_model.__name__} is not registered as a native Gemini schema. "
                f"Use one of: {schema_names}."
            )

    def _parse_response(self, response: Any, response_model: type[T]) -> T:
        usage_metadata = getattr(response, "usage_metadata", None)
        if usage_metadata is not None:
            self.usage.prompt_tokens += int(getattr(usage_metadata, "prompt_token_count", 0) or 0)
            self.usage.completion_tokens += int(getattr(usage_metadata, "candidates_token_count", 0) or 0)
            self.usage.total_tokens += int(getattr(usage_metadata, "total_token_count", 0) or 0)

        parsed = getattr(response, "parsed", None)
        if parsed is not None:
            return response_model.model_validate(parsed)

        text = str(getattr(response, "text", "") or "").strip()
        if not text:
            raise ValueError("Gemini response did not include structured JSON text.")
        return response_model.model_validate_json(text)

    def _generate_sync(
        self,
        model: str,
        system_prompt: str,
        user_prompt: str,
        response_model: type[T],
    ) -> T:
        self._validate_response_model(response_model)
        settings = get_settings()
        client = self._get_gemini_client(settings.gemini_api_key)
        response = _execute_gemini_request(
            client=client,
            model=model,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            response_model=response_model,
        )
        return self._parse_response(response, response_model)

    async def generate_structured(
        self,
        model: str,
        system_prompt: str,
        user_prompt: str,
        response_model: type[T],
        fallback_factory: Callable[[], T],
    ) -> T:
        self._validate_response_model(response_model)
        if not self._has_gemini():
            logger.info("GEMINI_API_KEY is not set; using offline structured fallback for %s", model)
            return fallback_factory()

        try:
            return await asyncio.to_thread(
                self._generate_sync,
                model,
                system_prompt,
                user_prompt,
                response_model,
            )
        except UnsupportedGeminiSchemaError:
            raise
        except Exception as exc:
            logger.error("Gemini structured generation unavailable; using fallback | model=%s | error=%s", model, exc)
            return fallback_factory()


__all__ = [
    "GEMINI_FLASH_MODEL",
    "GEMINI_PRO_MODEL",
    "GEMINI_RETRY_ATTEMPTS",
    "GEMINI_RETRY_MAX_SECONDS",
    "NATIVE_GEMINI_SCHEMAS",
    "StructuredLLM",
    "TokenUsage",
    "UnsupportedGeminiSchemaError",
]

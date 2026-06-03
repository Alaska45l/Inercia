from __future__ import annotations

import asyncio
import json
import logging
import urllib.error
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, ClassVar, Generic, Optional, TypeVar

from pydantic import BaseModel

from inercia.config import get_settings

logger = logging.getLogger("inercia.ai.llm")

T = TypeVar("T", bound=BaseModel)

GEMINI_FLASH_MODEL: str = "gemini-2.5-flash"
GEMINI_PRO_MODEL: str = "gemini-2.5-pro"
KIMI_FALLBACK_MODEL: str = "moonshotai/kimi-k2.6"
OPENCODE_DEFAULT_MODEL: str = "kimi-k2.6"


@dataclass
class TokenUsage:
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


class StructuredLLM(Generic[T]):
    _gemini_clients: ClassVar[dict[str, Any]] = {}

    def __init__(self) -> None:
        self.usage = TokenUsage()

    def _has_gemini(self) -> bool:
        return bool(get_settings().gemini_api_key)

    def _has_opencode(self) -> bool:
        return bool(get_settings().opencode_api_key)

    def _is_quota_error(self, exc: Exception) -> bool:
        message = str(exc)
        return "RESOURCE_EXHAUSTED" in message or "429" in message or "quota" in message.lower()

    def _is_non_retryable_error(self, exc: Exception) -> bool:
        message = str(exc).lower()
        return (
            "retryable\":false" in message
            or "do not retry" in message
            or "browser_signature_banned" in message
            or "error 1010" in message
        )

    @classmethod
    def _get_gemini_client(cls, api_key: str) -> Any:
        client = cls._gemini_clients.get(api_key)
        if client is not None:
            return client
        from google import genai

        client = genai.Client(api_key=api_key)
        cls._gemini_clients[api_key] = client
        return client

    def _generate_sync(
        self,
        model: str,
        system_prompt: str,
        user_prompt: str,
        response_model: type[T],
    ) -> T:
        settings = get_settings()
        client = self._get_gemini_client(settings.gemini_api_key)
        response = client.models.generate_content(
            model=model,
            contents=user_prompt,
            config={
                "system_instruction": system_prompt,
                "response_mime_type": "application/json",
                "response_schema": response_model,
            },
        )
        usage_metadata = getattr(response, "usage_metadata", None)
        if usage_metadata is not None:
            self.usage.prompt_tokens += int(getattr(usage_metadata, "prompt_token_count", 0) or 0)
            self.usage.completion_tokens += int(getattr(usage_metadata, "candidates_token_count", 0) or 0)
            self.usage.total_tokens += int(getattr(usage_metadata, "total_token_count", 0) or 0)
        parsed = getattr(response, "parsed", None)
        if parsed is not None:
            return response_model.model_validate(parsed)
        return response_model.model_validate_json(str(response.text))

    def _generate_opencode_sync(
        self,
        model: str,
        system_prompt: str,
        user_prompt: str,
        response_model: type[T],
    ) -> T:
        settings = get_settings()
        schema = response_model.model_json_schema()
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {
                    "role": "user",
                    "content": (
                        f"{user_prompt}\n\nReturn only JSON matching this schema:\n"
                        f"{json.dumps(schema, ensure_ascii=False)}"
                    ),
                },
            ],
            "temperature": 0.4,
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": response_model.__name__,
                    "schema": schema,
                    "strict": True,
                },
            },
        }
        body = json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(
            settings.opencode_base_url,
            data=body,
            headers={
                "Authorization": f"Bearer {settings.opencode_api_key}",
                "Content-Type": "application/json",
                "Accept": "application/json",
                "Accept-Language": "en-US,en;q=0.9",
                "User-Agent": settings.opencode_user_agent,
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                data = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"OpenCode request failed with HTTP {exc.code}: {detail}") from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(f"OpenCode request failed: {exc.reason}") from exc

        choices = data.get("choices", [])
        if not choices:
            raise RuntimeError("OpenCode response did not include choices.")
        message = choices[0].get("message", {})
        content = message.get("content", "")
        if isinstance(content, list):
            content = "".join(str(part.get("text", "")) for part in content if isinstance(part, dict))
        if not isinstance(content, str) or not content.strip():
            raise RuntimeError("OpenCode response did not include message content.")
        return response_model.model_validate_json(content)

    async def generate_opencode_structured(
        self,
        model: str,
        system_prompt: str,
        user_prompt: str,
        response_model: type[T],
        fallback_factory: Callable[[], T],
        max_attempts: int = 2,
    ) -> T:
        if not self._has_opencode():
            logger.info("OPENCODE_API_KEY is not set; using offline structured fallback for %s", model)
            return fallback_factory()

        delay = 1.0
        last_error: Optional[Exception] = None
        for attempt in range(1, max_attempts + 1):
            try:
                return await asyncio.to_thread(
                    self._generate_opencode_sync,
                    model,
                    system_prompt,
                    user_prompt,
                    response_model,
                )
            except Exception as exc:
                last_error = exc
                logger.warning("OpenCode structured call failed | model=%s | attempt=%d | error=%s", model, attempt, exc)
                if self._is_non_retryable_error(exc):
                    logger.warning("OpenCode returned a non-retryable error; skipping retries | model=%s", model)
                    break
                if self._is_quota_error(exc):
                    logger.warning("OpenCode quota exhausted; skipping retries | model=%s", model)
                    break
                if attempt < max_attempts:
                    await asyncio.sleep(delay)
                    delay *= 2
        logger.error("OpenCode structured unavailable; using fallback | model=%s | error=%s", model, last_error)
        return fallback_factory()

    async def generate_structured(
        self,
        model: str,
        system_prompt: str,
        user_prompt: str,
        response_model: type[T],
        fallback_factory: Callable[[], T],
        max_attempts: int = 3,
    ) -> T:
        if not self._has_gemini():
            logger.info("GEMINI_API_KEY is not set; using offline structured fallback for %s", model)
            return fallback_factory()

        delay = 1.0
        last_error: Optional[Exception] = None
        for attempt in range(1, max_attempts + 1):
            try:
                return await asyncio.to_thread(
                    self._generate_sync,
                    model,
                    system_prompt,
                    user_prompt,
                    response_model,
                )
            except Exception as exc:
                last_error = exc
                logger.warning("Structured LLM call failed | model=%s | attempt=%d | error=%s", model, attempt, exc)
                if self._is_quota_error(exc):
                    logger.warning("Structured LLM quota exhausted; skipping retries | model=%s", model)
                    break
                if attempt < max_attempts:
                    await asyncio.sleep(delay)
                    delay *= 2
        logger.error("Structured LLM unavailable; using fallback | model=%s | error=%s", model, last_error)
        return fallback_factory()


__all__ = [
    "GEMINI_FLASH_MODEL",
    "GEMINI_PRO_MODEL",
    "KIMI_FALLBACK_MODEL",
    "OPENCODE_DEFAULT_MODEL",
    "StructuredLLM",
    "TokenUsage",
]

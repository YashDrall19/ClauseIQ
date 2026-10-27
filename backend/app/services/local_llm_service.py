import asyncio
import logging
from typing import TypeVar

from pydantic import BaseModel, ValidationError

from app.config import get_settings
from app.prompts.contract_prompts import SYSTEM_PROMPT


logger = logging.getLogger(__name__)
T = TypeVar("T", bound=BaseModel)


class LLMUnavailable(RuntimeError):
    pass


class LLMOverloaded(RuntimeError):
    pass


class LLMResponseError(RuntimeError):
    pass


class LocalLLMService:
    """Provider boundary retained under its original import path."""

    def __init__(self) -> None:
        self._semaphore = asyncio.Semaphore(get_settings().ai_max_concurrent_requests)

    async def is_available(self) -> bool:
        settings = get_settings()
        return bool(settings.gemini_api_key if settings.ai_provider == "gemini" else settings.openai_api_key)

    async def generate(self, user_prompt: str, response_model: type[T]) -> T:
        settings = get_settings()
        try:
            await asyncio.wait_for(self._semaphore.acquire(), timeout=0.1)
        except TimeoutError as exc:
            raise LLMOverloaded("AI inference is busy; try again shortly.") from exc
        try:
            content = await asyncio.wait_for(
                asyncio.to_thread(self._generate_sync, user_prompt, response_model),
                timeout=settings.ai_timeout_seconds,
            )
        except TimeoutError as exc:
            raise LLMUnavailable("The configured AI provider timed out.") from exc
        except LLMUnavailable:
            raise
        except Exception as exc:
            logger.exception("AI provider request failed")
            status_code = getattr(exc, "code", None)
            provider = settings.ai_provider.capitalize()
            detail = f"{provider} request failed"
            if status_code:
                detail += f" (HTTP {status_code})"
            raise LLMUnavailable(f"{detail}: {exc}") from exc
        finally:
            self._semaphore.release()
        try:
            return response_model.model_validate_json(content)
        except (ValidationError, ValueError, TypeError) as exc:
            logger.warning("AI provider returned schema-invalid JSON")
            raise LLMResponseError("The AI provider returned an invalid structured response.") from exc

    @staticmethod
    def _generate_sync(user_prompt: str, response_model: type[T]) -> str:
        settings = get_settings()
        prompt = f"{SYSTEM_PROMPT}\n\n{user_prompt}"
        if settings.ai_provider == "gemini":
            if not settings.gemini_api_key:
                raise LLMUnavailable("GEMINI_API_KEY is not configured.")
            from google import genai
            from google.genai import types

            client = genai.Client(api_key=settings.gemini_api_key)
            response = client.models.generate_content(
                model=settings.gemini_model,
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=response_model,
                    temperature=0.1,
                ),
            )
            if not response.text:
                raise LLMResponseError("Gemini returned an empty response.")
            return response.text

        if not settings.openai_api_key:
            raise LLMUnavailable("OPENAI_API_KEY is not configured.")
        from openai import OpenAI

        response = OpenAI(api_key=settings.openai_api_key).chat.completions.create(
            model=settings.openai_model,
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"},
            temperature=0.1,
        )
        content = response.choices[0].message.content
        if not content:
            raise LLMResponseError("OpenAI returned an empty response.")
        return content


local_llm_service = LocalLLMService()

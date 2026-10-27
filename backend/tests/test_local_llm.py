import asyncio

import pytest

from app.schemas.answer import ModelAnswer
from app.services.local_llm_service import LLMResponseError, LLMUnavailable, LocalLLMService


def test_malformed_llm_json_is_rejected(monkeypatch):
    monkeypatch.setattr(LocalLLMService, "_generate_sync", staticmethod(lambda *_: "not-json"))
    with pytest.raises(LLMResponseError):
        asyncio.run(LocalLLMService().generate("question", ModelAnswer))


def test_missing_provider_key_is_reported(monkeypatch):
    monkeypatch.setattr(
        "app.services.local_llm_service.get_settings",
        lambda: type("Settings", (), {"ai_provider": "gemini", "gemini_api_key": None})(),
    )
    with pytest.raises(LLMUnavailable, match="GEMINI_API_KEY is not configured"):
        LocalLLMService._generate_sync("question", ModelAnswer)

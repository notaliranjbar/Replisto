"""Minimal client for OpenAI-compatible chat completion APIs.

Works with OpenAI directly and with gateways that serve other models (Claude, Gemini, ...)
behind the same API shape. Only `base_url`, key and model name change between them.
"""

import base64
import re
from dataclasses import dataclass, field
from typing import Any

import httpx

from app.core.config import Settings, get_settings


class LLMError(Exception):
    def __init__(self, message: str, *, retryable: bool) -> None:
        super().__init__(message)
        self.retryable = retryable


class LLMNotConfiguredError(LLMError):
    def __init__(self) -> None:
        super().__init__("LLM_API_KEY / LLM_MODEL are not set", retryable=False)


@dataclass
class Usage:
    prompt_tokens: int = 0
    completion_tokens: int = 0

    def add(self, raw: dict[str, Any] | None) -> None:
        if raw:
            self.prompt_tokens += int(raw.get("prompt_tokens") or 0)
            self.completion_tokens += int(raw.get("completion_tokens") or 0)


@dataclass
class ChatResult:
    # The assistant message as returned: {"role", "content", "tool_calls"?}
    message: dict[str, Any]
    usage: dict[str, Any] = field(default_factory=dict)

    @property
    def content(self) -> str:
        return (self.message.get("content") or "").strip()

    @property
    def tool_calls(self) -> list[dict[str, Any]]:
        return self.message.get("tool_calls") or []


class LLMClient:
    def __init__(self, http: httpx.AsyncClient, settings: Settings | None = None) -> None:
        self._http = http
        self._settings = settings or get_settings()

    @property
    def configured(self) -> bool:
        return self._settings.llm_configured

    async def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        *,
        model: str | None = None,
        max_tokens: int | None = None,
        tool_choice: str | None = None,
    ) -> ChatResult:
        """`tool_choice` names a tool the model must call (for structured output)."""
        if not self.configured:
            raise LLMNotConfiguredError()
        body: dict[str, Any] = {
            "model": model or self._settings.llm_model,
            "messages": messages,
            "temperature": self._settings.llm_temperature,
            "max_tokens": max_tokens or self._settings.llm_max_output_tokens,
        }
        if tools:
            body["tools"] = tools
        if tools and tool_choice:
            body["tool_choice"] = {"type": "function", "function": {"name": tool_choice}}
        data = await self._post("/chat/completions", body)
        try:
            choice = data["choices"][0]
            return ChatResult(message=choice["message"], usage=data.get("usage") or {})
        except (KeyError, IndexError, TypeError):
            raise LLMError("malformed response from LLM provider", retryable=True) from None

    async def extract_text_from_image(self, image: bytes, mime_type: str) -> str:
        """Transcribe an uploaded image (price list, menu, info card) into plain text."""
        data_url = f"data:{mime_type};base64,{base64.b64encode(image).decode()}"
        result = await self.chat(
            [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": (
                                "This image was uploaded by an online shop owner as information "
                                "for their customer-support assistant. Transcribe ALL of its "
                                "text and information faithfully in the original language. "
                                "Keep prices, sizes, and numbers exact. Use "
                                "simple lines or a list for tables. Output only the content."
                            ),
                        },
                        {"type": "image_url", "image_url": {"url": data_url}},
                    ],
                }
            ],
            model=self._settings.llm_vision_model or None,
            max_tokens=2000,
        )
        return result.content

    async def _post(self, path: str, body: dict[str, Any]) -> dict[str, Any]:
        url = self._settings.llm_base_url.rstrip("/") + path
        # Newer models reject some classic parameters (reasoning models want
        # max_completion_tokens and only the default temperature). Adapt and resend instead
        # of failing, so switching models is only a config change.
        for _ in range(len(_PARAMETER_FIXES) + 1):
            try:
                resp = await self._http.post(
                    url,
                    json=body,
                    headers={"Authorization": f"Bearer {self._settings.llm_api_key}"},
                    timeout=self._settings.llm_timeout_seconds,
                )
            except httpx.HTTPError as exc:
                raise LLMError(f"network error: {type(exc).__name__}", retryable=True) from None
            if resp.status_code == 400 and _fix_rejected_parameter(body, resp.text):
                continue
            break
        if resp.status_code == 429 or resp.status_code >= 500:
            raise LLMError(f"provider busy (HTTP {resp.status_code})", retryable=True)
        if resp.is_error:
            raise LLMError(
                f"provider rejected request (HTTP {resp.status_code}): {resp.text[:300]}",
                retryable=False,
            )
        try:
            return resp.json()
        except ValueError:
            raise LLMError("non-JSON response from LLM provider", retryable=True) from None


def _rename_max_tokens(body: dict[str, Any]) -> None:
    body["max_completion_tokens"] = body.pop("max_tokens")


_PARAMETER_FIXES = {
    "max_tokens": _rename_max_tokens,
    "temperature": lambda body: body.pop("temperature"),
}


def _fix_rejected_parameter(body: dict[str, Any], error_text: str) -> bool:
    """If a 400 names a parameter we can drop or rename, change `body` and return True."""
    text = error_text.lower()
    for param, fix in _PARAMETER_FIXES.items():
        if param in body and re.search(rf"\b{param}\b", text):
            fix(body)
            return True
    return False

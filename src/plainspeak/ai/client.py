"""Thin wrapper over the Anthropic SDK so the agent code can be tested with a fake."""

import json
import logging
from typing import Any, Protocol

import anthropic

from plainspeak.config import Settings

log = logging.getLogger(__name__)

FALLBACK_BETA = "server-side-fallback-2026-07-01"


class AIError(RuntimeError):
    """Claude could not produce a usable response. The message is safe to show users."""


class LLM(Protocol):
    def create(
        self,
        *,
        system: str,
        messages: list[dict[str, Any]],
        output_schema: dict[str, Any],
        tools: list[dict[str, Any]] | None = None,
    ) -> Any: ...


class ClaudeClient:
    def __init__(self, settings: Settings) -> None:
        # With no explicit key the SDK resolves ANTHROPIC_API_KEY / an `ant auth login` profile.
        self._client = anthropic.Anthropic(api_key=settings.anthropic_api_key or None)
        self._model = settings.anthropic_model
        self._effort = settings.anthropic_effort
        self._fallbacks = settings.anthropic_fallbacks

    def create(
        self,
        *,
        system: str,
        messages: list[dict[str, Any]],
        output_schema: dict[str, Any],
        tools: list[dict[str, Any]] | None = None,
    ) -> Any:
        output_config: dict[str, Any] = {"format": {"type": "json_schema", "schema": output_schema}}
        if self._effort:
            output_config["effort"] = self._effort
        kwargs: dict[str, Any] = {
            "model": self._model,
            "max_tokens": 16000,
            "system": system,
            "messages": messages,
            "output_config": output_config,
        }
        if tools:
            kwargs["tools"] = tools
        try:
            if self._fallbacks:
                response = self._client.beta.messages.create(
                    **kwargs, fallbacks=self._fallbacks, betas=[FALLBACK_BETA]
                )
            else:
                response = self._client.messages.create(**kwargs)
        except anthropic.AuthenticationError as e:
            raise AIError("Anthropic credentials are missing or invalid.") from e
        except TypeError as e:
            # The SDK raises TypeError when no credential source can be resolved.
            if "authentication" not in str(e):
                raise
            raise AIError(
                "Anthropic credentials are missing. Set ANTHROPIC_API_KEY in .env."
            ) from e
        except anthropic.RateLimitError as e:
            raise AIError("Claude is rate limited. Try again shortly.") from e
        except anthropic.BadRequestError as e:
            log.error("Claude rejected the request: %s", e.message)
            raise AIError("Claude rejected the request. Check the server log.") from e
        except anthropic.APIStatusError as e:
            log.error("Claude API error %s (request %s)", e.status_code, e.request_id)
            raise AIError(f"Claude API error ({e.status_code}).") from e
        except anthropic.APIConnectionError as e:
            raise AIError("Could not reach the Claude API.") from e
        log.info("Claude response %s stop_reason=%s", response.id, response.stop_reason)
        return response


def parse_json_output(response: Any) -> dict[str, Any]:
    """Read the structured JSON result from a final (non-tool-use) response."""
    if response.stop_reason == "refusal":
        raise AIError("Claude declined to answer this request.")
    if response.stop_reason == "max_tokens":
        raise AIError("Claude's response was cut off.")
    text = next((b.text for b in response.content if b.type == "text"), None)
    if text is None:
        raise AIError("Claude returned no text output.")
    try:
        return json.loads(text)
    except json.JSONDecodeError as e:
        raise AIError("Claude returned invalid JSON.") from e

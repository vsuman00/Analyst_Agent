"""
llm_client.py — Layer 3 Utility
---------------------------------
Centralised OpenAI API wrapper for the Analyst-Agent pipeline.

All LLM calls in the system MUST route through this module.
This ensures:
  - Single point of API key management (via OPENAI_API_KEY env var)
  - Consistent retry / error handling
  - Swappable model configuration via OPENAI_MODEL env var
  - Strict JSON-only responses enforced via response_format
  - Deterministic temperature=0 by default

Environment Variables (set in .env or system env):
  OPENAI_API_KEY   Required. Your OpenAI secret key.
  OPENAI_MODEL     Optional. Default: "gpt-4o-mini"
  OPENAI_MAX_TOKENS Optional. Default: 2048

Usage:
    from app.utils.llm_client import llm_json_call, llm_text_call

    # Returns parsed dict (JSON mode enforced)
    result = llm_json_call(
        system_prompt="You are an analyst.",
        user_prompt="Summarise: {data}",
    )

    # Returns raw string
    narrative = llm_text_call(
        system_prompt="You are a technical writer.",
        user_prompt="Write an executive summary for: {data}",
    )
"""

from __future__ import annotations

import os
import json
import time
from typing import Any, Dict, Optional

try:
    from openai import OpenAI, APIError, RateLimitError, APIConnectionError
except ImportError:
    raise ImportError(
        "openai package is not installed. Run: pip install openai>=1.0.0"
    )

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # python-dotenv is optional; env vars can be set directly

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

_API_KEY    = os.environ.get("OPENAI_API_KEY", "")
_MODEL      = os.environ.get("OPENAI_MODEL",      "gpt-4o-mini")
_MAX_TOKENS = int(os.environ.get("OPENAI_MAX_TOKENS", "2048"))
_TEMPERATURE = 0       # Deterministic output — do NOT raise without explicit reason
_MAX_RETRIES = 3
_RETRY_DELAY = 2       # seconds between retries
_JSON_MIN_COMPLETION_TOKENS = int(os.environ.get("OPENAI_JSON_MIN_TOKENS", "4096"))
_JSON_COMPLETION_TOKEN_MULTIPLIER = int(os.environ.get("OPENAI_JSON_TOKEN_MULTIPLIER", "3"))
_REASONING_EFFORT = os.environ.get("OPENAI_REASONING_EFFORT", "minimal")
_VERBOSITY = os.environ.get("OPENAI_VERBOSITY", "low")

if not _API_KEY:
    raise EnvironmentError(
        "OPENAI_API_KEY environment variable is not set.\n"
        "  1. Create a .env file in the project root with: OPENAI_API_KEY=sk-...\n"
        "  2. Or export it in your shell: export OPENAI_API_KEY=sk-..."
    )

_client = OpenAI(api_key=_API_KEY)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _call_with_retry(
    messages: list,
    response_format: Optional[Dict] = None,
    max_tokens: int = _MAX_TOKENS,
) -> str:
    """
    Execute a chat completion with exponential-backoff retry on transient errors.
    Returns the raw string content of the first choice.
    """
    # Newer OpenAI models (o1, o3, o4, gpt-5, etc.) require
    # 'max_completion_tokens' instead of the legacy 'max_tokens' param,
    # and do not accept the 'temperature' parameter.
    _model_lower = _MODEL.lower()
    _is_gpt5 = "gpt-5" in _model_lower
    _uses_new_param = (
        _model_lower.startswith(("o1", "o3", "o4"))
        or _is_gpt5
    )

    kwargs: Dict[str, Any] = {
        "model":       _MODEL,
        "messages":    messages,
    }
    # Only set temperature for models that support it
    if not _uses_new_param:
        kwargs["temperature"] = _TEMPERATURE
    # Select the correct token-limit parameter for the model family
    if _uses_new_param:
        kwargs["max_completion_tokens"] = _completion_token_limit(
            max_tokens=max_tokens,
            is_json_call=bool(response_format),
        )
    else:
        kwargs["max_tokens"] = max_tokens
    if _is_gpt5:
        kwargs["reasoning_effort"] = _REASONING_EFFORT
        kwargs["verbosity"] = _VERBOSITY
    if response_format:
        kwargs["response_format"] = response_format

    last_error: Exception = RuntimeError("Unknown error")
    for attempt in range(1, _MAX_RETRIES + 1):
        try:
            response = _client.chat.completions.create(**kwargs)
            choice = response.choices[0]
            content = choice.message.content or ""
            if not content.strip():
                finish_reason = getattr(choice, "finish_reason", "unknown")
                usage = getattr(response, "usage", None)
                usage_summary = _format_usage(usage)
                token_limit = kwargs.get("max_completion_tokens", kwargs.get("max_tokens"))
                raise RuntimeError(
                    "OpenAI returned empty content "
                    f"(model={_MODEL}, finish_reason={finish_reason}, "
                    f"requested_max_tokens={max_tokens}, token_limit={token_limit}, "
                    f"usage={usage_summary})"
                )
            return content
        except RateLimitError as e:
            last_error = e
            wait = _RETRY_DELAY * attempt
            print(f"[LLM] Rate limit hit. Retrying in {wait}s (attempt {attempt}/{_MAX_RETRIES})")
            time.sleep(wait)
        except APIConnectionError as e:
            last_error = e
            wait = _RETRY_DELAY * attempt
            print(f"[LLM] Connection error. Retrying in {wait}s (attempt {attempt}/{_MAX_RETRIES})")
            time.sleep(wait)
        except APIError as e:
            # Non-transient API errors — fail immediately
            raise RuntimeError(f"OpenAI API error: {e}") from e

    raise RuntimeError(
        f"OpenAI call failed after {_MAX_RETRIES} attempts: {last_error}"
    )


def _format_usage(usage: Any) -> str:
    """Return compact token usage for diagnostics without depending on SDK internals."""
    if usage is None:
        return "unknown"

    prompt_tokens = getattr(usage, "prompt_tokens", None)
    completion_tokens = getattr(usage, "completion_tokens", None)
    total_tokens = getattr(usage, "total_tokens", None)

    parts = []
    if prompt_tokens is not None:
        parts.append(f"prompt={prompt_tokens}")
    if completion_tokens is not None:
        parts.append(f"completion={completion_tokens}")
    if total_tokens is not None:
        parts.append(f"total={total_tokens}")
    return ", ".join(parts) if parts else "unknown"


def _completion_token_limit(max_tokens: int, is_json_call: bool) -> int:
    """
    GPT-5-style chat completion limits include hidden reasoning plus visible text.
    JSON callers pass visible-output sized budgets, so reserve extra headroom.
    """
    if not is_json_call:
        return max_tokens

    scaled_limit = max_tokens * max(1, _JSON_COMPLETION_TOKEN_MULTIPLIER)
    return max(max_tokens, _JSON_MIN_COMPLETION_TOKENS, scaled_limit)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def llm_json_call(
    system_prompt: str,
    user_prompt: str,
    max_tokens: int = _MAX_TOKENS,
) -> Dict[str, Any]:
    """
    Make an LLM call with JSON mode enforced.

    Returns a parsed Python dict.
    Raises ValueError if the response is not valid JSON.

    Rules:
      - temperature is fixed at 0 (deterministic)
      - response_format={"type": "json_object"} is always set
      - The system_prompt MUST instruct the model to return JSON only
    """
    messages = [
        {"role": "system",  "content": system_prompt},
        {"role": "user",    "content": user_prompt},
    ]
    raw = _call_with_retry(
        messages,
        response_format={"type": "json_object"},
        max_tokens=max_tokens,
    )
    try:
        return json.loads(raw)
    except json.JSONDecodeError as e:
        raise ValueError(
            f"LLM returned invalid JSON: {e}\nRaw response: {raw[:500]}"
        ) from e


def llm_text_call(
    system_prompt: str,
    user_prompt: str,
    max_tokens: int = _MAX_TOKENS,
) -> str:
    """
    Make an LLM call expecting free-form text (Markdown, prose, etc.).

    Returns the raw string response.
    """
    messages = [
        {"role": "system",  "content": system_prompt},
        {"role": "user",    "content": user_prompt},
    ]
    return _call_with_retry(messages, max_tokens=max_tokens)

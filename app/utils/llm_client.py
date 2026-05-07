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
_TEMPERATURE = 0       # Deterministic — do NOT raise without explicit reason
_MAX_RETRIES = 3
_RETRY_DELAY = 2       # seconds between retries

# Lazy init: if API key is missing, _client is None.
# All callers check for None and fall back to deterministic mode gracefully.
_client = None

if not _API_KEY:
    import warnings
    warnings.warn(
        "OPENAI_API_KEY is not set. LLM features are disabled. "
        "Pipeline will run in deterministic-only mode. "
        "Set OPENAI_API_KEY in .env to enable LLM BRD composition.",
        stacklevel=2,
    )
else:
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
    kwargs: Dict[str, Any] = {
        "model":       _MODEL,
        "messages":    messages,
        "temperature": _TEMPERATURE,
        "max_tokens":  max_tokens,
    }
    if response_format:
        kwargs["response_format"] = response_format

    if _client is None:
        raise RuntimeError(
            "LLM client is not initialised. "
            "Set OPENAI_API_KEY in your .env file to enable LLM features."
        )

    last_error: Exception = RuntimeError("Unknown error")
    for attempt in range(1, _MAX_RETRIES + 1):
        try:
            response = _client.chat.completions.create(**kwargs)
            return response.choices[0].message.content or ""
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

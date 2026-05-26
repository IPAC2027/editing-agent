"""OpenAI-compatible LLM backend.

Supports any server that implements the OpenAI ``/v1/chat/completions`` endpoint:
- Local:      Ollama  (LLM_BASE_URL=http://localhost:11434/v1, LLM_API_KEY=ollama)
- Commercial: OpenAI  (LLM_BASE_URL=https://api.openai.com/v1)
              Anthropic via their OpenAI-compatible shim, etc.

Configuration (environment / .env)
-----------------------------------
LLM_ENABLED   = false          # set true to enable
LLM_BASE_URL  = http://localhost:11434/v1
LLM_MODEL     = llama3
LLM_API_KEY   = ollama
"""

from __future__ import annotations

import os

from openai import OpenAI


def _get_client() -> OpenAI:
    return OpenAI(
        base_url=os.environ.get("LLM_BASE_URL", "http://localhost:11434/v1"),
        api_key=os.environ.get("LLM_API_KEY", "ollama"),
    )


def is_enabled() -> bool:
    return os.environ.get("LLM_ENABLED", "false").lower() in ("1", "true", "yes")


def chat(system: str, user: str, *, model: str | None = None) -> str:
    """Send a chat completion request and return the assistant message text.

    Raises ``RuntimeError`` if ``LLM_ENABLED`` is not set.
    """
    if not is_enabled():
        raise RuntimeError("LLM is disabled. Set LLM_ENABLED=true to use LLM features.")
    client = _get_client()
    m = model or os.environ.get("LLM_MODEL", "llama3")
    response = client.chat.completions.create(
        model=m,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    )
    return response.choices[0].message.content or ""

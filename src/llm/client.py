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


def chat(
    system: str,
    user: str,
    *,
    model: str | None = None,
    json_mode: bool = False,
    temperature: float | None = None,
    timeout: float | None = None,
) -> str:
    """Send a chat completion request and return the assistant message text.

    ``json_mode`` asks the server to constrain the output to JSON.  Both Ollama
    and LM Studio support this through the OpenAI-compatible
    ``response_format`` field; a server that does not is tolerated, because the
    caller parses defensively either way.  Constraining the decoding rather
    than only the prompt is what makes a small local model usable for
    classification: a malformed answer becomes a parse failure instead of
    something to salvage.

    Raises ``RuntimeError`` if ``LLM_ENABLED`` is not set.
    """
    if not is_enabled():
        raise RuntimeError("LLM is disabled. Set LLM_ENABLED=true to use LLM features.")
    client = _get_client()
    name = model or os.environ.get("LLM_MODEL", "llama3")
    kwargs: dict = {
        "model": name,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "temperature": 0.0 if temperature is None else temperature,
        "timeout": timeout if timeout is not None
                   else float(os.environ.get("LLM_TIMEOUT", "60")),
    }
    if json_mode:
        kwargs["response_format"] = {"type": "json_object"}
    try:
        response = client.chat.completions.create(**kwargs)
    except TypeError:
        kwargs.pop("response_format", None)
        response = client.chat.completions.create(**kwargs)
    return response.choices[0].message.content or ""

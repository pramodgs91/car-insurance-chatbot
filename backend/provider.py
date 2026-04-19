"""
LLM Provider abstraction — Claude (Anthropic) and OpenAI.

simple_complete(): no-tool, non-streaming completions for voice summariser,
intent classifier, and QC.  Caller supplies `family` so the right SDK is used.
"""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env", override=True)

_anthropic_client = None
_openai_client = None


def _get_anthropic():
    global _anthropic_client
    if _anthropic_client is None:
        from anthropic import AsyncAnthropic
        _anthropic_client = AsyncAnthropic(max_retries=3)
    return _anthropic_client


def _get_openai():
    global _openai_client
    if _openai_client is None:
        from openai import AsyncOpenAI
        key = os.environ.get("OPENAI_API_KEY")
        if not key:
            raise ValueError("OPENAI_API_KEY is not set — cannot use OpenAI family")
        _openai_client = AsyncOpenAI(api_key=key, max_retries=3)
    return _openai_client


async def simple_complete(
    model: str,
    user_message: str,
    system: str | None = None,
    max_tokens: int = 512,
    family: str = "claude",
) -> str:
    """Single-turn text completion — no tools, no streaming."""
    if family == "openai":
        client = _get_openai()
        msgs = []
        if system:
            msgs.append({"role": "system", "content": system})
        msgs.append({"role": "user", "content": user_message})
        resp = await client.chat.completions.create(
            model=model,
            messages=msgs,
            max_tokens=max_tokens,
        )
        return resp.choices[0].message.content or ""
    else:
        client = _get_anthropic()
        kwargs: dict = {
            "model": model,
            "max_tokens": max_tokens,
            "messages": [{"role": "user", "content": user_message}],
        }
        if system:
            kwargs["system"] = system
        resp = await client.messages.create(**kwargs)
        return resp.content[0].text


def openai_client():
    """Expose the raw OpenAI async client for the agent's streaming loop."""
    return _get_openai()


def anthropic_client():
    """Expose the raw Anthropic async client for the agent's streaming loop."""
    return _get_anthropic()

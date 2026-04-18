"""
Shared model-family defaults for the chat, voice, and QC stack.
"""
from __future__ import annotations

import os


MODEL_FAMILIES = ("claude", "openai")

MODEL_TASK_LABELS = {
    "chat_agent": "Chat agent",
    "voice_summarizer": "Voice summariser",
    "intent_classifier": "Intent classifier",
    "quality_checker": "Quality checker",
    "document_extraction": "Document extraction",
}


DEFAULT_MODEL_FAMILY = os.environ.get("MODEL_FAMILY", "claude").strip().lower() or "claude"
if DEFAULT_MODEL_FAMILY not in MODEL_FAMILIES:
    DEFAULT_MODEL_FAMILY = "claude"


DEFAULT_MODELS = {
    "claude": {
        "chat_agent": os.environ.get("CLAUDE_MODEL", "claude-haiku-4-5-20251001"),
        "voice_summarizer": os.environ.get("CLAUDE_VOICE_MODEL", "claude-haiku-4-5-20251001"),
        "intent_classifier": os.environ.get("CLAUDE_CLASSIFIER_MODEL", "claude-haiku-4-5-20251001"),
        "quality_checker": os.environ.get("CLAUDE_QC_MODEL", "claude-haiku-4-5-20251001"),
        "document_extraction": os.environ.get("EXTRACTION_MODEL", "claude-sonnet-4-20250514"),
    },
    "openai": {
        "chat_agent": os.environ.get("OPENAI_CHAT_MODEL", "gpt-4.1"),
        "voice_summarizer": os.environ.get("OPENAI_VOICE_MODEL", "gpt-4o-mini"),
        "intent_classifier": os.environ.get("OPENAI_CLASSIFIER_MODEL", "gpt-4o-mini"),
        "quality_checker": os.environ.get("OPENAI_QC_MODEL", "gpt-4o-mini"),
        "document_extraction": os.environ.get("OPENAI_EXTRACTION_MODEL", "gpt-4o-mini"),
    },
}


def default_task_models(family: str) -> dict[str, str]:
    chosen = family if family in DEFAULT_MODELS else DEFAULT_MODEL_FAMILY
    return dict(DEFAULT_MODELS[chosen])

"""
Runtime configuration store — tone, verbosity, feature toggles, voice
controls, and provider/model routing. All changes take effect immediately
and persist to disk.
"""
from __future__ import annotations

import json
import threading
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path

from model_defaults import (
    DEFAULT_MODEL_FAMILY,
    MODEL_FAMILIES,
    MODEL_TASK_LABELS,
    default_task_models,
)


STYLE_PRESETS = {
    "salesy": {
        "tone": "warm, enthusiastic, urgency-aware",
        "verbosity": "medium",
        "persuasion": "high",
        "description": "Pushes toward conversion with social proof, urgency, value framing.",
    },
    "simple": {
        "tone": "plain, friendly, jargon-free",
        "verbosity": "low",
        "persuasion": "low",
        "description": "Clear, short answers — best for first-time buyers.",
    },
    "crisp": {
        "tone": "professional, direct",
        "verbosity": "low",
        "persuasion": "medium",
        "description": "Fast, no-fluff responses with bullet points.",
    },
    "elaborate": {
        "tone": "thorough, educational",
        "verbosity": "high",
        "persuasion": "medium",
        "description": "Explains the why behind recommendations in depth.",
    },
    "chatty": {
        "tone": "casual, conversational, empathetic",
        "verbosity": "medium",
        "persuasion": "low",
        "description": "Natural conversation, feels like chatting with a friend.",
    },
}


VOICE_LANGUAGES = ("english", "hindi")
VOICE_TONES = ("friendly", "professional", "sales")
VOICE_DETAIL_LEVELS = ("quick", "moderate", "detailed")
VOICE_SPEEDS = ("slow", "normal", "fast")


@dataclass
class InstructionBlock:
    block_id: str
    title: str
    content: str
    enabled: bool = True


@dataclass
class VoiceSettings:
    output_enabled: bool = False
    input_enabled: bool = False
    language: str = "english"
    tone: str = "friendly"
    detail_level: str = "quick"
    auto_play: bool = False
    interruptible: bool = True
    speed: str = "normal"


CURRENT_DEFAULTS_VERSION = 3


@dataclass
class RuntimeConfigData:
    style: str = "salesy"
    rag_enabled: bool = True
    evaluation_loop_enabled: bool = False
    latency_optimizations_enabled: bool = True
    custom_instructions: list[InstructionBlock] = field(default_factory=list)
    model_family: str = DEFAULT_MODEL_FAMILY
    task_models: dict[str, str] = field(default_factory=lambda: default_task_models(DEFAULT_MODEL_FAMILY))
    voice: VoiceSettings = field(default_factory=VoiceSettings)
    defaults_version: int = CURRENT_DEFAULTS_VERSION


class RuntimeConfig:
    """Thread-safe, persisted runtime config."""

    def __init__(self, persist_path: Path):
        self.persist_path = persist_path
        self._lock = threading.RLock()
        self._data = RuntimeConfigData()
        self._load()

    def snapshot(self) -> dict:
        with self._lock:
            return {
                "style": self._data.style,
                "style_preset": STYLE_PRESETS.get(self._data.style, STYLE_PRESETS["salesy"]),
                "available_styles": list(STYLE_PRESETS.keys()),
                "rag_enabled": self._data.rag_enabled,
                "evaluation_loop_enabled": self._data.evaluation_loop_enabled,
                "latency_optimizations_enabled": self._data.latency_optimizations_enabled,
                "custom_instructions": [asdict(b) for b in self._data.custom_instructions],
                "model_family": self._data.model_family,
                "available_model_families": list(MODEL_FAMILIES),
                "task_models": dict(self._data.task_models),
                "task_model_labels": dict(MODEL_TASK_LABELS),
                "voice": asdict(self._data.voice),
                "voice_languages": list(VOICE_LANGUAGES),
                "voice_tones": list(VOICE_TONES),
                "voice_detail_levels": list(VOICE_DETAIL_LEVELS),
                "voice_speeds": list(VOICE_SPEEDS),
            }

    def public_snapshot(self) -> dict:
        snap = self.snapshot()
        return {
            "voice": snap["voice"],
            "voice_languages": snap["voice_languages"],
            "voice_tones": snap["voice_tones"],
            "voice_detail_levels": snap["voice_detail_levels"],
            "voice_speeds": snap["voice_speeds"],
            "model_family": snap["model_family"],
        }

    def update_style(self, style: str) -> None:
        with self._lock:
            if style not in STYLE_PRESETS:
                raise ValueError(f"Unknown style: {style}")
            self._data.style = style
            self._persist()

    def toggle_feature(self, feature: str, enabled: bool) -> None:
        valid = {"rag_enabled", "evaluation_loop_enabled", "latency_optimizations_enabled"}
        if feature not in valid:
            raise ValueError(f"Unknown feature: {feature}")
        with self._lock:
            setattr(self._data, feature, bool(enabled))
            self._persist()

    def add_instruction(self, title: str, content: str, enabled: bool = True) -> str:
        block_id = uuid.uuid4().hex[:10]
        with self._lock:
            self._data.custom_instructions.append(
                InstructionBlock(block_id=block_id, title=title, content=content, enabled=enabled)
            )
            self._persist()
        return block_id

    def update_instruction(
        self,
        block_id: str,
        title: str | None = None,
        content: str | None = None,
        enabled: bool | None = None,
    ) -> bool:
        with self._lock:
            for block in self._data.custom_instructions:
                if block.block_id == block_id:
                    if title is not None:
                        block.title = title
                    if content is not None:
                        block.content = content
                    if enabled is not None:
                        block.enabled = enabled
                    self._persist()
                    return True
        return False

    def delete_instruction(self, block_id: str) -> bool:
        with self._lock:
            before = len(self._data.custom_instructions)
            self._data.custom_instructions = [
                block for block in self._data.custom_instructions if block.block_id != block_id
            ]
            changed = len(self._data.custom_instructions) != before
            if changed:
                self._persist()
            return changed

    def update_voice(self, **patch) -> None:
        valid = {
            "output_enabled",
            "input_enabled",
            "language",
            "tone",
            "detail_level",
            "auto_play",
            "interruptible",
            "speed",
        }
        unknown = set(patch) - valid
        if unknown:
            raise ValueError(f"Unknown voice setting(s): {', '.join(sorted(unknown))}")

        with self._lock:
            voice = self._data.voice
            for key, value in patch.items():
                if value is None:
                    continue
                if key == "language" and value not in VOICE_LANGUAGES:
                    raise ValueError(f"Unknown voice language: {value}")
                if key == "tone" and value not in VOICE_TONES:
                    raise ValueError(f"Unknown voice tone: {value}")
                if key == "detail_level" and value not in VOICE_DETAIL_LEVELS:
                    raise ValueError(f"Unknown voice detail level: {value}")
                if key == "speed" and value not in VOICE_SPEEDS:
                    raise ValueError(f"Unknown voice speed: {value}")
                setattr(voice, key, value)
            self._persist()

    def update_model_family(self, family: str) -> None:
        if family not in MODEL_FAMILIES:
            raise ValueError(f"Unknown model family: {family}")
        with self._lock:
            self._data.model_family = family
            self._data.task_models = default_task_models(family)
            self._persist()

    def update_task_models(self, task_models: dict[str, str]) -> None:
        if not isinstance(task_models, dict):
            raise ValueError("task_models must be an object")
        with self._lock:
            for task, model in task_models.items():
                if task not in MODEL_TASK_LABELS:
                    raise ValueError(f"Unknown task model: {task}")
                value = (model or "").strip()
                if not value:
                    raise ValueError(f"Model name for {task} cannot be empty")
                self._data.task_models[task] = value
            self._persist()

    def _persist(self) -> None:
        self.persist_path.parent.mkdir(parents=True, exist_ok=True)
        with self.persist_path.open("w") as handle:
            json.dump(
                {
                    "style": self._data.style,
                    "rag_enabled": self._data.rag_enabled,
                    "evaluation_loop_enabled": self._data.evaluation_loop_enabled,
                    "latency_optimizations_enabled": self._data.latency_optimizations_enabled,
                    "custom_instructions": [asdict(block) for block in self._data.custom_instructions],
                    "model_family": self._data.model_family,
                    "task_models": dict(self._data.task_models),
                    "voice": asdict(self._data.voice),
                    "defaults_version": self._data.defaults_version,
                },
                handle,
                indent=2,
            )

    def _load(self) -> None:
        if not self.persist_path.exists():
            return
        try:
            with self.persist_path.open() as handle:
                data = json.load(handle)

            self._data.style = data.get("style", self._data.style)
            self._data.rag_enabled = data.get("rag_enabled", self._data.rag_enabled)
            self._data.evaluation_loop_enabled = data.get(
                "evaluation_loop_enabled",
                self._data.evaluation_loop_enabled,
            )
            self._data.latency_optimizations_enabled = data.get(
                "latency_optimizations_enabled",
                self._data.latency_optimizations_enabled,
            )
            self._data.custom_instructions = [
                InstructionBlock(**block) for block in data.get("custom_instructions", [])
            ]

            family = data.get("model_family", self._data.model_family)
            if family in MODEL_FAMILIES:
                self._data.model_family = family
            self._data.task_models = default_task_models(self._data.model_family)
            for task, model in data.get("task_models", {}).items():
                if task in MODEL_TASK_LABELS and isinstance(model, str) and model.strip():
                    self._data.task_models[task] = model.strip()

            voice = data.get("voice", {})
            if isinstance(voice, dict):
                self._data.voice.output_enabled = bool(
                    voice.get("output_enabled", self._data.voice.output_enabled)
                )
                self._data.voice.input_enabled = bool(
                    voice.get("input_enabled", self._data.voice.input_enabled)
                )
                language = voice.get("language", self._data.voice.language)
                tone = voice.get("tone", self._data.voice.tone)
                detail_level = voice.get("detail_level", self._data.voice.detail_level)
                speed = voice.get("speed", self._data.voice.speed)
                self._data.voice.language = language if language in VOICE_LANGUAGES else self._data.voice.language
                self._data.voice.tone = tone if tone in VOICE_TONES else self._data.voice.tone
                self._data.voice.detail_level = (
                    detail_level if detail_level in VOICE_DETAIL_LEVELS else self._data.voice.detail_level
                )
                self._data.voice.auto_play = bool(voice.get("auto_play", self._data.voice.auto_play))
                self._data.voice.interruptible = bool(
                    voice.get("interruptible", self._data.voice.interruptible)
                )
                self._data.voice.speed = speed if speed in VOICE_SPEEDS else self._data.voice.speed

            persisted_version = int(data.get("defaults_version", 1))
            self._data.defaults_version = persisted_version
            if persisted_version < CURRENT_DEFAULTS_VERSION:
                self._migrate_defaults(persisted_version)
        except Exception:
            pass

    def _migrate_defaults(self, from_version: int) -> None:
        if from_version < 2:
            self._data.evaluation_loop_enabled = False
        if from_version < 3:
            if self._data.model_family not in MODEL_FAMILIES:
                self._data.model_family = DEFAULT_MODEL_FAMILY
            merged = default_task_models(self._data.model_family)
            merged.update({k: v for k, v in self._data.task_models.items() if k in MODEL_TASK_LABELS and v})
            self._data.task_models = merged
        self._data.defaults_version = CURRENT_DEFAULTS_VERSION
        self._persist()

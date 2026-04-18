"""
Runtime configuration store — tone, verbosity, feature toggles, system
instruction blocks. All changes take effect immediately (no redeploy).
Persists to JSON on disk so restarts keep state.
"""
from __future__ import annotations
import json
import threading
import uuid
from dataclasses import dataclass, field, asdict
from pathlib import Path


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


@dataclass
class InstructionBlock:
    block_id: str
    title: str
    content: str
    enabled: bool = True


@dataclass
class RuntimeConfigData:
    style: str = "salesy"
    rag_enabled: bool = True
    evaluation_loop_enabled: bool = True
    latency_optimizations_enabled: bool = True
    custom_instructions: list[InstructionBlock] = field(default_factory=list)


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

    def update_instruction(self, block_id: str, title: str | None = None,
                           content: str | None = None, enabled: bool | None = None) -> bool:
        with self._lock:
            for b in self._data.custom_instructions:
                if b.block_id == block_id:
                    if title is not None:
                        b.title = title
                    if content is not None:
                        b.content = content
                    if enabled is not None:
                        b.enabled = enabled
                    self._persist()
                    return True
        return False

    def delete_instruction(self, block_id: str) -> bool:
        with self._lock:
            before = len(self._data.custom_instructions)
            self._data.custom_instructions = [
                b for b in self._data.custom_instructions if b.block_id != block_id
            ]
            changed = len(self._data.custom_instructions) != before
            if changed:
                self._persist()
            return changed

    # ── internal ─────────────────────────────────────────────────────────

    def _persist(self) -> None:
        self.persist_path.parent.mkdir(parents=True, exist_ok=True)
        with self.persist_path.open("w") as f:
            json.dump({
                "style": self._data.style,
                "rag_enabled": self._data.rag_enabled,
                "evaluation_loop_enabled": self._data.evaluation_loop_enabled,
                "latency_optimizations_enabled": self._data.latency_optimizations_enabled,
                "custom_instructions": [asdict(b) for b in self._data.custom_instructions],
            }, f, indent=2)

    def _load(self) -> None:
        if not self.persist_path.exists():
            return
        try:
            with self.persist_path.open() as f:
                data = json.load(f)
            self._data.style = data.get("style", "salesy")
            self._data.rag_enabled = data.get("rag_enabled", True)
            self._data.evaluation_loop_enabled = data.get("evaluation_loop_enabled", True)
            self._data.latency_optimizations_enabled = data.get("latency_optimizations_enabled", True)
            self._data.custom_instructions = [
                InstructionBlock(**b) for b in data.get("custom_instructions", [])
            ]
        except Exception:
            pass

"""
Lightweight voice guide and intent classification helpers.
"""
from __future__ import annotations

import hashlib
import json
from collections import OrderedDict
from typing import Any

from llm import ProviderError


VOICE_GUIDE_SYSTEM = """You are a fast voice guide layered on top of a car insurance chat UI.

Rules:
- You are not the main chat agent.
- Never call tools. Never use retrieval. Never invent facts outside the provided screen context.
- Summarize what is on screen, what matters most, and what the user should do next.
- Speak naturally for audio. Do not read the whole chat message verbatim.
- If the user asks a clarification question, answer only from the visible UI state.
- If the question clearly needs broader insurance knowledge, say it should go through chat.
"""


INTENT_CLASSIFIER_SYSTEM = """Classify the spoken input for a car insurance chat UI.

Return JSON only:
{
  "intent": "clarification" | "response" | "detailed_question" | "ambiguous",
  "reason": "short explanation"
}

Rules:
- clarification: asks about the current screen, field, or next step only
- response: directly answers the bot's last question or picks an option
- detailed_question: needs deeper reasoning, comparison, insurance knowledge, tools, or RAG
- ambiguous: too unclear to trust
"""


DETAIL_TOKEN_LIMITS = {
    "quick": 90,
    "moderate": 150,
    "detailed": 230,
}


def _jsonish(data: Any) -> str:
    return json.dumps(data or {}, ensure_ascii=False, sort_keys=True)


class VoiceService:
    def __init__(self, config, model_router):
        self.config = config
        self.model_router = model_router
        self._summary_cache: OrderedDict[str, str] = OrderedDict()

    async def guide(
        self,
        *,
        message: str,
        ux: dict | None,
        stage: str | None,
        language: str | None = None,
        detail_level: str | None = None,
        tone: str | None = None,
        query: str | None = None,
    ) -> dict[str, str]:
        snapshot = self.config.snapshot()
        voice = snapshot["voice"]
        language = language or voice["language"]
        detail_level = detail_level or voice["detail_level"]
        tone = tone or voice["tone"]

        cache_key = self._cache_key(
            message=message,
            ux=ux,
            stage=stage,
            language=language,
            detail_level=detail_level,
            tone=tone,
            query=query,
            family=snapshot["model_family"],
            model=snapshot["task_models"]["voice_summarizer"],
        )
        cached = self._summary_cache.get(cache_key)
        if cached:
            self._summary_cache.move_to_end(cache_key)
            return {"text": cached}

        mode_instruction = {
            "quick": "Keep it to 1 or 2 short spoken lines.",
            "moderate": "Cover the key highlights and next step in a short spoken summary.",
            "detailed": "Give a guided walkthrough of the current screen, still concise enough for voice.",
        }.get(detail_level, "Keep it short and spoken.")

        prompt = (
            f"Language: {language}.\n"
            f"Tone: {tone}.\n"
            f"Stage: {stage or (ux or {}).get('stage') or 'unknown'}.\n"
            f"{mode_instruction}\n"
            "Prefer concise spoken phrasing and short sentences.\n\n"
            f"Latest bot message:\n{message}\n\n"
            f"Current UX JSON:\n{_jsonish(ux)}\n"
        )
        if query:
            prompt += (
                f"\nSpoken clarification question:\n{query}\n\n"
                "Answer that question only from the provided UI state. "
                "If the question needs broader insurance knowledge, say it should be asked through chat."
            )
        else:
            prompt += (
                "\nExplain what is on screen, the important choice, and the immediate next action."
            )

        text = await self.model_router.complete_text(
            task="voice_summarizer",
            system=VOICE_GUIDE_SYSTEM,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=DETAIL_TOKEN_LIMITS.get(detail_level, 150),
        )

        spoken = (text or "").strip()
        if not spoken:
            spoken = "I can summarize the current screen once the response finishes loading."
        self._remember(cache_key, spoken)
        return {"text": spoken}

    async def classify(
        self,
        *,
        transcript: str,
        message: str | None,
        ux: dict | None,
        stage: str | None,
    ) -> dict[str, str]:
        heuristic = self._heuristic_intent(transcript, ux)
        if heuristic["intent"] != "ambiguous":
            return heuristic

        prompt = (
            f"Spoken input:\n{transcript}\n\n"
            f"Current stage: {stage or (ux or {}).get('stage') or 'unknown'}\n"
            f"Current UX JSON:\n{_jsonish(ux)}\n\n"
            f"Latest bot message:\n{message or ''}"
        )

        try:
            raw = await self.model_router.complete_text(
                task="intent_classifier",
                system=INTENT_CLASSIFIER_SYSTEM,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=120,
                json_mode=True,
            )
            parsed = json.loads(raw)
            intent = parsed.get("intent", "ambiguous")
            if intent not in {"clarification", "response", "detailed_question", "ambiguous"}:
                intent = "ambiguous"
            return {
                "intent": intent,
                "reason": parsed.get("reason", "Model classification"),
                "follow_up": "Do you want me to explain this screen or send that as your reply?"
                if intent == "ambiguous"
                else "",
            }
        except (ProviderError, json.JSONDecodeError):
            return heuristic

    def _heuristic_intent(self, transcript: str, ux: dict | None) -> dict[str, str]:
        text = (transcript or "").strip()
        lower = text.lower()
        if not text:
            return {
                "intent": "ambiguous",
                "reason": "Empty transcript",
                "follow_up": "I didn't catch that. Please say it again.",
            }

        option_labels = []
        input_spec = (ux or {}).get("input") or {}
        for option in input_spec.get("options") or []:
            label = str(option.get("label", "")).strip().lower()
            value = str(option.get("value", "")).strip().lower()
            if label:
                option_labels.append(label)
            if value:
                option_labels.append(value)

        clarification_markers = (
            "what does",
            "what is this",
            "what does this",
            "what next",
            "is this required",
            "do i need",
            "which one do i choose",
            "which option",
            "what should i do",
            "where do i click",
            "what does it mean",
        )
        detailed_markers = (
            "what is zero dep",
            "what is zero depreciation",
            "compare",
            "which policy",
            "which plan",
            "better and why",
            "difference between",
            "explain",
            "why is",
            "best insurer",
            "claim settlement",
            "should i buy",
        )
        response_markers = (
            "yes",
            "no",
            "skip",
            "continue",
            "go ahead",
            "third party",
            "comprehensive",
            "personal",
            "taxi",
        )

        if any(marker in lower for marker in clarification_markers):
            return {"intent": "clarification", "reason": "UI clarification phrasing"}

        if any(marker in lower for marker in detailed_markers):
            return {"intent": "detailed_question", "reason": "Needs broader explanation"}

        if any(marker == lower for marker in response_markers):
            return {"intent": "response", "reason": "Direct short response"}

        if option_labels and any(option in lower for option in option_labels):
            return {"intent": "response", "reason": "Matches current choice options"}

        if len(lower.split()) <= 4 and not lower.endswith("?"):
            return {"intent": "response", "reason": "Short likely answer"}

        if "?" in lower or lower.startswith(("what", "why", "how", "which")):
            return {"intent": "detailed_question", "reason": "Question likely needs chat reasoning"}

        return {
            "intent": "ambiguous",
            "reason": "Heuristics were not confident",
            "follow_up": "Do you want me to explain this screen or send that as your reply?",
        }

    def _cache_key(self, **payload) -> str:
        raw = json.dumps(payload, sort_keys=True, ensure_ascii=False)
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def _remember(self, key: str, value: str) -> None:
        self._summary_cache[key] = value
        self._summary_cache.move_to_end(key)
        while len(self._summary_cache) > 64:
            self._summary_cache.popitem(last=False)

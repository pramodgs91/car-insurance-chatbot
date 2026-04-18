"""
Agentic orchestration for the car insurance chatbot.

Design:
- Tools are fetched from a ToolRegistry (never hallucinates data).
- RAG is consulted ONLY on explanation/objection/compare queries.
- Response style is injected from runtime config.
- Progress events are streamed while tools run (perceived latency).
- Agent returns both the response AND a structured UX payload
  (suggestions + input controls) for the frontend.
"""
from __future__ import annotations

import asyncio
import json
import os
import re
from pathlib import Path
from typing import AsyncIterator

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent / ".env", override=True)

from anthropic import AsyncAnthropic

from tools import build_registry
from tools.fields import JOURNEY
from rag import VectorStore
from admin import RuntimeConfig, STYLE_PRESETS


MODEL = os.environ.get("CLAUDE_MODEL", "claude-sonnet-4-20250514")
client = AsyncAnthropic(max_retries=3)


# ── System prompt builder ────────────────────────────────────────────────────

CORE_PROMPT = """You are an expert, warm, and slightly sales-oriented car insurance advisor for an Indian insurance aggregator.

## Core rules (NEVER violate)
1. **Always call tools for factual data.** Never guess car details, premiums, IDV, add-on prices, or required fields. If a lookup fails, say so — do NOT make up numbers.
2. **Progressive input collection.** Ask ONE primary question per turn. Accept multiple inputs only if the user volunteers them. Skip questions for data already known.
3. **Stay in the flow.** The purchase journey has stages: registration_lookup → car_confirmation → policy_history → plan_selection → addons → previous_policy_details → nominee_details → review. Call `get_required_fields` whenever you need to know what to ask next.
4. **Guide, don't overwhelm.** Summarize, recommend, then ask. Don't dump 10 options at once.
5. **Be honest about mandatory items.** Compulsory Personal Accident cover is legally required (IRDAI rule). Don't pretend it's optional.

## Sales craft (apply tastefully — never pushy)
- Frame price in daily terms ("just ₹X/day").
- Use social proof ("most buyers with a car under 5 years pick Zero Dep").
- Surface urgency only when genuine (policy about to lapse, NCB about to reset).
- Handle objections by re-framing value, not by repeating price.

## Formatting
- Markdown. Short paragraphs. Bullets when listing 3+ items.
- Bold key numbers.
- Use ₹ symbol for rupees. Format: ₹12,345 (Indian comma style).
- For quote comparisons, use a markdown table with columns: Insurer, Premium, IDV, Claim Settlement, Why pick.

## Output contract
At the END of every user-facing reply, include a machine-readable block (nothing after it):

<ux>
{
  "stage": "<current journey stage key>",
  "suggestions": ["short suggestion 1", "short suggestion 2", "short suggestion 3"],
  "input": {
    "type": "text" | "choice" | "multi_choice" | "none",
    "field_key": "<field key if collecting input>",
    "options": [{"value": "...", "label": "..."}]
  }
}
</ux>

Rules for the <ux> block:
- `suggestions`: 2-4 SHORT natural-language replies the user might tap. They must map to the user's POV (e.g. "Show cheapest plan", not "Here is the cheapest plan").
- `input`: If you are asking a choice question (policy type, yes/no, NCB %, insurer pick, addons), return a `choice` or `multi_choice` with options. Otherwise `text` (for open-ended answers) or `none` (for the review step after everything is collected).
- Never put the <ux> block before prose. Always last.
- Keep suggestions conversion-oriented whenever the user is mid-journey.
"""


STYLE_RULES = """
## Active response style: {style_name}
- Tone: {tone}
- Verbosity: {verbosity}
- Persuasion level: {persuasion}

Adapt every message to this style. Low verbosity = tight sentences, minimal preamble. High persuasion = more value framing and gentle nudges.
"""


RAG_PREAMBLE = """
## Knowledge base excerpts (retrieved for this turn)
The following passages come from our product knowledge base. Use them to ground factual answers about insurance concepts, add-ons, claims, or objections. If the excerpts don't cover the question, say so plainly — do NOT invent facts.

{passages}

---
"""


def build_system_prompt(config: RuntimeConfig, rag_passages: list[dict] | None) -> str:
    snapshot = config.snapshot()
    preset = snapshot["style_preset"]
    parts = [CORE_PROMPT]

    parts.append(STYLE_RULES.format(
        style_name=snapshot["style"],
        tone=preset["tone"],
        verbosity=preset["verbosity"],
        persuasion=preset["persuasion"],
    ))

    enabled = [b for b in snapshot["custom_instructions"] if b["enabled"]]
    if enabled:
        parts.append("\n## Custom instructions\n" + "\n\n".join(
            f"### {b['title']}\n{b['content']}" for b in enabled
        ))

    if rag_passages:
        rendered = "\n\n".join(
            f"[{i+1}] From \"{p['doc_name']}\": {p['text']}"
            for i, p in enumerate(rag_passages)
        )
        parts.append(RAG_PREAMBLE.format(passages=rendered))

    return "\n".join(parts)


# ── UX block parsing ─────────────────────────────────────────────────────────

_UX_RE = re.compile(r"<ux>\s*(\{.*?\})\s*</ux>", re.DOTALL)


def extract_ux(text: str) -> tuple[str, dict | None]:
    """Split the model's reply into (prose, ux_dict). Tolerates malformed JSON."""
    match = _UX_RE.search(text)
    if not match:
        return text.strip(), None
    prose = (text[:match.start()] + text[match.end():]).strip()
    try:
        ux = json.loads(match.group(1))
    except json.JSONDecodeError:
        return prose, None
    return prose, ux


# ── RAG trigger heuristic ────────────────────────────────────────────────────

_RAG_KEYWORDS = [
    "what is", "what's", "what are", "how does", "how do", "explain",
    "why", "compare", "difference", "cover", "claim", "mandatory", "ncb",
    "idv", "zero dep", "return to invoice", "engine protect", "rsa",
    "consumables", "deductible", "depreciation", "addon", "add-on", "add on",
    "expensive", "cheaper", "too much", "later", "trust", "best insurer",
    "recommend", "suggest", "pa cover", "personal accident",
]


def should_retrieve(query: str) -> bool:
    q = query.lower()
    return any(kw in q for kw in _RAG_KEYWORDS) or q.endswith("?")


# ── Agent ────────────────────────────────────────────────────────────────────

class Agent:
    def __init__(self, vector_store: VectorStore, config: RuntimeConfig):
        self.tools = build_registry()
        self.vector_store = vector_store
        self.config = config

    async def _maybe_retrieve(self, query: str) -> list[dict]:
        cfg = self.config.snapshot()
        if not cfg["rag_enabled"]:
            return []
        if not self.vector_store.enabled:
            return []
        if not should_retrieve(query):
            return []
        return self.vector_store.search(query, top_k=3)

    async def _quality_check(self, prose: str) -> str | None:
        cfg = self.config.snapshot()
        if not cfg["evaluation_loop_enabled"]:
            return None
        if len(prose) < 80:
            return None
        check = await client.messages.create(
            model=MODEL,
            max_tokens=120,
            messages=[{
                "role": "user",
                "content": (
                    "You're a quality checker for a car-insurance advisor chatbot. "
                    "Review this reply and check: factual accuracy, progressive flow "
                    "(one question at a time), tone, and whether a <ux> block "
                    "exists. If it looks good, reply exactly APPROVED. Otherwise, "
                    "write one short sentence describing what to fix.\n\n"
                    f"Reply:\n{prose[:1500]}"
                ),
            }],
        )
        out = check.content[0].text.strip()
        return None if out.upper().startswith("APPROVED") else out

    async def stream(
        self, user_message: str, history: list, session_data: dict
    ) -> AsyncIterator[dict]:
        cfg = self.config.snapshot()

        if cfg["latency_optimizations_enabled"]:
            yield {"type": "progress", "text": "Got it — let me check that for you..."}

        retrieve_task = asyncio.create_task(self._maybe_retrieve(user_message))
        history.append({"role": "user", "content": user_message})
        rag_passages = await retrieve_task

        if rag_passages and cfg["latency_optimizations_enabled"]:
            yield {
                "type": "progress",
                "text": f"Pulled {len(rag_passages)} reference passage(s) from the knowledge base",
            }

        system_prompt = build_system_prompt(self.config, rag_passages)
        tool_schemas = self.tools.anthropic_schemas()

        for _ in range(6):
            try:
                response = await client.messages.create(
                    model=MODEL,
                    max_tokens=2048,
                    system=system_prompt,
                    tools=tool_schemas,
                    messages=history,
                )
            except Exception as exc:
                yield {"type": "error", "text": f"Model error: {exc}"}
                return

            if response.stop_reason == "tool_use":
                history.append({"role": "assistant", "content": response.content})

                tool_blocks = [b for b in response.content if b.type == "tool_use"]
                for tb in tool_blocks:
                    human_msg = _progress_msg_for_tool(tb.name, tb.input)
                    yield {"type": "tool_start", "tool": tb.name, "text": human_msg}

                async def run_one(tb):
                    result = await self.tools.execute(tb.name, tb.input)
                    return tb.id, tb.name, result

                results = await asyncio.gather(*(run_one(tb) for tb in tool_blocks))

                tool_results = []
                for tb_id, tb_name, result in results:
                    ok = "error" not in result
                    yield {"type": "tool_end", "tool": tb_name, "ok": ok}

                    if tb_name == "get_car_details" and ok:
                        session_data["car_info"] = result
                    elif tb_name == "get_insurance_quotes" and ok:
                        session_data["quotes"] = result.get("quotes", [])
                    elif tb_name == "get_addon_prices" and ok:
                        session_data["addons"] = result.get("addons", [])

                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": tb_id,
                        "content": json.dumps(result),
                    })

                history.append({"role": "user", "content": tool_results})
                continue

            text = ""
            for b in response.content:
                if hasattr(b, "text"):
                    text += b.text

            correction = await self._quality_check(text)
            if correction:
                history.append({"role": "assistant", "content": text})
                history.append({
                    "role": "user",
                    "content": [{
                        "type": "text",
                        "text": f"[INTERNAL QC — not from user] Please revise your previous reply. Issue: {correction}. Reply with the corrected response only — keep the <ux> block at the end. Do not mention this revision.",
                    }],
                })
                revised = await client.messages.create(
                    model=MODEL,
                    max_tokens=2048,
                    system=system_prompt,
                    tools=tool_schemas,
                    messages=history,
                )
                revised_text = "".join(b.text for b in revised.content if hasattr(b, "text"))
                if revised_text:
                    history.pop()
                    history.pop()
                    text = revised_text

            history.append({"role": "assistant", "content": text})
            prose, ux = extract_ux(text)
            yield {"type": "final", "text": prose, "ux": ux}
            return

        yield {"type": "error", "text": "Max tool iterations reached."}


# ── Progress message helpers ─────────────────────────────────────────────────

def _progress_msg_for_tool(name: str, input_data: dict) -> str:
    if name == "get_car_details":
        return f"Looking up {input_data.get('registration_number', 'your car')}..."
    if name == "get_insurance_quotes":
        return "Fetching quotes from 12+ insurers..."
    if name == "get_addon_prices":
        return "Pricing add-on covers..."
    if name == "get_required_fields":
        return "Checking what's next..."
    return f"Running {name}..."

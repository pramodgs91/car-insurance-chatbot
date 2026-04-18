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


# Default to Haiku 4.5 — 2-3× faster TTFT than Sonnet; plenty smart for
# a structured journey. Override with CLAUDE_MODEL env var if needed.
MODEL = os.environ.get("CLAUDE_MODEL", "claude-haiku-4-5-20251001")
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


def build_system_blocks(config: RuntimeConfig, rag_passages: list[dict] | None) -> list[dict]:
    """
    Return system as a list of content blocks. The static prefix
    (core + style + custom instructions) is marked with cache_control
    so Anthropic caches it across turns — saves input-token cost AND
    shaves 300–800ms of input processing on cache hits.

    RAG passages live in a separate (uncached) trailing block because
    they change per turn.
    """
    snapshot = config.snapshot()
    preset = snapshot["style_preset"]

    static_parts = [CORE_PROMPT, STYLE_RULES.format(
        style_name=snapshot["style"],
        tone=preset["tone"],
        verbosity=preset["verbosity"],
        persuasion=preset["persuasion"],
    )]

    enabled = [b for b in snapshot["custom_instructions"] if b["enabled"]]
    if enabled:
        static_parts.append("\n## Custom instructions\n" + "\n\n".join(
            f"### {b['title']}\n{b['content']}" for b in enabled
        ))

    blocks: list[dict] = [{
        "type": "text",
        "text": "\n".join(static_parts),
        "cache_control": {"type": "ephemeral"},
    }]

    if rag_passages:
        rendered = "\n\n".join(
            f"[{i+1}] From \"{p['doc_name']}\": {p['text']}"
            for i, p in enumerate(rag_passages)
        )
        blocks.append({
            "type": "text",
            "text": RAG_PREAMBLE.format(passages=rendered),
        })

    return blocks


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
        """
        Event types:
          progress  — transient status text (pre-flight, retrieval)
          token     — incremental text chunk for the live bot bubble
          tool_start / tool_end — tool-call lifecycle (shown as pills)
          final     — end of turn with cleaned prose + parsed <ux>
          error     — fatal model/network error
        """
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

        system_blocks = build_system_blocks(self.config, rag_passages)
        tool_schemas = self.tools.anthropic_schemas()

        for _ in range(6):
            text_accum = ""
            ux_started = False  # once we see "<ux>" we stop forwarding tokens
            final_message = None

            try:
                async with client.messages.stream(
                    model=MODEL,
                    max_tokens=2048,
                    system=system_blocks,
                    tools=tool_schemas,
                    messages=history,
                ) as stream:
                    async for event in stream:
                        etype = getattr(event, "type", None)
                        if etype == "content_block_delta":
                            delta = getattr(event, "delta", None)
                            chunk = getattr(delta, "text", None) if delta else None
                            if not chunk:
                                continue
                            text_accum += chunk
                            if ux_started:
                                continue
                            # If the model just started emitting "<ux>"
                            # mid-chunk, split and forward only the pre-ux part.
                            idx = text_accum.find("<ux>")
                            if idx != -1:
                                # The chunk that revealed "<ux>" may contain
                                # prose bytes before it — figure out how many
                                # of THIS chunk belong pre-ux.
                                pre_in_accum = text_accum[:idx]
                                already_sent_len = len(text_accum) - len(chunk)
                                if len(pre_in_accum) > already_sent_len:
                                    yield {
                                        "type": "token",
                                        "text": pre_in_accum[already_sent_len:],
                                    }
                                ux_started = True
                            else:
                                yield {"type": "token", "text": chunk}
                    final_message = await stream.get_final_message()
            except Exception as exc:
                yield {"type": "error", "text": f"Model error: {exc}"}
                return

            if final_message is None:
                yield {"type": "error", "text": "Empty model response."}
                return

            if final_message.stop_reason == "tool_use":
                # Discard any interim text the user saw this turn — progress
                # pills take over for tool execution.
                if text_accum:
                    yield {"type": "token_reset"}

                history.append({"role": "assistant", "content": final_message.content})

                tool_blocks = [b for b in final_message.content if b.type == "tool_use"]
                for tb in tool_blocks:
                    yield {
                        "type": "tool_start",
                        "tool": tb.name,
                        "text": _progress_msg_for_tool(tb.name, tb.input),
                    }

                async def run_one(tb):
                    return tb.id, tb.name, await self.tools.execute(tb.name, tb.input)

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

            # end_turn — final reply. Tokens have already streamed.
            # Optional QC (off by default for speed).
            correction = await self._quality_check(text_accum)
            if correction:
                history.append({"role": "assistant", "content": text_accum})
                history.append({
                    "role": "user",
                    "content": [{
                        "type": "text",
                        "text": f"[INTERNAL QC — not from user] Please revise your previous reply. Issue: {correction}. Reply with the corrected response only — keep the <ux> block at the end. Do not mention this revision.",
                    }],
                })
                # Reset the live bubble — the revised text will stream fresh.
                yield {"type": "token_reset"}
                revised_accum = ""
                revised_ux_started = False
                try:
                    async with client.messages.stream(
                        model=MODEL,
                        max_tokens=2048,
                        system=system_blocks,
                        tools=tool_schemas,
                        messages=history,
                    ) as stream:
                        async for event in stream:
                            if getattr(event, "type", None) != "content_block_delta":
                                continue
                            delta = getattr(event, "delta", None)
                            chunk = getattr(delta, "text", None) if delta else None
                            if not chunk:
                                continue
                            revised_accum += chunk
                            if revised_ux_started:
                                continue
                            idx = revised_accum.find("<ux>")
                            if idx != -1:
                                pre = revised_accum[:idx]
                                sent = len(revised_accum) - len(chunk)
                                if len(pre) > sent:
                                    yield {"type": "token", "text": pre[sent:]}
                                revised_ux_started = True
                            else:
                                yield {"type": "token", "text": chunk}
                except Exception:
                    revised_accum = ""
                if revised_accum:
                    history.pop()  # remove QC instruction
                    history.pop()  # remove original (pre-revision) reply
                    text_accum = revised_accum

            history.append({"role": "assistant", "content": text_accum})
            prose, ux = extract_ux(text_accum)
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

"""
Agentic orchestration for the car insurance chatbot.

Design:
- Tools are fetched from a ToolRegistry (never hallucinates data).
- RAG is consulted ONLY on explanation/objection/compare queries.
- Response style is injected from runtime config.
- Progress events are streamed while tools run (perceived latency).
- Provider/model routing is runtime-configurable and shared with voice/QC.
"""
from __future__ import annotations

import asyncio
import json
import re
from typing import AsyncIterator

from tools import build_registry
from rag import VectorStore
from admin import RuntimeConfig


CORE_PROMPT = """You are an expert, warm, and slightly sales-oriented car insurance advisor for an Indian insurance aggregator.

## Core rules (NEVER violate)
1. Always call tools for factual data. Never guess car details, premiums, IDV, add-on prices, or required fields. If a lookup fails, say so — do NOT make up numbers.
2. Progressive input collection. Ask ONE primary question per turn. Accept multiple inputs only if the user volunteers them. Skip questions for data already known.
3. Stay in the flow. The purchase journey has stages: registration_lookup → car_confirmation → policy_history → plan_selection → addons → previous_policy_details → nominee_details → review. Call `get_required_fields` whenever you need to know what to ask next.
4. Guide, don't overwhelm. Summarize, recommend, then ask. Don't dump 10 options at once.
5. Be honest about mandatory items. Compulsory Personal Accident cover is legally required (IRDAI rule). Don't pretend it's optional.
6. Upload-first onboarding. In the VERY FIRST reply of a session, invite the user to upload their RC card AND/OR previous policy, or to type their registration number — whichever is faster. Add a suggestion chip labeled "📎 Upload RC or policy" so the frontend renders a file picker. The user can upload one document or both; each upload is processed separately and fields are merged.
7. Trust uploaded extractions. If a user message is wrapped in square brackets and starts with "[I uploaded" — the fields inside are authoritative. Do NOT call `get_car_details` for the same registration; acknowledge the upload, confirm the key details in one sentence, and advance to the next missing field. Never re-ask for something already extracted.
8. Re-prompt for documents after quote selection. Once the user has selected a quote/plan (moving past plan_selection into addons or later stages), check the conversation history. If you see NO "[I uploaded…]" messages in this session, include "📎 Upload RC card or previous policy" as one of the `suggestions` in the next 1–2 replies. Remind the user that uploading these docs lets you auto-fill nominee details, previous insurer name, and policy number — significantly speeding up the checkout.

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


QC_SYSTEM = """You are a quality checker for a car-insurance advisor chatbot.

Review the assistant reply and check:
- factual accuracy
- progressive flow (one question at a time)
- tone
- whether a <ux> block exists

If it looks good, reply exactly APPROVED.
Otherwise, reply with one short sentence describing the main issue to fix.
"""


REVISION_SYSTEM = """You are revising a chatbot reply.

Return only the corrected reply. Keep the <ux> block at the end.
Do not mention that you revised anything.
"""


_UX_RE = re.compile(r"<ux>\s*(\{.*?\})\s*</ux>", re.DOTALL)

_RAG_KEYWORDS = [
    "what is", "what's", "what are", "how does", "how do", "explain",
    "why", "compare", "difference", "cover", "claim", "mandatory", "ncb",
    "idv", "zero dep", "return to invoice", "engine protect", "rsa",
    "consumables", "deductible", "depreciation", "addon", "add-on", "add on",
    "expensive", "cheaper", "too much", "later", "trust", "best insurer",
    "recommend", "suggest", "pa cover", "personal accident",
]


def build_system_blocks(config: RuntimeConfig, rag_passages: list[dict] | None) -> list[dict]:
    snapshot = config.snapshot()
    preset = snapshot["style_preset"]

    # Block 1: Static core (cached independently — large, rarely changes)
    core_text = CORE_PROMPT + "\n\n" + STYLE_RULES.format(
        style_name=snapshot["style"],
        tone=preset["tone"],
        verbosity=preset["verbosity"],
        persuasion=preset["persuasion"],
    )
    blocks: list[dict] = [
        {"type": "text", "text": core_text, "cache_control": {"type": "ephemeral"}}
    ]

    # Block 2: Custom instructions (separate cached block — changes when admin edits)
    # Kept separate so Block 1 cache stays warm even when instructions change.
    enabled = [block for block in snapshot["custom_instructions"] if block["enabled"]]
    if enabled:
        custom_text = (
            "## Operator custom instructions\n"
            "IMPORTANT: The following instructions come from the operator and MUST be "
            "followed in addition to the core rules above. They take precedence over "
            "default behaviour when there is any conflict.\n\n"
            + "\n\n".join(f"### {b['title']}\n{b['content']}" for b in enabled)
        )
        blocks.append(
            {"type": "text", "text": custom_text, "cache_control": {"type": "ephemeral"}}
        )

    # Block 3: RAG passages (dynamic — not cached, changes every turn)
    if rag_passages:
        rendered = "\n\n".join(
            f"[{i + 1}] From \"{p['doc_name']}\": {p['text']}"
            for i, p in enumerate(rag_passages)
        )
        blocks.append({"type": "text", "text": RAG_PREAMBLE.format(passages=rendered)})

    return blocks


def extract_ux(text: str) -> tuple[str, dict | None]:
    match = _UX_RE.search(text)
    if not match:
        return text.strip(), None
    prose = (text[: match.start()] + text[match.end() :]).strip()
    try:
        ux = json.loads(match.group(1))
    except json.JSONDecodeError:
        return prose, None
    return prose, ux


def should_retrieve(query: str) -> bool:
    q = query.lower()
    return any(keyword in q for keyword in _RAG_KEYWORDS) or q.endswith("?")


class Agent:
    def __init__(self, vector_store: VectorStore, config: RuntimeConfig, model_router):
        self.tools = build_registry()
        self.vector_store = vector_store
        self.config = config
        self.model_router = model_router

    async def _maybe_retrieve(self, query: str) -> list[dict]:
        cfg = self.config.snapshot()
        if not cfg["rag_enabled"] or not self.vector_store.enabled or not should_retrieve(query):
            return []
        return self.vector_store.search(query, top_k=3)

    async def _quality_check(self, prose: str) -> str | None:
        cfg = self.config.snapshot()
        if not cfg["evaluation_loop_enabled"] or len(prose) < 80:
            return None
        out = await self.model_router.complete_text(
            task="quality_checker",
            system=QC_SYSTEM,
            messages=[{"role": "user", "content": prose[:1800]}],
            max_tokens=120,
        )
        return None if out.upper().startswith("APPROVED") else out

    async def _revise_reply(self, reply: str, issue: str) -> str:
        prompt = (
            f"Original reply:\n{reply}\n\n"
            f"Issue to fix:\n{issue}\n\n"
            "Return the improved reply only."
        )
        revised = await self.model_router.complete_text(
            task="quality_checker",
            system=REVISION_SYSTEM,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=450,
        )
        return revised.strip() or reply

    async def stream(
        self,
        user_message: str,
        history: list,
        session_data: dict,
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

        system_blocks = build_system_blocks(self.config, rag_passages)
        tool_schemas = self.tools.anthropic_schemas()

        for _ in range(6):
            text_accum = ""
            ux_started = False
            outcome = {"kind": "message", "tool_calls": []}

            try:
                async for event in self.model_router.stream_chat(system_blocks, history, tool_schemas):
                    if event["type"] == "text":
                        chunk = event.get("text") or ""
                        if not chunk:
                            continue
                        text_accum += chunk
                        if ux_started:
                            continue
                        idx = text_accum.find("<ux>")
                        if idx != -1:
                            pre_in_accum = text_accum[:idx]
                            already_sent_len = len(text_accum) - len(chunk)
                            if len(pre_in_accum) > already_sent_len:
                                yield {"type": "token", "text": pre_in_accum[already_sent_len:]}
                            ux_started = True
                        else:
                            yield {"type": "token", "text": chunk}
                    elif event["type"] == "tool_calls":
                        outcome = {"kind": "tool_calls", "tool_calls": event.get("tool_calls", [])}
                    elif event["type"] == "message":
                        outcome = {"kind": "message", "tool_calls": []}
            except Exception as exc:
                yield {"type": "error", "text": f"Model error: {exc}"}
                return

            if outcome["kind"] == "tool_calls":
                if text_accum:
                    yield {"type": "token_reset"}
                history.append(
                    {
                        "role": "assistant",
                        "content": text_accum,
                        "tool_calls": outcome["tool_calls"],
                    }
                )

                for tool_call in outcome["tool_calls"]:
                    yield {
                        "type": "tool_start",
                        "tool": tool_call["name"],
                        "text": _progress_msg_for_tool(tool_call["name"], tool_call["input"]),
                    }

                async def run_one(tool_call: dict) -> tuple[dict, dict]:
                    result = await self.tools.execute(tool_call["name"], tool_call["input"], session_data=session_data)
                    return tool_call, result

                results = await asyncio.gather(*(run_one(call) for call in outcome["tool_calls"]))
                for tool_call, result in results:
                    ok = "error" not in result
                    yield {"type": "tool_end", "tool": tool_call["name"], "ok": ok}

                    if tool_call["name"] == "get_car_details" and ok:
                        session_data["car_info"] = result
                    elif tool_call["name"] == "get_insurance_quotes" and ok:
                        session_data["quotes"] = result.get("quotes", [])
                    elif tool_call["name"] == "get_addon_prices" and ok:
                        session_data["addons"] = result.get("addons", [])

                    history.append(
                        {
                            "role": "tool",
                            "tool_call_id": tool_call["id"],
                            "name": tool_call["name"],
                            "content": json.dumps(result),
                        }
                    )
                continue

            if not text_accum.strip():
                yield {"type": "error", "text": "Empty model response."}
                return

            correction = await self._quality_check(text_accum)
            if correction:
                yield {"type": "token_reset"}
                try:
                    text_accum = await self._revise_reply(text_accum, correction)
                except Exception:
                    pass

            history.append({"role": "assistant", "content": text_accum})
            prose, ux = extract_ux(text_accum)
            yield {"type": "final", "text": prose, "ux": ux}
            return

        yield {"type": "error", "text": "Max tool iterations reached."}


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

"""
Provider abstraction for chat, lightweight voice/QC tasks, and document
extraction. Keeps the rest of the app provider-neutral.
"""
from __future__ import annotations

import base64
import importlib
import io
import json
import os
from pathlib import Path
from typing import Any, AsyncIterator

from dotenv import load_dotenv

from model_defaults import MODEL_FAMILIES


load_dotenv(Path(__file__).parent / ".env", override=True)


class ProviderError(RuntimeError):
    """Raised when a provider call cannot be completed."""


def _flatten_system_text(system_blocks: list[dict] | str | None) -> str:
    if isinstance(system_blocks, str):
        return system_blocks
    if not system_blocks:
        return ""
    parts: list[str] = []
    for block in system_blocks:
        text = block.get("text") if isinstance(block, dict) else None
        if text:
            parts.append(text)
    return "\n\n".join(parts).strip()


def _strip_code_fences(text: str) -> str:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`")
        if "\n" in cleaned:
            cleaned = cleaned.split("\n", 1)[1]
    if cleaned.endswith("```"):
        cleaned = cleaned[:-3]
    return cleaned.strip()


def _extract_json_object(text: str) -> dict[str, Any]:
    cleaned = _strip_code_fences(text)
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start != -1 and end != -1 and end > start:
            return json.loads(cleaned[start : end + 1])
        raise


def _openai_tools(tools: list[dict]) -> list[dict]:
    rendered: list[dict] = []
    for tool in tools or []:
        rendered.append(
            {
                "type": "function",
                "function": {
                    "name": tool["name"],
                    "description": tool.get("description", ""),
                    "parameters": tool.get("input_schema", {"type": "object", "properties": {}}),
                },
            }
        )
    return rendered


def _coerce_openai_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, dict) and item.get("type") == "text":
                parts.append(item.get("text", ""))
            elif hasattr(item, "text"):
                parts.append(getattr(item, "text"))
        return "".join(parts)
    return ""


def _neutral_to_openai_messages(history: list[dict]) -> list[dict]:
    rendered: list[dict] = []
    for msg in history:
        role = msg["role"]
        if role in {"user", "assistant"} and "tool_calls" not in msg:
            rendered.append({"role": role, "content": msg.get("content", "")})
            continue
        if role == "assistant" and "tool_calls" in msg:
            rendered.append(
                {
                    "role": "assistant",
                    "content": msg.get("content", "") or "",
                    "tool_calls": [
                        {
                            "id": call["id"],
                            "type": "function",
                            "function": {
                                "name": call["name"],
                                "arguments": json.dumps(call["input"]),
                            },
                        }
                        for call in msg.get("tool_calls", [])
                    ],
                }
            )
            continue
        if role == "tool":
            rendered.append(
                {
                    "role": "tool",
                    "tool_call_id": msg["tool_call_id"],
                    "content": msg.get("content", ""),
                }
            )
    return rendered


def _neutral_to_anthropic_messages(history: list[dict]) -> list[dict]:
    rendered: list[dict] = []
    pending_tool_results: list[dict] = []

    def flush_tool_results() -> None:
        nonlocal pending_tool_results
        if pending_tool_results:
            rendered.append({"role": "user", "content": pending_tool_results})
            pending_tool_results = []

    for msg in history:
        role = msg["role"]
        if role == "tool":
            pending_tool_results.append(
                {
                    "type": "tool_result",
                    "tool_use_id": msg["tool_call_id"],
                    "content": msg.get("content", ""),
                }
            )
            continue

        flush_tool_results()
        if role in {"user", "assistant"} and "tool_calls" not in msg:
            rendered.append({"role": role, "content": msg.get("content", "")})
            continue

        if role == "assistant" and "tool_calls" in msg:
            blocks: list[dict] = []
            if msg.get("content"):
                blocks.append({"type": "text", "text": msg["content"]})
            for call in msg.get("tool_calls", []):
                blocks.append(
                    {
                        "type": "tool_use",
                        "id": call["id"],
                        "name": call["name"],
                        "input": call["input"],
                    }
                )
            rendered.append({"role": "assistant", "content": blocks})

    flush_tool_results()
    return rendered


class AnthropicProvider:
    def __init__(self):
        from anthropic import AsyncAnthropic

        self.client = AsyncAnthropic(max_retries=3)

    async def stream_chat(
        self,
        model: str,
        system_blocks: list[dict],
        history: list[dict],
        tools: list[dict],
        max_tokens: int = 2048,
    ) -> AsyncIterator[dict]:
        try:
            async with self.client.messages.stream(
                model=model,
                max_tokens=max_tokens,
                system=system_blocks,
                tools=tools,
                messages=_neutral_to_anthropic_messages(history),
            ) as stream:
                async for event in stream:
                    if getattr(event, "type", None) != "content_block_delta":
                        continue
                    delta = getattr(event, "delta", None)
                    chunk = getattr(delta, "text", None) if delta else None
                    if chunk:
                        yield {"type": "text", "text": chunk}
                final_message = await stream.get_final_message()
        except Exception as exc:
            raise ProviderError(str(exc)) from exc

        if final_message.stop_reason == "tool_use":
            tool_calls = []
            for block in final_message.content:
                if getattr(block, "type", None) == "tool_use":
                    tool_calls.append(
                        {
                            "id": block.id,
                            "name": block.name,
                            "input": block.input or {},
                        }
                    )
            yield {"type": "tool_calls", "tool_calls": tool_calls}
            return

        yield {"type": "message"}

    async def complete_text(
        self,
        model: str,
        system: str,
        messages: list[dict],
        max_tokens: int = 220,
    ) -> str:
        try:
            response = await self.client.messages.create(
                model=model,
                max_tokens=max_tokens,
                system=system,
                messages=_neutral_to_anthropic_messages(messages),
            )
        except Exception as exc:
            raise ProviderError(str(exc)) from exc

        parts = [
            block.text
            for block in response.content
            if getattr(block, "type", None) == "text" and getattr(block, "text", None)
        ]
        return "".join(parts).strip()

    async def extract_document(
        self,
        model: str,
        file_bytes: bytes,
        media_type: str,
        prompt: str,
        tool_schema: dict[str, Any],
    ) -> dict[str, Any]:
        content_block = _anthropic_media_block(file_bytes, media_type)
        try:
            response = await self.client.messages.create(
                model=model,
                max_tokens=1024,
                tools=[tool_schema],
                tool_choice={"type": "tool", "name": tool_schema["name"]},
                messages=[
                    {
                        "role": "user",
                        "content": [content_block, {"type": "text", "text": prompt}],
                    }
                ],
            )
        except Exception as exc:
            raise ProviderError(str(exc)) from exc

        for block in response.content:
            if getattr(block, "type", None) == "tool_use" and block.name == tool_schema["name"]:
                return block.input or {}
        raise ProviderError("Model did not return structured extraction.")


def _anthropic_media_block(file_bytes: bytes, media_type: str) -> dict[str, Any]:
    b64 = base64.standard_b64encode(file_bytes).decode("ascii")
    if media_type.startswith("image/"):
        return {
            "type": "image",
            "source": {"type": "base64", "media_type": media_type, "data": b64},
        }
    if media_type == "application/pdf":
        return {
            "type": "document",
            "source": {"type": "base64", "media_type": media_type, "data": b64},
        }
    raise ProviderError(f"Unsupported media type: {media_type}")


class OpenAIProvider:
    def __init__(self):
        module = importlib.import_module("openai")
        self.client = module.AsyncOpenAI(api_key=os.environ.get("OPENAI_API_KEY"))

    async def stream_chat(
        self,
        model: str,
        system_blocks: list[dict],
        history: list[dict],
        tools: list[dict],
        max_tokens: int = 2048,
    ) -> AsyncIterator[dict]:
        try:
            stream = await self.client.chat.completions.create(
                model=model,
                max_tokens=max_tokens,
                messages=[
                    {"role": "system", "content": _flatten_system_text(system_blocks)},
                    *_neutral_to_openai_messages(history),
                ],
                tools=_openai_tools(tools) or None,
                stream=True,
            )
        except Exception as exc:
            raise ProviderError(str(exc)) from exc

        tool_calls: dict[int, dict[str, Any]] = {}
        finish_reason = None
        try:
            async for chunk in stream:
                choice = chunk.choices[0] if chunk.choices else None
                if choice is None:
                    continue
                finish_reason = choice.finish_reason or finish_reason
                delta = choice.delta
                content = _coerce_openai_text(getattr(delta, "content", None))
                if content:
                    yield {"type": "text", "text": content}
                for tool_call in getattr(delta, "tool_calls", None) or []:
                    index = getattr(tool_call, "index", 0) or 0
                    entry = tool_calls.setdefault(
                        index,
                        {"id": None, "name": "", "arguments": ""},
                    )
                    if getattr(tool_call, "id", None):
                        entry["id"] = tool_call.id
                    func = getattr(tool_call, "function", None)
                    if func and getattr(func, "name", None):
                        entry["name"] = func.name
                    if func and getattr(func, "arguments", None):
                        entry["arguments"] += func.arguments
        except Exception as exc:
            raise ProviderError(str(exc)) from exc

        if finish_reason == "tool_calls" or tool_calls:
            parsed_calls = []
            for index in sorted(tool_calls):
                raw = tool_calls[index]
                try:
                    arguments = json.loads(raw["arguments"] or "{}")
                except json.JSONDecodeError as exc:
                    raise ProviderError(f"OpenAI tool arguments were invalid JSON: {exc}") from exc
                parsed_calls.append(
                    {
                        "id": raw["id"] or f"call_{index}",
                        "name": raw["name"],
                        "input": arguments,
                    }
                )
            yield {"type": "tool_calls", "tool_calls": parsed_calls}
            return

        yield {"type": "message"}

    async def complete_text(
        self,
        model: str,
        system: str,
        messages: list[dict],
        max_tokens: int = 220,
        json_mode: bool = False,
    ) -> str:
        params = {
            "model": model,
            "max_tokens": max_tokens,
            "messages": [{"role": "system", "content": system}, *_neutral_to_openai_messages(messages)],
        }
        if json_mode:
            params["response_format"] = {"type": "json_object"}
        try:
            response = await self.client.chat.completions.create(**params)
        except Exception as exc:
            raise ProviderError(str(exc)) from exc
        content = response.choices[0].message.content or ""
        return content.strip()

    async def extract_document(
        self,
        model: str,
        file_bytes: bytes,
        media_type: str,
        prompt: str,
        tool_schema: dict[str, Any],
    ) -> dict[str, Any]:
        user_content: list[dict[str, Any]]
        if media_type.startswith("image/"):
            b64 = base64.standard_b64encode(file_bytes).decode("ascii")
            user_content = [
                {"type": "text", "text": _openai_extraction_prompt(prompt, tool_schema)},
                {"type": "image_url", "image_url": {"url": f"data:{media_type};base64,{b64}"}},
            ]
        elif media_type == "application/pdf":
            text = _extract_pdf_text(file_bytes)
            if not text.strip():
                raise ProviderError("OpenAI extraction could not read text from this PDF.")
            user_content = [
                {
                    "type": "text",
                    "text": (
                        _openai_extraction_prompt(prompt, tool_schema)
                        + "\n\nExtracted PDF text:\n"
                        + text[:12000]
                    ),
                }
            ]
        else:
            raise ProviderError(f"Unsupported media type: {media_type}")

        try:
            response = await self.client.chat.completions.create(
                model=model,
                max_tokens=900,
                response_format={"type": "json_object"},
                messages=[
                    {"role": "system", "content": "Return only valid JSON."},
                    {"role": "user", "content": user_content},
                ],
            )
        except Exception as exc:
            raise ProviderError(str(exc)) from exc

        try:
            return _extract_json_object(response.choices[0].message.content or "{}")
        except json.JSONDecodeError as exc:
            raise ProviderError(f"OpenAI extraction returned invalid JSON: {exc}") from exc


def _extract_pdf_text(file_bytes: bytes) -> str:
    from pypdf import PdfReader

    reader = PdfReader(io.BytesIO(file_bytes))
    return "\n".join((page.extract_text() or "") for page in reader.pages)


def _openai_extraction_prompt(prompt: str, tool_schema: dict[str, Any]) -> str:
    properties = tool_schema.get("input_schema", {}).get("properties", {})
    fields = ", ".join(properties.keys())
    return (
        f"{prompt}\n\nReturn a JSON object with the following keys only: {fields}. "
        "Use empty strings for unknown values."
    )


class ModelRouter:
    def __init__(self, config):
        self.config = config
        self._providers: dict[str, Any] = {}

    def _provider(self, family: str):
        if family not in MODEL_FAMILIES:
            raise ProviderError(f"Unsupported model family: {family}")
        if family not in self._providers:
            if family == "claude":
                self._providers[family] = AnthropicProvider()
            else:
                self._providers[family] = OpenAIProvider()
        return self._providers[family]

    def _family_and_model(self, task: str) -> tuple[str, str]:
        snapshot = self.config.snapshot()
        family = snapshot["model_family"]
        model = snapshot["task_models"].get(task)
        if not model:
            raise ProviderError(f"No model configured for task: {task}")
        return family, model

    async def stream_chat(
        self,
        system_blocks: list[dict],
        history: list[dict],
        tools: list[dict],
        max_tokens: int = 2048,
    ) -> AsyncIterator[dict]:
        family, model = self._family_and_model("chat_agent")
        provider = self._provider(family)
        async for event in provider.stream_chat(
            model=model,
            system_blocks=system_blocks,
            history=history,
            tools=tools,
            max_tokens=max_tokens,
        ):
            yield event

    async def complete_text(
        self,
        task: str,
        system: str,
        messages: list[dict],
        max_tokens: int = 220,
        json_mode: bool = False,
    ) -> str:
        family, model = self._family_and_model(task)
        provider = self._provider(family)
        if family == "openai":
            return await provider.complete_text(
                model=model,
                system=system,
                messages=messages,
                max_tokens=max_tokens,
                json_mode=json_mode,
            )
        return await provider.complete_text(
            model=model,
            system=system,
            messages=messages,
            max_tokens=max_tokens,
        )

    async def extract_document(
        self,
        file_bytes: bytes,
        media_type: str,
        prompt: str,
        tool_schema: dict[str, Any],
    ) -> dict[str, Any]:
        family, model = self._family_and_model("document_extraction")
        provider = self._provider(family)
        return await provider.extract_document(
            model=model,
            file_bytes=file_bytes,
            media_type=media_type,
            prompt=prompt,
            tool_schema=tool_schema,
        )

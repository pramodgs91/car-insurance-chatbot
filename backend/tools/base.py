"""
Tool abstraction layer.

Every external data dependency is accessed via a Tool. Tools have a consistent
interface so they can be mocked for dev, swapped with real APIs or MCP servers
in production, and called by the LLM via Anthropic tool-use.

Contract:
- Each Tool subclass declares: name, description, input_schema, and an
  implementation of `run(**kwargs)` that returns a JSON-serializable dict.
- Tools must be stateless — they read from a pluggable data provider.
- Tools never return made-up data; if a lookup fails, they return an error field.
"""
from __future__ import annotations
from abc import ABC, abstractmethod
from typing import Any


class Tool(ABC):
    name: str
    description: str
    input_schema: dict

    @abstractmethod
    async def run(self, **kwargs) -> dict:
        """Execute the tool and return a JSON-serializable result."""

    def anthropic_schema(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": self.input_schema,
        }

    def openai_schema(self) -> dict:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.input_schema,
            },
        }


class ToolRegistry:
    """Holds all registered tools and dispatches tool-use calls."""

    def __init__(self):
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        self._tools[tool.name] = tool

    def get(self, name: str) -> Tool | None:
        return self._tools.get(name)

    def anthropic_schemas(self) -> list[dict]:
        return [t.anthropic_schema() for t in self._tools.values()]

    def openai_schemas(self) -> list[dict]:
        return [t.openai_schema() for t in self._tools.values()]

    async def execute(self, name: str, input_data: dict, session_data: dict | None = None) -> dict:
        tool = self._tools.get(name)
        if tool is None:
            return {"error": f"Unknown tool: {name}"}
        try:
            return await tool.run(**input_data, _session_data=session_data)
        except TypeError:
            return await tool.run(**input_data)
        except Exception as exc:  # pragma: no cover - defensive
            return {"error": f"Tool execution failed: {exc}"}

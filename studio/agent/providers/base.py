"""The provider interface: the only thing the agent loop knows about an LLM.

History is a list of provider-native items (Gemini steps, Anthropic messages, scripted dicts). The loop
stores each item verbatim and sends the list back unchanged, which preserves provider-required metadata
such as Gemini thought signatures and Anthropic thinking blocks.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Literal, Protocol

Stop = Literal["tool_use", "end", "max_tokens", "refusal"]


class ProviderError(RuntimeError):
    """The provider call failed (API error, failed interaction). Nothing was executed."""


class ProviderConfigError(ProviderError):
    """Missing credential, unknown model or unsupported capability, detected before any call."""


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    parameters: dict[str, Any]          # JSON schema


@dataclass(frozen=True)
class ToolCall:
    id: str
    name: str
    input: dict[str, Any]


@dataclass
class ToolOutcome:
    call_id: str
    name: str
    content: dict[str, Any]
    images: list[tuple[str, bytes]] = field(default_factory=list)    # (mime, bytes)
    is_error: bool = False

    def text(self) -> str:
        return json.dumps(self.content, default=str)


@dataclass
class Usage:
    input_tokens: int = 0               # billable input used for the cost calculation (see adapter)
    output_tokens: int = 0              # visible output
    thought_tokens: int = 0             # billed as output by both providers
    raw: dict = field(default_factory=dict)   # the provider's usage object as reported, for audit

    @property
    def billable_output(self) -> int:
        return self.output_tokens + self.thought_tokens


@dataclass
class Turn:
    items: list[dict[str, Any]]         # provider-native, appended to history verbatim
    text: str
    tool_calls: list[ToolCall]
    usage: Usage
    stop: Stop
    model: str


class Provider(Protocol):
    name: str
    model: str
    live: bool                          # True = network call that may cost money
    supports_tool_images: bool

    def verify(self) -> None:
        """Confirm credentials and that the model id exists. Raises ProviderConfigError."""
        ...

    def user_items(self, text: str) -> list[dict[str, Any]]: ...

    def tool_result_items(self, outcomes: list[ToolOutcome]) -> list[dict[str, Any]]: ...

    def estimate_input_tokens(self, system: str, history: list[dict[str, Any]], tools: list[ToolSpec]) -> int: ...

    def complete(self, *, system: str, history: list[dict[str, Any]], tools: list[ToolSpec],
                 max_output_tokens: int) -> Turn: ...


def rough_tokens(*parts: Any, images: int = 0) -> int:
    """Conservative estimate (~3.5 chars/token, +1,600 per image) used only for the spend cap."""
    chars = sum(len(p if isinstance(p, str) else json.dumps(p, default=str)) for p in parts)
    return int(chars / 3.5) + images * 1600

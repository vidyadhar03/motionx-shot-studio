"""Anthropic adapter: official `anthropic` SDK, Messages API, manual tool loop (the loop is ours so every
tool call is recorded before and after it runs).

Per the claude-api skill (2026-10): default model claude-opus-5-5 (adaptive thinking is always on; effort
in output_config, default medium); tool_choice auto; tool_result content may hold text and base64 image
blocks; thinking blocks must be passed back unchanged, so assistant content is stored verbatim.
Server-side model fallbacks are NOT enabled: this app does no automatic fallback.
"""
from __future__ import annotations

import base64
from typing import Any

from .base import (
    ProviderConfigError, ProviderError, ToolCall, ToolOutcome, ToolSpec, Turn, Usage, rough_tokens,
)

DEFAULT_MODEL = "claude-opus-5-5"


class AnthropicProvider:
    name = "anthropic"
    live = True
    supports_tool_images = True

    def __init__(self, *, model: str | None = None, api_key: str | None = None, effort: str = "low",
                 client: Any = None):
        self.model = model or DEFAULT_MODEL
        self.effort = effort if effort in ("low", "medium", "high", "xhigh", "max") else "low"
        if client is not None:
            self._client = client
        else:
            if not api_key:
                raise ProviderConfigError("Anthropic needs ANTHROPIC_API_KEY; none is configured")
            import anthropic
            self._client = anthropic.Anthropic(api_key=api_key)
        self._verified = False

    def verify(self) -> None:
        if self._verified:
            return
        import anthropic
        try:
            m = self._client.models.retrieve(self.model)
        except anthropic.APIError as e:
            raise ProviderConfigError(f"Anthropic model {self.model!r} could not be verified: {e}") from None
        if getattr(m, "id", None) != self.model:
            raise ProviderConfigError(f"Anthropic returned {getattr(m, 'id', None)!r} for {self.model!r}")
        self._verified = True

    def user_items(self, text: str) -> list[dict[str, Any]]:
        return [{"role": "user", "content": [{"type": "text", "text": text}]}]

    def tool_result_items(self, outcomes: list[ToolOutcome]) -> list[dict[str, Any]]:
        # All results of one assistant turn go back in ONE user message.
        blocks = []
        for o in outcomes:
            content: list[dict[str, Any]] = [{"type": "text", "text": o.text()}]
            content += [{"type": "image", "source": {"type": "base64", "media_type": mime,
                                                     "data": base64.b64encode(data).decode()}}
                        for mime, data in o.images]
            blocks.append({"type": "tool_result", "tool_use_id": o.call_id, "content": content,
                           "is_error": o.is_error})
        return [{"role": "user", "content": blocks}]

    def estimate_input_tokens(self, system: str, history: list[dict[str, Any]], tools: list[ToolSpec]) -> int:
        images = sum(1 for m in history for b in (m.get("content") or []) if isinstance(b, dict)
                     and b.get("type") == "tool_result" for c in b.get("content", []) if c.get("type") == "image")
        return rough_tokens(system, history, [t.__dict__ for t in tools], images=images)

    def complete(self, *, system: str, history: list[dict[str, Any]], tools: list[ToolSpec],
                 max_output_tokens: int) -> Turn:
        import anthropic
        try:
            resp = self._client.messages.create(
                model=self.model,
                max_tokens=max_output_tokens,
                system=system,
                tools=[{"name": t.name, "description": t.description, "input_schema": t.parameters} for t in tools],
                tool_choice={"type": "auto"},
                output_config={"effort": self.effort},
                messages=history,
            )
        except anthropic.APIError as e:
            raise ProviderError(f"Anthropic request failed: {e}") from None
        blocks = [b.model_dump(mode="json", exclude_none=True) for b in resp.content]
        calls = [ToolCall(id=b.id, name=b.name, input=dict(b.input)) for b in resp.content if b.type == "tool_use"]
        text = "\n".join(b.text for b in resp.content if b.type == "text")
        stop = {"tool_use": "tool_use", "max_tokens": "max_tokens", "refusal": "refusal"}.get(resp.stop_reason, "end")
        u = resp.usage
        usage = Usage(input_tokens=(u.input_tokens or 0) + (getattr(u, "cache_read_input_tokens", 0) or 0)
                      + (getattr(u, "cache_creation_input_tokens", 0) or 0),
                      output_tokens=u.output_tokens or 0)
        # Tools run only on a genuine tool_use stop; a refusal or truncated turn executes nothing.
        return Turn(items=[{"role": "assistant", "content": blocks}], text=text,
                    tool_calls=calls if stop == "tool_use" else [], usage=usage, stop=stop, model=self.model)

"""Gemini adapter: Google Gen AI SDK (`google-genai`), Interactions API in stateless mode.

Verified 2026-10-20 against ai.google.dev (function calling, thinking/signatures, models, pricing) and
the installed SDK (google-genai 2.31.0):
  * client.interactions.create(model, input=[steps], tools=[{"type": "function", ...}],
    system_instruction=str, store=False, generation_config={...})
  * response.steps: "thought" (signature, summary), "function_call" (id, name, arguments),
    "model_output" (content[]); response.status in {completed, requires_action, failed, incomplete,
    budget_exceeded, ...}; response.usage.total_input_tokens / total_output_tokens / total_thought_tokens
  * stateless mode: resend every received step unchanged (thought steps carry the signature)
  * function results: {"type": "function_result", "call_id", "name", "result": [text|image parts],
    "is_error"}; image parts are supported for Gemini 3+ models
Thinking tokens are billed as output.
"""
from __future__ import annotations

import base64
from typing import Any

from .base import (
    ProviderConfigError, ProviderError, ToolCall, ToolOutcome, ToolSpec, Turn, Usage, rough_tokens,
)

DEFAULT_MODEL = "gemini-3.8-flash"


class GeminiProvider:
    name = "gemini"
    live = True

    def __init__(self, *, model: str | None = None, api_key: str | None = None, vertex_project: str | None = None,
                 vertex_location: str = "global", thinking_level: str = "low", client: Any = None):
        self.model = model or DEFAULT_MODEL
        self.thinking_level = thinking_level
        # Multimodal function results are documented for Gemini 3 series and later.
        self.supports_tool_images = not self.model.startswith(("gemini-2", "gemini-1"))
        if client is not None:
            self._client = client                       # tests inject a mocked client
        else:
            if not api_key and not vertex_project:
                raise ProviderConfigError("Gemini needs GEMINI_API_KEY (or STUDIO_GEMINI_VERTEX_PROJECT with "
                                          "Application Default Credentials); none is configured")
            from google import genai
            self._client = (genai.Client(vertexai=True, project=vertex_project, location=vertex_location)
                            if vertex_project else genai.Client(api_key=api_key))
        self._verified = False

    def verify(self) -> None:
        if self._verified:
            return
        from google.genai import errors
        try:
            m = self._client.models.get(model=self.model)
        except errors.APIError as e:
            raise ProviderConfigError(f"Gemini model {self.model!r} could not be verified: {e}") from None
        if not getattr(m, "name", None):
            raise ProviderConfigError(f"Gemini returned no model record for {self.model!r}")
        self._verified = True

    def user_items(self, text: str) -> list[dict[str, Any]]:
        return [{"type": "user_input", "content": [{"type": "text", "text": text}]}]

    def tool_result_items(self, outcomes: list[ToolOutcome]) -> list[dict[str, Any]]:
        items = []
        for o in outcomes:
            parts: list[dict[str, Any]] = [{"type": "text", "text": o.text()}]
            if self.supports_tool_images:
                parts += [{"type": "image", "mime_type": mime, "data": base64.b64encode(data).decode()}
                          for mime, data in o.images]
            items.append({"type": "function_result", "call_id": o.call_id, "name": o.name, "result": parts,
                          "is_error": o.is_error})
        return items

    def estimate_input_tokens(self, system: str, history: list[dict[str, Any]], tools: list[ToolSpec]) -> int:
        images = sum(1 for it in history if it.get("type") == "function_result"
                     for p in it.get("result", []) if p.get("type") == "image")
        stripped = [{**it, "result": [p for p in it.get("result", []) if p.get("type") != "image"]}
                    if it.get("type") == "function_result" else it for it in history]
        return rough_tokens(system, stripped, [t.__dict__ for t in tools], images=images)

    def complete(self, *, system: str, history: list[dict[str, Any]], tools: list[ToolSpec],
                 max_output_tokens: int) -> Turn:
        from google.genai import errors
        try:
            resp = self._client.interactions.create(
                model=self.model,
                input=history,
                system_instruction=system,
                tools=[{"type": "function", "name": t.name, "description": t.description,
                        "parameters": t.parameters} for t in tools],
                store=False,                         # we own the history; resend steps verbatim
                generation_config={"max_output_tokens": max_output_tokens, "thinking_level": self.thinking_level,
                                   "tool_choice": "auto"},
            )
        except errors.APIError as e:
            raise ProviderError(f"Gemini request failed: {e}") from None
        status = str(getattr(resp, "status", ""))
        if status in ("failed", "cancelled"):
            raise ProviderError(f"Gemini interaction {status}: {getattr(resp, 'errors', None)}")
        steps = list(resp.steps or [])
        items = [s.model_dump(mode="json", exclude_unset=True) for s in steps]
        calls = [ToolCall(id=s.id, name=s.name, input=dict(s.arguments or {}))
                 for s in steps if getattr(s, "type", None) == "function_call"]
        text = "\n".join(c.text for s in steps if getattr(s, "type", None) == "model_output"
                         for c in (s.content or []) if getattr(c, "type", None) == "text" and getattr(c, "text", None))
        u = resp.usage
        usage = Usage(input_tokens=getattr(u, "total_input_tokens", 0) or 0,
                      output_tokens=getattr(u, "total_output_tokens", 0) or 0,
                      thought_tokens=getattr(u, "total_thought_tokens", 0) or 0) if u else Usage()
        stop = ("tool_use" if calls else
                "max_tokens" if status in ("incomplete", "budget_exceeded") else "end")
        return Turn(items=items, text=text, tool_calls=calls, usage=usage, stop=stop, model=self.model)

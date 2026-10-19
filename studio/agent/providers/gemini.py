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

Retries: the Interactions client retries 408/409/429/5xx up to 3 times by default, and setting
HttpOptions.retry_options.attempts=0 still leaves 1 retry (verified offline 2026-10-20 with a mock
transport). A retried POST can be billed twice, so this adapter sets the Interactions client's retry
strategy to "none" and refuses to call if that is not in effect. Model verification uses a separate
client so the classic client's retry handling cannot alter the Interactions configuration.

Errors: Interactions calls raise google.genai._gaos.lib.compat_errors.* (NOT google.genai.errors.APIError);
both families, plus transport errors, are mapped to ProviderError.
"""
from __future__ import annotations

import base64
from typing import Any

from .base import (
    ProviderConfigError, ProviderError, ToolCall, ToolOutcome, ToolSpec, Turn, Usage, rough_tokens,
)

DEFAULT_MODEL = "gemini-3.8-flash"


def _api_errors() -> tuple[type[BaseException], ...]:
    import httpx
    from google.genai import errors
    out: list[type[BaseException]] = [errors.APIError, httpx.HTTPError]
    try:
        from google.genai._gaos.lib.compat_errors import GeminiNextGenAPIClientError
        out.append(GeminiNextGenAPIClientError)
    except ImportError:                                  # SDK layout changed: fail loudly at review time
        pass
    return tuple(out)


API_ERRORS = _api_errors()


def _safe(e: BaseException) -> str:
    text = str(e)
    return "<redacted>" if "AIza" in text else text[:600]


def gemini_usage(u: Any) -> Usage:
    """Billable usage from an Interactions `Usage`, conservatively.

    Found in the first live run (2026-10-20): `total_input_tokens` grew far less than the function-result
    content added to the history, so tool results appear to be counted in `total_tool_use_tokens`
    ("tokens present in tool-use prompt(s)"). The docs do not state how those are billed, so they are
    treated as input. Billable input = max(input + tool_use, total - output - thought); thoughts are
    reported separately from output and billed as output. Cached input is still charged at the full rate.
    """
    if u is None:
        return Usage()
    raw = u.model_dump(mode="json", exclude_none=True) if hasattr(u, "model_dump") else dict(u)
    g = lambda k: int(raw.get(k) or 0)  # noqa: E731
    out, thought = g("total_output_tokens"), g("total_thought_tokens")
    billable_in = max(g("total_input_tokens") + g("total_tool_use_tokens"), g("total_tokens") - out - thought)
    return Usage(input_tokens=billable_in, output_tokens=out, thought_tokens=thought, raw=raw)


def disable_interactions_retries(client: Any) -> None:
    from google.genai._gaos.utils import RetryConfig
    client.interactions.sdk_configuration.retry_config = RetryConfig("none", None, False)


def check_no_retries(client: Any) -> None:
    """Refuse to send if automatic retries are in effect (a retried POST may be billed twice)."""
    cfg = getattr(getattr(client.interactions, "sdk_configuration", None), "retry_config", None)
    if cfg is None:                                      # injected mock clients have no SDK configuration
        return
    if getattr(cfg, "strategy", None) != "none":
        raise ProviderConfigError(f"Gemini Interactions retries are enabled (strategy {cfg.strategy!r}); refusing to call")


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
            self._client = self._meta = client          # tests inject a mocked client
        else:
            if not api_key and not vertex_project:
                raise ProviderConfigError("Gemini needs GEMINI_API_KEY (or STUDIO_GEMINI_VERTEX_PROJECT with "
                                          "Application Default Credentials); none is configured")
            from google import genai

            def make():
                return (genai.Client(vertexai=True, project=vertex_project, location=vertex_location)
                        if vertex_project else genai.Client(api_key=api_key))
            self._client, self._meta = make(), make()    # interactions client / model-metadata client
            disable_interactions_retries(self._client)
        self._verified = False
        self.verified_model: dict[str, Any] | None = None

    def verify(self) -> None:
        if self._verified:
            return
        try:
            m = self._meta.models.get(model=self.model)
        except API_ERRORS as e:
            raise ProviderConfigError(f"Gemini model {self.model!r} could not be verified: {_safe(e)}") from None
        if not getattr(m, "name", None):
            raise ProviderConfigError(f"Gemini returned no model record for {self.model!r}")
        self.verified_model = {k: getattr(m, k, None) for k in ("name", "display_name", "version",
                               "input_token_limit", "output_token_limit", "supported_actions", "thinking")}
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
        check_no_retries(self._client)
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
        except API_ERRORS as e:
            raise ProviderError(f"Gemini request failed: {_safe(e)}") from None
        status = str(getattr(resp, "status", ""))
        if status in ("failed", "cancelled"):
            raise ProviderError(f"Gemini interaction {status}: {getattr(resp, 'errors', None)}")
        steps = list(resp.steps or [])
        items = [s.model_dump(mode="json", exclude_unset=True) for s in steps]
        calls = [ToolCall(id=s.id, name=s.name, input=dict(s.arguments or {}))
                 for s in steps if getattr(s, "type", None) == "function_call"]
        text = "\n".join(c.text for s in steps if getattr(s, "type", None) == "model_output"
                         for c in (s.content or []) if getattr(c, "type", None) == "text" and getattr(c, "text", None))
        usage = gemini_usage(resp.usage)
        stop = ("tool_use" if calls else
                "max_tokens" if status in ("incomplete", "budget_exceeded") else "end")
        return Turn(items=items, text=text, tool_calls=calls, usage=usage, stop=stop, model=self.model)

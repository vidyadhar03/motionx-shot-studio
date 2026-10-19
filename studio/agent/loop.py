"""The one agent loop. Provider-agnostic; owns turns, limits, spend, the tool-call ledger and persistence.

Replay safety: a tool call is recorded `started` before it runs and `done`/`error` after. A call id
seen again returns the stored result without executing; a call left `started` by a crash is never
re-run (the model is told to re-read). Reloading a thread only reads rows; it executes nothing.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Callable

from ..config import Settings
from ..generation import GenerationService
from ..media import MediaStore
from ..ops import Ops
from . import pricing
from .providers.base import Provider, ProviderConfigError, ProviderError, ToolCall, ToolOutcome
from .store import AgentStore
from .tools import SPECS, AgentTools, outcome_from_record, outcome_record

log = logging.getLogger("studio.agent")


class AgentBudgetError(RuntimeError):
    """A live LLM call was refused by the LLM spend cap or request cap (independent of Comfy credits)."""


SYSTEM_RULES = """You are the MotionX Shot Studio directing assistant, working inside ONE film project.
Project state lives in tools, not in this conversation: read before you write, and never invent what you can read.
Tools: list, read, write, propose_generation. You can edit DRAFT shots and create scenes. You can only PROPOSE
generations; a person approves, submits, reviews and selects. You cannot change assets, decisions, budgets or
locked shots. Load /skills/shot-direction before revising a shot; it maps review notes to shot fields.
Every write needs the shot's current revision; if a write is refused, read again and adjust. If a tool refusal or
limit changed your plan, say so plainly. Finish by telling the person what you changed and what awaits approval."""


@dataclass
class TurnReport:
    turns: int
    stop: str
    spent_usd: float


def make_provider(settings: Settings, provider: str, model: str | None) -> Provider:
    """No automatic fallback: an unavailable provider is an error, never a silent switch."""
    if provider == "scripted":
        from .providers.scripted import ScriptedProvider
        return ScriptedProvider()
    if provider == "gemini":
        from .providers.gemini import GeminiProvider
        return GeminiProvider(model=model or None, api_key=settings.gemini_api_key,
                              vertex_project=settings.gemini_vertex_project,
                              vertex_location=settings.gemini_vertex_location, thinking_level=settings.agent_thinking)
    if provider == "anthropic":
        from .providers.anthropic_provider import AnthropicProvider
        return AnthropicProvider(model=model or None, api_key=settings.anthropic_api_key, effort=settings.agent_thinking)
    raise ProviderConfigError(f"unknown agent provider {provider!r}; use scripted, gemini or anthropic")


class AgentRunner:
    def __init__(self, settings: Settings, ops: Ops, service: GenerationService, media: MediaStore,
                 store: AgentStore, provider_factory: Callable[[str, str], Provider] | None = None):
        self.settings, self.ops, self.service, self.media, self.store = settings, ops, service, media, store
        self._factory = provider_factory or (lambda p, m: make_provider(settings, p, m))

    def default_model(self, provider: str) -> str:
        if self.settings.agent_model:
            return self.settings.agent_model
        return {"scripted": "scripted-revise-v1", "gemini": "gemini-3.8-flash", "anthropic": "claude-opus-5-5"}.get(
            provider, "")

    def create_thread(self, project_id: str, provider: str | None = None, model: str | None = None) -> dict:
        self.ops.get_project(project_id)
        provider = provider or self.settings.agent_provider
        return self.store.create_thread(project_id, provider, model or self.default_model(provider))

    def system_prompt(self, project_id: str, focus_shot_id: str | None) -> str:
        p = self.ops.get_project(project_id)
        assets = ", ".join(f"@{a['handle']} v{a['current_version']} ({a['kind']})" for a in self.ops.list_assets(project_id))
        return (f"{SYSTEM_RULES}\n\nProject: {p['name']}\nBrief: {p['brief'][:400]}\nDirection: {p['direction']}\n"
                f"Assets: {assets or 'none'}\nSkills: /skills/shot-direction (shot grammar, how notes map to fields)\n"
                f"Focus shot: {focus_shot_id or 'none'}")

    # -- one user message ---------------------------------------------------------------------
    def send(self, thread_id: str, text: str, focus_shot_id: str | None = None) -> TurnReport:
        thread = self.store.thread(thread_id)
        provider = self._factory(thread["provider"], thread["model"])
        if provider.live:
            self._check_live_allowed(provider)          # before ANY network call, incl. verification
            provider.verify()
        tools = AgentTools(thread["project_id"], self.ops, self.service, self.media)
        system = self.system_prompt(thread["project_id"], focus_shot_id)
        self.store.append(thread_id, "user", {"text": text, "focus_shot_id": focus_shot_id})
        self.store.append_items(thread_id, provider.user_items(text))
        history = self.store.provider_items(thread_id)
        stop = "end"
        for turn in range(1, self.settings.agent_max_turns + 1):
            pre = None
            if provider.live:
                try:
                    pre = self._check_budget(provider, system, history)
                except AgentBudgetError as e:          # mid-thread: stop cleanly and say why
                    if turn == 1:
                        raise
                    self.store.append(thread_id, "notice", {"level": "warn", "text": f"stopped before request {turn}: {e}"})
                    return TurnReport(turn - 1, "budget", self.store.live_spend_usd())
            try:
                t = provider.complete(system=system, history=history, tools=SPECS,
                                      max_output_tokens=self.settings.agent_max_output_tokens)
            except ProviderError as e:
                self.store.append(thread_id, "notice", {"level": "error", "text": f"{provider.name}: {e}"})
                return TurnReport(turn, "error", self.store.live_spend_usd())
            est = pricing.usd(provider.model, t.usage.input_tokens, t.usage.billable_output) if provider.live else 0.0
            self.store.record_usage(thread_id, provider.name, provider.model, t.usage.input_tokens,
                                    t.usage.billable_output, est, provider.live, thought_tokens=t.usage.thought_tokens,
                                    pre_estimate_usd=pre, raw_usage=t.usage.raw,
                                    calc_method=getattr(provider, "calc_method", None))
            if pre is not None and est > pre:
                # The pre-call figure is an estimate, not a bound; if reality exceeded it, stop and report.
                self.store.append_items(thread_id, t.items)
                if t.tool_calls:                       # keep history well-formed: every call gets a result
                    skipped = [ToolOutcome(c.id, c.name, {"error": "NotExecuted", "message": "stopped: spend estimate "
                                           "exceeded"}, is_error=True) for c in t.tool_calls]
                    self.store.append_items(thread_id, provider.tool_result_items(skipped))
                self.store.append(thread_id, "notice", {"level": "warn", "text":
                                  f"request {turn} cost ${est:.5f}, above its ${pre:.5f} estimate; stopped"})
                return TurnReport(turn, "estimate_exceeded", self.store.live_spend_usd())
            self.store.append_items(thread_id, t.items)
            history += t.items
            if t.text:
                self.store.append(thread_id, "assistant_text", {"text": t.text, "stop": t.stop})
            stop = t.stop
            if t.stop != "tool_use" or not t.tool_calls:
                if t.stop in ("max_tokens", "refusal"):
                    self.store.append(thread_id, "notice", {"level": "warn", "text": f"turn ended: {t.stop}"})
                return TurnReport(turn, stop, self.store.live_spend_usd())
            outcomes = [self._execute(thread_id, tools, call) for call in t.tool_calls]
            if not provider.supports_tool_images:
                for o in outcomes:
                    if o.images:
                        o.content = {**o.content, "image": "omitted: this model cannot take images in tool results"}
                        o.images = []
            items = provider.tool_result_items(outcomes)
            self.store.append_items(thread_id, items)
            history += items
        self.store.append(thread_id, "notice", {"level": "warn",
                                                "text": f"stopped at the turn limit ({self.settings.agent_max_turns})"})
        return TurnReport(self.settings.agent_max_turns, "turn_limit", self.store.live_spend_usd())

    def _execute(self, thread_id: str, tools: AgentTools, call: ToolCall) -> ToolOutcome:
        if not self.store.start_call(thread_id, call.id, call.name, call.input):
            prior = self.store.call(thread_id, call.id)
            if prior["status"] in ("done", "error"):
                return outcome_from_record(call.id, call.name, prior["result"], self.media)     # no re-execution
            msg = {"error": "Interrupted", "message": "this call was interrupted earlier; its effect is unknown. "
                                                     "Re-read the affected path before trying again."}
            self.store.finish_call(thread_id, call.id, "interrupted", {"content": msg, "is_error": True})
            return ToolOutcome(call.id, call.name, msg, is_error=True)
        outcome = tools.execute(call)
        self.store.finish_call(thread_id, call.id, "error" if outcome.is_error else "done", outcome_record(outcome))
        return outcome

    # -- live gates -----------------------------------------------------------------------------
    def _check_live_allowed(self, provider: Provider) -> None:
        if self.settings.agent_max_live_requests <= 0:
            raise AgentBudgetError("live calls are disabled: STUDIO_AGENT_MAX_LIVE_REQUESTS is 0")
        if self.settings.agent_budget_usd <= 0:
            raise AgentBudgetError(f"live {provider.name} calls are disabled: STUDIO_AGENT_BUDGET_USD is 0 "
                                   "(the LLM spend cap is separate from Comfy credits)")
        try:
            pricing.price_for(provider.model)
        except pricing.UnknownPrice as e:
            raise AgentBudgetError(str(e)) from None

    def _check_budget(self, provider: Provider, system: str, history: list[dict]) -> float:
        """Pre-call ESTIMATE, not a guaranteed bound: input is approximated from characters (+ a per-image
        allowance) and thinking is assumed to stay within agent_thought_allowance, which the provider does not
        guarantee. Returns the estimate; raises if spent + estimate would exceed the cap or the request cap."""
        if self.store.live_requests() >= self.settings.agent_max_live_requests:
            raise AgentBudgetError(f"live request cap reached ({self.settings.agent_max_live_requests})")
        est_in = provider.estimate_input_tokens(system, history, SPECS)
        est = pricing.usd(provider.model, est_in,
                          self.settings.agent_max_output_tokens + self.settings.agent_thought_allowance)
        spent = self.store.live_spend_usd()
        if spent + est > self.settings.agent_budget_usd:
            raise AgentBudgetError(f"next {provider.name} request is estimated at ${est:.4f}; ${spent:.4f} of the "
                                   f"${self.settings.agent_budget_usd:.2f} LLM cap is already used")
        return est

    # -- reading a thread (never executes anything) --------------------------------------------
    def view(self, thread_id: str) -> dict:
        thread = self.store.thread(thread_id)
        return {"thread": thread, "messages": self.store.messages(thread_id), "tool_calls": self.store.calls(thread_id),
                "usage": self.store.usage(thread_id), "live_spend_usd": self.store.live_spend_usd()}

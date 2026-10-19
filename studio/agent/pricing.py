"""LLM price table used ONLY for the agent spend cap (estimates, not invoices).

Sources, read 2026-10-20:
  Gemini   https://ai.google.dev/gemini-api/docs/pricing  (Standard paid tier; thinking billed as output)
  Anthropic claude-api skill model table (cached 2026-10-06), first-party API rates
A free tier is never assumed. A model without an entry here cannot be used live: the cap must be
computable before the call.
"""
from __future__ import annotations

from datetime import date

# model -> list of (valid_from, input $/1M, output $/1M), newest last
PRICES: dict[str, list[tuple[date, float, float]]] = {
    "gemini-3.8-flash": [(date(2026, 1, 1), 0.75, 3.75), (date(2027, 1, 1), 1.50, 7.50)],
    "gemini-3.6-flash": [(date(2026, 1, 1), 0.75, 3.75), (date(2027, 1, 1), 1.50, 7.50)],
    "gemini-4-argon": [(date(2026, 1, 1), 2.00, 10.00), (date(2026, 12, 1), 4.00, 20.00)],
    "gemini-3.5-flash-lite": [(date(2026, 1, 1), 0.30, 2.50)],
    "claude-opus-5-5": [(date(2026, 1, 1), 4.00, 20.00)],
    "claude-sonnet-5-5": [(date(2026, 1, 1), 2.00, 10.00)],
    "claude-haiku-5-5": [(date(2026, 1, 1), 0.10, 0.50)],
}


# How est_usd was calculated. "documented" = stated in official docs; "inferred" = our reading, not confirmed.
CALC_METHODS: dict[str, dict[str, str]] = {
    "none": {"certainty": "no_charge", "formula": "scripted provider: no network call"},
    "gemini.v1": {
        "certainty": "incomplete",
        "formula": "total_input_tokens x input + (total_output_tokens + total_thought_tokens) x output",
        "caveat": "total_tool_use_tokens, total_tokens and the modality breakdown were NOT recorded for these rows; "
                  "function-result content appears to be reported outside total_input_tokens, so this may "
                  "understate the charge. Not reconstructed.",
    },
    "gemini.v2": {
        "certainty": "calculated_conservative",
        "formula": "max(total_input_tokens + total_tool_use_tokens, total_tokens - output - thought) x input + "
                   "(total_output_tokens + total_thought_tokens) x output",
        "documented": "thinking billed at the output price; image tokens are part of input; thoughts reported "
                      "separately from output (total = input + output + thought)",
        "inferred": "that total_tool_use_tokens are billed as input for client function calls (the field is "
                    "documented, its billing is not); cached input charged at the full rate (overstates)",
    },
    "anthropic.v1": {
        "certainty": "calculated_conservative",
        "formula": "(input + cache_read + cache_creation) x input + output x output",
        "inferred": "cache reads charged at the full input rate (overstates)",
    },
}


class UnknownPrice(LookupError):
    pass


def price_for(model: str, on: date | None = None) -> tuple[float, float]:
    schedule = PRICES.get(model)
    if not schedule:
        raise UnknownPrice(f"no price on file for {model!r}; add it to studio/agent/pricing.py before live use")
    on = on or date.today()
    current = [p for p in schedule if p[0] <= on] or schedule[:1]
    _, inp, out = current[-1]
    return inp, out


def usd(model: str, input_tokens: int, output_tokens: int, on: date | None = None) -> float:
    inp, out = price_for(model, on)
    return round(input_tokens / 1e6 * inp + output_tokens / 1e6 * out, 6)

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

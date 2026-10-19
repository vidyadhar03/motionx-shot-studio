"""Read-only Comfy account balance (GET https://api.comfy.org/customers/balance).

Used to observe the real charge of a paid take as a before/after delta. This module never calls
any purchase endpoint. Amounts come back in cents; credits are converted at the published
rate of 211 credits per USD.
"""
from __future__ import annotations

import httpx

BALANCE_URL = "https://api.comfy.org/customers/balance"
CREDITS_PER_USD = 211


def fetch_balance_credits(api_key: str | None, timeout: float = 10.0) -> float | None:
    if not api_key:
        return None
    try:
        r = httpx.get(BALANCE_URL, headers={"X-API-Key": api_key}, timeout=timeout)
        if r.status_code != 200:
            return None
        cents = r.json().get("amount_cents")
        return None if cents is None else round(float(cents) / 100 * CREDITS_PER_USD, 2)
    except (httpx.HTTPError, ValueError):
        return None

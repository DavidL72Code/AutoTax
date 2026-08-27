"""Node 4 — the only node allowed to spend a model call on extraction.

It sees just the fields the rules could not prove and just the financially
relevant lines of the body. Concurrent escalations are coalesced into a single
Gemini request by `llm.EXTRACT`, so a 40-email sync still costs a few calls.
"""
from __future__ import annotations

import time

from ... import llm
from .. import patterns
from ..state import Draft, ReceiptState, missing_fields
from ._util import step

_NUMERIC = ("amount", "tax", "subtotal")


def _coerce(field: str, value) -> object:
    if value is None or value == "":
        return None
    if field in _NUMERIC:
        return patterns.money(value)
    text = str(value).strip()
    return text or None


async def escalate(state: ReceiptState) -> dict:
    started = time.perf_counter()
    email = state.get("email") or {}
    attempts = state.get("attempts", 0) + 1
    wanted = state.get("missing") or missing_fields(state.get("draft") or {})
    if not wanted:
        return {"attempts": attempts, "steps": [step("escalate", "nothing to ask", started)]}

    if not llm.available():
        return {
            "attempts": attempts,
            "steps": [step("escalate", "skipped — no API key configured", started)],
        }

    try:
        result = await llm.EXTRACT.submit(
            {
                "sender": email.get("sender", ""),
                "subject": email.get("subject", ""),
                "snippet": patterns.financial_snippet(email.get("body") or ""),
                "missing": wanted,
            }
        )
    except Exception as exc:  # noqa: BLE001 - a failed call is a soft failure
        return {
            "attempts": attempts,
            "llm_calls": state.get("llm_calls", 0) + 1,
            "issues": [*(state.get("issues") or []), f"llm_error: {type(exc).__name__}"],
            "steps": [step("escalate", f"model call failed: {exc}", started)],
        }

    draft: Draft = {}
    sources: dict[str, str] = {}
    for field in wanted:
        value = _coerce(field, (result or {}).get(field))
        if value is not None:
            draft[field] = value  # type: ignore[literal-required]
            sources[field] = "llm"

    merged = {**(state.get("draft") or {}), **draft}
    filled = ", ".join(f"{k}={v}" for k, v in draft.items()) or "nothing"
    return {
        "draft": draft,
        "sources": sources,
        "attempts": attempts,
        "llm_calls": state.get("llm_calls", 0) + 1,
        "missing": missing_fields(merged),
        "steps": [step("escalate", f"asked for {', '.join(wanted)} → {filled}", started)],
    }

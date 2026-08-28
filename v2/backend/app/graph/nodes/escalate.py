"""Node 4 — the only node allowed to spend a model call on extraction.

It sees just the fields the rules could not prove and just the financially
relevant lines of the body. Concurrent escalations are coalesced into a single
Gemini request by `llm.EXTRACT`, so a 40-email sync still costs a few calls.
"""
from __future__ import annotations

import time

from ... import llm
from .. import patterns
from ..state import Draft, ReceiptState, missing_fields, score
from ._util import step

_NUMERIC = ("amount", "tax", "subtotal")

# Not a defect in the receipt. It marks a record that reached the queue because
# the one automatic recovery path was unavailable, so a reader can tell "retry
# this later" apart from "read this email and decide".
MODEL_UNAVAILABLE = "model_unavailable"


def _confidence(value) -> float | None:
    """The model is asked for 0-1 and mostly obliges. Anything unparseable is
    treated as no answer rather than as a confident one."""
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return round(min(1.0, max(0.0, number)), 3)


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
        return {"attempts": attempts, "steps": [step("escalate", "nothing to ask", started, key="trace.escalate.nothing")]}

    if not llm.available():
        return {
            "attempts": attempts,
            "issues": [*(state.get("issues") or []), MODEL_UNAVAILABLE],
            "steps": [step("escalate", "skipped — no API key configured", started, key="trace.escalate.no_key")],
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
            "issues": [*(state.get("issues") or []), MODEL_UNAVAILABLE],
            "steps": [step("escalate", f"model call failed: {exc}", started,
                       key="trace.escalate.failed", params={"error": type(exc).__name__})],
        }

    draft: Draft = {}
    sources: dict[str, str] = {}
    reported = (result or {}).get("confidence") or {}
    if not isinstance(reported, dict):
        reported = {}
    self_scores: dict[str, float] = {}
    for field in wanted:
        value = _coerce(field, (result or {}).get(field))
        if value is not None:
            draft[field] = value  # type: ignore[literal-required]
            sources[field] = "llm"
            said = _confidence(reported.get(field))
            if said is not None:
                self_scores[field] = said

    merged = {**(state.get("draft") or {}), **draft}
    merged_sources = {**(state.get("sources") or {}), **sources}
    merged_confidence = {**(state.get("model_confidence") or {}), **self_scores}
    filled = (
        ", ".join(
            f"{k}={v}" + (f" @{self_scores[k]:.2f}" if k in self_scores else " @unscored")
            for k, v in draft.items()
        )
        or "nothing"
    )
    return {
        "draft": draft,
        "sources": sources,
        "model_confidence": merged_confidence,
        "attempts": attempts,
        "llm_calls": state.get("llm_calls", 0) + 1,
        "missing": missing_fields(merged),
        "steps": [step("escalate", f"asked for {', '.join(wanted)} → {filled}", started,
                       score(merged, merged_sources, state.get("issues") or [], merged_confidence),
                       key="trace.escalate.asked",
                       params={"fields": list(wanted), "filled": filled})],
    }

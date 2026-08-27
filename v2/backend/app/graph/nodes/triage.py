"""Node 1 — is this email a purchase at all?

Cheap signals decide the clear cases. Only genuinely ambiguous emails cost a
model call, and those are coalesced into a shared batch by `llm.TRIAGE`.
"""
from __future__ import annotations

import re
import time

from ... import llm
from .. import patterns
from ..state import ReceiptState
from ._util import step

_HAS_MONEY = re.compile(r"\$\s?[\d,]+\.\d{2}")


async def triage(state: ReceiptState) -> dict:
    started = time.perf_counter()
    email = state.get("email") or {}
    subject = email.get("subject") or ""
    body = email.get("body") or ""

    purchase = bool(patterns.PURCHASE_SIGNAL.search(body) or patterns.PURCHASE_SIGNAL.search(subject))
    promo = bool(patterns.PROMO_SUBJECT.search(subject) or patterns.PROMO_BODY.search(body))
    shipping = bool(patterns.SHIPPING_ONLY.search(subject)) and not purchase
    money = bool(_HAS_MONEY.search(body))

    if purchase and not promo:
        return _decision(state, True, "purchase signal in body", started, "regex")
    if shipping:
        return _decision(state, False, "shipping status, not a purchase", started, "regex")
    if promo and not purchase:
        return _decision(state, False, "marketing copy without purchase evidence", started, "regex")

    if llm.available():
        try:
            verdict = await llm.TRIAGE.submit(
                {
                    "sender": email.get("sender", ""),
                    "subject": subject,
                    "snippet": patterns.financial_snippet(body, 400),
                }
            )
            if verdict is not None:
                is_receipt = bool(verdict.get("receipt"))
                why = str(verdict.get("why") or "model judgement")[:60]
                out = _decision(state, is_receipt, why, started, "llm")
                out["llm_calls"] = state.get("llm_calls", 0) + 1
                return out
        except Exception as exc:  # noqa: BLE001 - fall through to the heuristic
            return _decision(state, money, f"model unavailable ({type(exc).__name__}), used amount heuristic", started, "heuristic")

    return _decision(state, money, "amount present but no explicit purchase wording", started, "heuristic")


def _decision(state: ReceiptState, is_receipt: bool, why: str, started: float, how: str) -> dict:
    return {
        "is_receipt": is_receipt,
        "triage_reason": why,
        "status": "pending" if is_receipt else "skipped",
        "steps": [step("triage", f"{'receipt' if is_receipt else 'not a receipt'} — {why} [{how}]", started)],
    }

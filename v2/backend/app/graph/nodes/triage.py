"""Node 1, is this email a purchase at all?

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

    # These two are read from the subject alone, and the subject is the point:
    # it is what the merchant says the email is *about*, where the body is
    # whatever else they chose to restate. A delivery notice quotes the order
    # total; a refund confirmation quotes the original figures. Both look like
    # purchases in the body and neither is one.
    #
    # `shipping` used to carry `and not purchase`, which any body mentioning
    # "Order total" defeated, so "Your package is out for delivery" was banked
    # as a second purchase of money already spent. It is unconditional now,
    # including over purchase wording in the subject, because "Your order
    # #12345 has shipped" is still a shipping notice. The trade is deliberate:
    # skipping a real receipt leaves a visible gap, while inventing spend
    # corrupts every total that reads it and shows nothing.
    shipping = bool(patterns.SHIPPING_ONLY.search(subject))
    refund = bool(patterns.REFUND_SIGNAL.search(subject))
    money = bool(_HAS_MONEY.search(body))

    # Both ahead of the purchase branch, for the reason above: each one restates
    # figures that would otherwise read as fresh spend.
    if refund:
        return _decision(state, True, "refund_confirmed", started, "regex", refund=True)
    if shipping:
        return _decision(state, False, "shipping_only", started, "regex")
    if purchase and not promo:
        return _decision(state, True, "purchase_signal", started, "regex")
    if promo and not purchase:
        return _decision(state, False, "marketing", started, "regex")

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
                # A code, not a sentence: it translates, it is countable, and
                # anything unrecognised degrades to `unclear` rather than to
                # untranslatable prose.
                reason = str(verdict.get("why") or "unclear").strip().lower()
                if reason not in REASONS:
                    reason = "purchase_confirmed" if is_receipt else "unclear"
                out = _decision(state, is_receipt, reason, started, "llm")
                out["llm_calls"] = state.get("llm_calls", 0) + 1
                return out
        except Exception as exc:  # noqa: BLE001 - fall through to the heuristic
            return _decision(state, money, "model_unavailable", started, "heuristic")

    return _decision(state, money, "amount_only", started, "heuristic")


# Every reason this node can give, as a code. The English is here so a trace
# read as text still says something; the code is what a translated UI renders.
# The model picks from the same list, which is why nothing here is open text.
REASONS = {
    "purchase_signal": "purchase signal in body",
    "shipping_only": "shipping status, not a purchase",
    "refund_confirmed": "refund, recorded as money returned",
    "marketing": "marketing copy without purchase evidence",
    "amount_only": "amount present but no explicit purchase wording",
    "model_unavailable": "model unavailable, used amount heuristic",
    # what the model may return
    "purchase_confirmed": "confirms a completed purchase",
    "order_placed": "confirms an order was placed",
    "payment_received": "confirms a payment",
    "account_notice": "account notice, not a purchase",
    "unclear": "no clear purchase evidence",
}


def _decision(state: ReceiptState, is_receipt: bool, reason: str, started: float, how: str,
              *, refund: bool = False) -> dict:
    why = REASONS.get(reason, reason)
    return {
        "is_receipt": is_receipt,
        "is_refund": refund,
        "triage_reason": why,
        "status": "pending" if is_receipt else "skipped",
        "steps": [step("triage", f"{'receipt' if is_receipt else 'not a receipt'}, {why} [{how}]", started,
             key="trace.triage.receipt" if is_receipt else "trace.triage.not_receipt",
             params={"reason": reason, "how": how})],
    }

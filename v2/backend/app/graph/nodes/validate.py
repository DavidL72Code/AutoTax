"""Node 6 — the check that makes a retry worth doing.

Anything caught here is a concrete, explainable defect: a total that does not
match its own line items, a tax larger than the purchase, a missing merchant.
Confirmed problems send the record back to `escalate` once, then to review.
"""
from __future__ import annotations

import time
from datetime import date, timedelta

from dateutil import parser as date_parser

from ..state import NON_DATA_ISSUES, ReceiptState, score
from ._util import step

MAX_PLAUSIBLE_AMOUNT = 100_000.0
MAX_TAX_RATE = 0.35

# Which field a model should be re-asked about when a check fails. Issues not
# listed here (a bad date, say) are recorded but never worth another call.
RETRYABLE = {
    "vendor_missing": ("vendor",),
    "amount_missing": ("amount",),
    "amount_not_positive": ("amount",),
    "amount_implausible": ("amount",),
    "tax_negative": ("tax",),
    "tax_exceeds_plausible_share": ("tax", "amount"),
    "total_does_not_reconcile": ("amount", "tax"),
}


async def validate(state: ReceiptState) -> dict:
    started = time.perf_counter()
    draft = state.get("draft") or {}
    issues: list[str] = []

    amount = draft.get("amount")
    tax = draft.get("tax")
    subtotal = draft.get("subtotal")

    if not draft.get("vendor"):
        issues.append("vendor_missing")
    if amount is None:
        issues.append("amount_missing")
    elif amount <= 0:
        issues.append("amount_not_positive")
    elif amount > MAX_PLAUSIBLE_AMOUNT:
        issues.append("amount_implausible")

    if amount and tax is not None:
        if tax < 0:
            issues.append("tax_negative")
        elif tax > amount * MAX_TAX_RATE:
            issues.append("tax_exceeds_plausible_share")

    if amount and subtotal is not None and tax is not None:
        drift = abs((subtotal + tax) - amount)
        if drift > max(0.05, amount * 0.02):
            issues.append("total_does_not_reconcile")

    parsed_date = draft.get("date")
    if parsed_date:
        try:
            value = date_parser.parse(str(parsed_date)).date()
            if value > date.today() + timedelta(days=2):
                issues.append("date_in_future")
        except (ValueError, OverflowError, TypeError):
            issues.append("date_unparseable")

    # `validate` recomputes the data issues from the draft every pass, which
    # would otherwise erase what `escalate` recorded about the run itself. Those
    # are not derivable from the draft, so they are carried forward explicitly.
    for carried in (state.get("issues") or []):
        if carried in NON_DATA_ISSUES and carried not in issues:
            issues.append(carried)

    retry_fields: list[str] = []
    for issue in issues:
        for field in RETRYABLE.get(issue, ()):
            if field not in retry_fields:
                retry_fields.append(field)

    detail = "clean" if not issues else ", ".join(issues)
    return {
        "issues": issues,
        "missing": retry_fields,
        "steps": [step("validate", detail, started,
                       score(draft, state.get("sources") or {}, issues,
                             state.get("model_confidence") or {}),
                       key="trace.validate.clean" if not issues else "trace.validate.issues",
                       params={"issues": issues})],
    }

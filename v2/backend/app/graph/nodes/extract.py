"""Node 2 — pull every field a regex can prove, so the model only sees gaps."""
from __future__ import annotations

import time

from dateutil import parser as date_parser

from .. import patterns
from ..state import Draft, ReceiptState, missing_fields
from ._util import step


def _normalise_date(raw: str | None) -> str | None:
    if not raw:
        return None
    try:
        return date_parser.parse(str(raw)).date().isoformat()
    except (ValueError, OverflowError, TypeError):
        return None


async def extract(state: ReceiptState) -> dict:
    started = time.perf_counter()
    email = state.get("email") or {}
    body = email.get("body") or ""
    text = f"{email.get('subject', '')}\n{body}"

    draft: Draft = {}
    sources: dict[str, str] = {}

    for field, value in (
        ("amount", patterns.extract_amount(text)),
        ("tax", patterns.extract_tax(text)),
        ("subtotal", patterns.extract_subtotal(text)),
        ("order_number", patterns.extract_order_number(text)),
        ("payment_method", patterns.extract_payment_method(text)),
    ):
        if value is not None:
            draft[field] = value  # type: ignore[literal-required]
            sources[field] = "regex"

    date = _normalise_date(email.get("date"))
    if date:
        draft["date"] = date
        sources["date"] = "regex"

    merged = {**(state.get("draft") or {}), **draft}
    found = ", ".join(f"{k}={draft[k]}" for k in ("amount", "tax") if k in draft) or "nothing"
    return {
        "draft": draft,
        "sources": sources,
        "missing": missing_fields(merged),
        "steps": [step("extract", f"regex found {found}", started)],
    }

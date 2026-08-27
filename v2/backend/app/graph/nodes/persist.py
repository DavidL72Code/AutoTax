"""Node 7 — write the record, or park it for review."""
from __future__ import annotations

import time

from ...store import repository
from ..state import ReceiptState, as_record, confidence
from ._util import step

REVIEW_THRESHOLD = 0.55


async def persist(state: ReceiptState) -> dict:
    started = time.perf_counter()
    score = confidence(state)
    blocking = {"amount_missing", "amount_not_positive", "vendor_missing"} & set(state.get("issues") or [])
    status = "needs_review" if blocking or score < REVIEW_THRESHOLD else "parsed"

    record = as_record({**state, "status": status})
    saved = await repository.save(state.get("user_id") or "local", record)
    return {
        "status": status,
        "saved_id": saved,
        "steps": [step("persist", f"saved as {status} (confidence {score})", started)],
    }

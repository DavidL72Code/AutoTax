"""Node 8 — write the record, and keep what was learned.

A correction is worth more than the row it fixes. When a field arrived from a
human, it is written to the cross-thread store so the next email from that
sender resolves without asking anyone. That is the difference between a review
queue that stays the same size and one that drains.
"""
from __future__ import annotations

import time

from langgraph.config import get_config

from ...store import repository
from .. import persistence
from ..state import BLOCKING, ReceiptState, as_record, confidence
from ._util import step

REVIEW_THRESHOLD = 0.55


def _thread_id() -> str:
    try:
        return str((get_config().get("configurable") or {}).get("thread_id") or "")
    except Exception:  # noqa: BLE001 - running outside a graph invocation
        return ""


async def _learn(state: ReceiptState) -> list[str]:
    """Persist anything a human decided. Returns what was learned, for the trace."""
    sources = state.get("sources") or {}
    draft = state.get("draft") or {}
    email = state.get("email") or {}
    user_id = state.get("user_id") or "local"
    learned = []

    if sources.get("vendor") == "human" and draft.get("vendor"):
        await persistence.remember_vendor(user_id, email.get("sender", ""), draft["vendor"])
        learned.append(f"{persistence.domain_key(email.get('sender', ''))} → {draft['vendor']}")

    if sources.get("category") == "human" and draft.get("vendor") and draft.get("category"):
        await persistence.remember_category(user_id, draft["vendor"], draft["category"])
        learned.append(f"{draft['vendor']} → {draft['category']}")

    return learned


async def persist(state: ReceiptState) -> dict:
    started = time.perf_counter()

    if state.get("status") == "discarded":
        record = {**as_record({**state, "status": "discarded"}), "thread_id": _thread_id()}
        saved = await repository.save(state.get("user_id") or "local", record)
        return {
            "status": "discarded",
            "saved_id": saved,
            "steps": [step("persist", "recorded as discarded so it is not parsed again", started,
                      key="trace.persist.discarded")],
        }

    score = confidence(state)
    blocking = BLOCKING & set(state.get("issues") or [])
    reviewed = bool(state.get("reviewed"))

    # A reviewed record is settled by definition — a person looked at the email.
    status = "parsed" if reviewed or (not blocking and score >= REVIEW_THRESHOLD) else "needs_review"

    learned = await _learn(state)
    record = {
        **as_record({**state, "status": status}),
        "thread_id": _thread_id(),
        "reviewed": reviewed,
    }
    saved = await repository.save(state.get("user_id") or "local", record)

    detail = f"saved as {status} (confidence {score:.2f})"
    if learned:
        detail += f" · learned {', '.join(learned)}"
    return {
        "status": status,
        "saved_id": saved,
        "steps": [step("persist", detail, started,
                       key="trace.persist.saved",
                       params={"status": status, "confidence": round(score, 2), "learned": learned})],
    }

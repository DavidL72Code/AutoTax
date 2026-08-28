"""Node 7 — stop and ask a person.

This is where the checkpointer earns its place. `interrupt()` raises out of the
node, LangGraph writes the thread's state to the checkpointer, and the run
ends. Hours later a `Command(resume=...)` re-enters this node on the same
thread with the human's answer, and execution continues into `validate` —
which re-checks the human's numbers exactly as it checked the model's — and on
to `persist`.

Two consequences worth being explicit about:

* The pause is durable. Nothing is held in a Python object waiting for a
  callback; the state lives in the checkpointer under the thread id.
* The answer re-enters the loop rather than bypassing it. A person who types a
  total that does not reconcile gets the same complaint the model would.
"""
from __future__ import annotations

import time

from langgraph.config import get_config
from langgraph.types import interrupt

from ...store import repository
from .. import patterns
from ..state import Draft, ReceiptState, as_record, confidence
from ._util import step


def _thread_id() -> str:
    try:
        return str((get_config().get("configurable") or {}).get("thread_id") or "")
    except Exception:  # noqa: BLE001 - running outside a graph invocation
        return ""

# Fields a reviewer is allowed to set. Anything else in the resume payload is
# ignored — the resume value arrives over HTTP and is not trusted.
EDITABLE = ("vendor", "amount", "tax", "date", "category", "payment_method")
NUMERIC = ("amount", "tax")


def _coerce(field: str, value):
    if value is None or value == "":
        return None
    if field in NUMERIC:
        return patterns.money(value)
    text = str(value).strip()
    return text[:120] or None


async def await_review(state: ReceiptState) -> dict:
    started = time.perf_counter()
    email = state.get("email") or {}

    # Write the provisional row before pausing, so the receipt is visible in
    # the queue while the thread sits in the checkpointer. Re-running this node
    # on resume rewrites the same document — the id is derived from the Gmail
    # message id, so it is an overwrite, never a duplicate.
    await repository.save(
        state.get("user_id") or "local",
        {**as_record({**state, "status": "needs_review"}), "thread_id": _thread_id()},
    )

    # Everything the reviewer needs to decide, and nothing they don't: the
    # email body itself is deliberately not included.
    answer = interrupt(
        {
            "reason": "needs_review",
            "email": {
                "id": email.get("id"),
                "sender": email.get("sender"),
                "subject": email.get("subject"),
                "date": email.get("date"),
            },
            "draft": state.get("draft") or {},
            "issues": state.get("issues") or [],
            "sources": state.get("sources") or {},
            "confidence": confidence(state),
            "steps": state.get("steps") or [],
            "editable": list(EDITABLE),
        }
    )

    answer = answer if isinstance(answer, dict) else {}
    action = str(answer.get("action") or "confirm").lower()

    if action == "discard":
        return {
            "status": "discarded",
            "reviewed": True,
            "resolution": {"action": "discard", "at": answer.get("at")},
            "steps": [step("await_review", "reviewer discarded this receipt", started, key="trace.review.discarded")],
        }

    draft: Draft = {}
    sources: dict[str, str] = {}
    for field in EDITABLE:
        if field not in answer:
            continue
        value = _coerce(field, answer[field])
        if value is not None:
            draft[field] = value  # type: ignore[literal-required]
            sources[field] = "human"

    changed = ", ".join(f"{k}={v}" for k, v in draft.items()) or "no changes"
    return {
        "draft": draft,
        "sources": sources,
        "reviewed": True,
        # Cleared so `validate` re-runs against the corrected values instead of
        # inheriting the complaint that caused the pause.
        "issues": [],
        "missing": [],
        "resolution": {"action": "confirm", "fields": list(draft.keys()), "at": answer.get("at")},
        "steps": [step("await_review", f"reviewer set {changed}", started,
                      key="trace.review.set", params={"fields": changed})],
    }


def review_payload(state: ReceiptState) -> dict:
    """The same shape the interrupt carries, for listing paused threads."""
    return {**as_record(state), "email": state.get("email") or {}}

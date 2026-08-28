"""Driving the graph: one thread per email, and resuming paused ones.

Concurrency here is what makes the batching in `llm.py` pay off — every email
that reaches `escalate` at roughly the same moment folds into one request.

Thread ids are `{user_id}:{email_id}`, which means re-running a message
*resumes* its thread rather than starting a parallel history of it. That is
also what a review resume addresses.
"""
from __future__ import annotations

import asyncio
from typing import Any, Awaitable, Callable, Iterable, Optional

from langgraph.types import Command

from .graph import receipt_graph
from .state import Email, ReceiptState, as_record, new_state

ProgressFn = Callable[[dict[str, Any]], Awaitable[None] | None]


def thread_id(user_id: str, email_id: str) -> str:
    return f"{user_id}:{email_id}"


def _config(user_id: str, email_id: str) -> dict[str, Any]:
    return {"configurable": {"thread_id": thread_id(user_id, email_id), "user_id": str(user_id)}}


def _interrupt_payload(result: dict[str, Any]) -> Optional[dict[str, Any]]:
    """LangGraph reports a dynamic interrupt on the returned state rather than
    raising, so a paused thread looks like a normal (unfinished) result."""
    raised = result.get("__interrupt__")
    if not raised:
        return None
    first = raised[0] if isinstance(raised, (list, tuple)) else raised
    return getattr(first, "value", None) or {}


def _record_from(result: dict[str, Any], user_id: str, email_id: str) -> dict[str, Any]:
    paused = _interrupt_payload(result)
    record = as_record(result if not paused else {**result, "status": "needs_review"})
    record["thread_id"] = thread_id(user_id, email_id)
    if paused:
        record["awaiting_review"] = True
    return record


NodeFn = Callable[[str, str], None]


async def run_one(
    email: Email,
    user_id: str = "local",
    *,
    interactive: bool = True,
    on_node: Optional[NodeFn] = None,
) -> dict[str, Any]:
    graph = receipt_graph(interactive=interactive)
    email_id = str(email.get("id") or "")
    config = _config(user_id, email_id)
    state = new_state(email, user_id)

    if on_node is None:
        result: ReceiptState = await graph.ainvoke(state, config=config)
        return _record_from(result, user_id, email_id)

    # Two stream modes at once: `updates` names the node that just finished,
    # `values` carries the state after it. `ainvoke` gives only the second, and
    # a caller that wants to show where the work is needs the first.
    result = {}
    async for mode, chunk in graph.astream(state, config=config, stream_mode=["updates", "values"]):
        if mode == "updates":
            for node in chunk or {}:
                # `__interrupt__` and friends are control signals, not nodes.
                if not str(node).startswith("__"):
                    on_node(str(node), email_id)
        elif isinstance(chunk, dict):
            result = chunk
    return _record_from(result, user_id, email_id)


async def resume_review(user_id: str, email_id: str, answer: dict[str, Any]) -> Optional[dict[str, Any]]:
    """Hand a human's answer back to the thread that is waiting for it.

    Returns None when no paused thread exists — the checkpoint may have been
    lost to a restart if the in-process checkpointer is in use, in which case
    the caller falls back to editing the stored record directly.
    """
    graph = receipt_graph(interactive=True)
    config = _config(user_id, email_id)

    snapshot = await graph.aget_state(config)
    if not snapshot or not snapshot.next:
        return None

    result = await graph.ainvoke(Command(resume=answer), config=config)
    return _record_from(result, user_id, email_id)


async def paused_threads(user_id: str, email_ids: Iterable[str]) -> list[dict[str, Any]]:
    """Which of these threads are actually sitting in the checkpointer.

    Also returns just enough of the email to identify it — sender, subject — so
    a reviewer can open the original in Gmail. The body is deliberately not
    included: it can carry anything the merchant put in it, and this app has no
    reason to hold or display that.
    """
    graph = receipt_graph(interactive=True)
    live = []
    for email_id in email_ids:
        snapshot = await graph.aget_state(_config(user_id, email_id))
        if snapshot and snapshot.next:
            email = (snapshot.values or {}).get("email") or {}
            live.append({
                "email_id": email_id,
                "next": list(snapshot.next),
                "source": {
                    "sender": email.get("sender"),
                    "subject": email.get("subject"),
                },
            })
    return live


async def run_many(
    emails: Iterable[Email],
    user_id: str = "local",
    *,
    concurrency: int = 16,
    interactive: bool = True,
    on_result: Optional[ProgressFn] = None,
    on_node: Optional[NodeFn] = None,
) -> list[dict[str, Any]]:
    emails = list(emails)
    gate = asyncio.Semaphore(concurrency)
    results: list[Optional[dict[str, Any]]] = [None] * len(emails)

    async def worker(index: int, email: Email) -> None:
        async with gate:
            try:
                record = await run_one(email, user_id, interactive=interactive, on_node=on_node)
            except Exception as exc:  # noqa: BLE001 - one bad email must not sink the sync
                record = {
                    "email_id": email.get("id"),
                    "status": "failed",
                    "issues": [f"pipeline_error: {type(exc).__name__}: {exc}"],
                    "confidence": 0.0,
                    "steps": [],
                }
            results[index] = record
            if on_result is not None:
                outcome = on_result({"index": index, "total": len(emails), "record": record})
                if asyncio.iscoroutine(outcome):
                    await outcome

    await asyncio.gather(*(worker(i, e) for i, e in enumerate(emails)))
    return [r for r in results if r is not None]

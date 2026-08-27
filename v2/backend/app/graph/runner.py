"""Runs many emails through the graph at once.

Concurrency here is what makes the batching in `llm.py` pay off: every email
that reaches `escalate` at roughly the same moment gets folded into one
request. Sequential runs would still be correct, just slower and pricier.
"""
from __future__ import annotations

import asyncio
from typing import Any, Awaitable, Callable, Iterable, Optional

from .graph import receipt_graph
from .state import Email, ReceiptState, as_record, new_state

ProgressFn = Callable[[dict[str, Any]], Awaitable[None] | None]


async def run_one(email: Email, user_id: str = "local") -> dict[str, Any]:
    state: ReceiptState = await receipt_graph().ainvoke(new_state(email, user_id))
    return as_record(state)


async def run_many(
    emails: Iterable[Email],
    user_id: str = "local",
    *,
    concurrency: int = 16,
    on_result: Optional[ProgressFn] = None,
) -> list[dict[str, Any]]:
    emails = list(emails)
    gate = asyncio.Semaphore(concurrency)
    results: list[Optional[dict[str, Any]]] = [None] * len(emails)

    async def worker(index: int, email: Email) -> None:
        async with gate:
            try:
                record = await run_one(email, user_id)
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

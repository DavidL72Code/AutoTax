"""Sync runs: fetch, feed the graph, stream progress.

A run is deliberately observable. Every state change is pushed to subscribers
as it happens, so the UI can show the pipeline working on real emails instead
of a spinner and a guess.
"""
from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timezone
from typing import Any, AsyncIterator, Optional

from . import auth
from .graph.runner import run_many
from .ingest import gmail
from .store import repository


class Run:
    def __init__(self, run_id: str, user_id: str, user_ids: Optional[list[str]] = None) -> None:
        self.id = run_id
        self.user_id = user_id
        # Writes go to the v2 id; the skip-list spans any linked v1 ids too, so
        # a message v1 already parsed is not fetched or re-parsed.
        self.user_ids = user_ids or [user_id]
        self.status = "starting"
        self.started_at = datetime.now(timezone.utc).isoformat()
        self.total = 0
        self.done = 0
        self.saved = 0
        self.review = 0
        self.skipped = 0
        self.error: Optional[str] = None
        self.records: list[dict] = []
        self._subscribers: list[asyncio.Queue] = []
        self._cancelled = False

    def snapshot(self) -> dict[str, Any]:
        return {
            "run_id": self.id,
            "status": self.status,
            "total": self.total,
            "done": self.done,
            "saved": self.saved,
            "review": self.review,
            "skipped": self.skipped,
            "error": self.error,
            "started_at": self.started_at,
        }

    def subscribe(self) -> asyncio.Queue:
        queue: asyncio.Queue = asyncio.Queue()
        queue.put_nowait({"type": "state", **self.snapshot()})
        self._subscribers.append(queue)
        return queue

    def unsubscribe(self, queue: asyncio.Queue) -> None:
        if queue in self._subscribers:
            self._subscribers.remove(queue)

    def emit(self, event: dict[str, Any]) -> None:
        for queue in list(self._subscribers):
            queue.put_nowait(event)

    def cancel(self) -> None:
        self._cancelled = True

    @property
    def cancelled(self) -> bool:
        return self._cancelled


_runs: dict[str, Run] = {}


def get_run(run_id: str) -> Optional[Run]:
    return _runs.get(run_id)


def start(user_id: str, user_ids: Optional[list[str]] = None, **options) -> Run:
    run = Run(uuid.uuid4().hex[:12], user_id, user_ids)
    _runs[run.id] = run
    asyncio.create_task(_execute(run, **options))
    return run


async def _execute(
    run: Run,
    *,
    max_results: int = 50,
    days_back: int = 180,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    emails: Optional[list[dict]] = None,
) -> None:
    try:
        if emails is None:
            refresh_token = await auth.refresh_token_for(run.user_id)
            if not refresh_token:
                raise RuntimeError("Gmail is not connected for this account")
            run.status = "fetching"
            run.emit({"type": "state", **run.snapshot()})
            known = await repository.existing_email_ids(run.user_ids)
            emails = await gmail.fetch_receipts(
                refresh_token,
                max_results=max_results,
                days_back=days_back,
                date_from=date_from,
                date_to=date_to,
                skip_ids=known,
            )

        run.total = len(emails)
        run.status = "parsing"
        run.emit({"type": "state", **run.snapshot()})

        if not emails:
            run.status = "done"
            run.emit({"type": "state", **run.snapshot()})
            run.emit({"type": "done", **run.snapshot()})
            return

        def on_result(update: dict) -> None:
            if run.cancelled:
                return
            record = update["record"]
            run.done += 1
            status = record.get("status")
            run.saved += int(status == "parsed")
            run.review += int(status == "needs_review")
            run.skipped += int(status == "skipped")
            run.records.append(record)
            run.emit({"type": "record", "record": record, **run.snapshot()})

        run.records = await run_many(emails, run.user_id, on_result=on_result)
        run.status = "cancelled" if run.cancelled else "done"
    except Exception as exc:  # noqa: BLE001 - surface the failure to the client
        run.status = "failed"
        run.error = f"{type(exc).__name__}: {exc}"
    finally:
        run.emit({"type": "state", **run.snapshot()})
        run.emit({"type": "done", **run.snapshot()})


async def stream(run: Run) -> AsyncIterator[dict]:
    queue = run.subscribe()
    try:
        while True:
            event = await queue.get()
            yield event
            if event.get("type") == "done":
                return
    finally:
        run.unsubscribe(queue)

"""Shared eval plumbing: an in-memory store, prompt capture, timing."""
from __future__ import annotations

import asyncio
import pathlib
import statistics
import sys
import time
from typing import Any

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

from app import llm  # noqa: E402
from app.store import repository  # noqa: E402


class MemoryStore:
    def __init__(self) -> None:
        self.rows: list[dict] = []

    async def save(self, user_id, record):
        self.rows.append({"user_id": user_id, **record})
        return str(len(self.rows))

    async def list(self, user_id):
        return self.rows

    async def existing_email_ids(self, user_id):
        return set()

    async def update(self, user_id, record_id, patch):
        return None

    async def delete(self, user_id, record_id):
        return False


def use_memory_store() -> MemoryStore:
    store = MemoryStore()
    repository.use(store)
    return store


class PromptRecorder:
    """Wraps llm._invoke so evals can inspect exactly what left the process."""

    def __init__(self) -> None:
        self.prompts: list[str] = []
        self._original = None

    def __enter__(self) -> "PromptRecorder":
        self._original = llm._invoke

        async def capture(prompt: str, max_tokens: int) -> str:
            self.prompts.append(prompt)
            return await self._original(prompt, max_tokens)

        llm._invoke = capture  # type: ignore[assignment]
        return self

    def __exit__(self, *exc: Any) -> None:
        if self._original is not None:
            llm._invoke = self._original  # type: ignore[assignment]


def percentile(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(int(round(pct / 100 * (len(ordered) - 1))), len(ordered) - 1)
    return round(ordered[index], 1)


def node_latencies(records: list[dict]) -> dict[str, dict[str, float]]:
    per_node: dict[str, list[float]] = {}
    for record in records:
        for step in record.get("steps", []):
            per_node.setdefault(step["node"], []).append(float(step["ms"]))
    return {
        node: {
            "calls": len(values),
            "p50": percentile(values, 50),
            "p95": percentile(values, 95),
            "max": round(max(values), 1),
            "total": round(sum(values), 1),
        }
        for node, values in sorted(per_node.items(), key=lambda kv: -sum(kv[1]))
    }


async def timed_run(emails: list[dict], user_id: str = "eval") -> tuple[list[dict], float, int]:
    from app.graph.runner import run_many

    llm.reset_calls()
    started = time.perf_counter()
    records = await run_many(emails, user_id, interactive=False)
    return records, time.perf_counter() - started, llm.calls_made()


def mean(values: list[float]) -> float:
    return round(statistics.mean(values), 1) if values else 0.0

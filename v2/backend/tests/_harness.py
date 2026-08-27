"""Shared test/eval plumbing: import path, in-memory store, fixture loading."""
from __future__ import annotations

import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from app.store import repository  # noqa: E402

DEMO_EMAILS = pathlib.Path(__file__).resolve().parents[3] / "python-service/app/reports/demo_emails.json"


class MemoryStore:
    def __init__(self) -> None:
        self.rows: list[dict] = []

    async def save(self, user_id, record):
        self.rows.append(record)
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


def load_demo_emails() -> list[dict]:
    raw = json.loads(DEMO_EMAILS.read_text())
    return [{"id": e["id"], "sender": e["from"], "subject": e["subject"], "date": e["date"], "body": e["body"]} for e in raw]

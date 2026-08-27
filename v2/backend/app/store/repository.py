"""Persistence with two interchangeable backends.

JSON-on-disk is the default so the graph runs with zero external setup.
Firestore takes over automatically when Firebase credentials are configured,
matching where v1 already keeps its data.
"""
from __future__ import annotations

import asyncio
import json
import uuid
from pathlib import Path
from typing import Any, Optional, Protocol

from ..config import settings
from . import firestore_client

DATA_DIR = Path(__file__).resolve().parents[2] / "data"


DEMO_PREFIX = "demo_"

UserIds = str | list[str]


def _as_list(user_id: UserIds) -> list[str]:
    return [user_id] if isinstance(user_id, str) else list(user_id)


def _normalise(record: dict[str, Any]) -> dict[str, Any]:
    """Fill in the fields v1 never wrote, so a v1 row renders in v2."""
    record.setdefault("status", "parsed")
    record.setdefault("confidence", 0.7 if record.get("vendor") and record.get("amount") else 0.3)
    record.setdefault("issues", [])
    record.setdefault("sources", {})
    record.setdefault("steps", [])
    record.setdefault("llm_calls", 0)
    record.setdefault("currency", "USD")
    record.setdefault("origin", "v1" if not record.get("steps") else "v2")
    return record


class Backend(Protocol):
    async def save(self, user_id: str, record: dict[str, Any]) -> Optional[str]: ...
    async def list(self, user_id: UserIds) -> list[dict[str, Any]]: ...
    async def existing_email_ids(self, user_id: UserIds) -> set[str]: ...
    async def update(self, user_id: str, record_id: str, patch: dict[str, Any]) -> Optional[dict]: ...
    async def delete(self, user_id: str, record_id: str) -> bool: ...


class JsonBackend:
    """Single file, whole-file rewrite, guarded by one lock. Fine for a
    personal inbox; swap to Firestore when more than one process writes."""

    def __init__(self, path: Path | None = None) -> None:
        self.path = path or (DATA_DIR / "transactions.json")
        self._lock = asyncio.Lock()

    def _read(self) -> dict[str, list[dict]]:
        if not self.path.exists():
            return {}
        try:
            return json.loads(self.path.read_text() or "{}")
        except json.JSONDecodeError:
            return {}

    def _write(self, data: dict[str, list[dict]]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, indent=2, default=str))
        tmp.replace(self.path)

    async def save(self, user_id: str, record: dict[str, Any]) -> Optional[str]:
        async with self._lock:
            data = self._read()
            rows = data.setdefault(user_id, [])
            email_id = record.get("email_id")
            for existing in rows:
                if email_id and existing.get("email_id") == email_id:
                    existing.update(record)
                    self._write(data)
                    return existing["id"]
            record_id = uuid.uuid4().hex
            rows.append({"id": record_id, **record})
            self._write(data)
            return record_id

    async def list(self, user_id: UserIds) -> list[dict[str, Any]]:
        data = self._read()
        rows = [_normalise(dict(row)) for key in _as_list(user_id) for row in data.get(key, [])]
        return sorted(rows, key=lambda r: (r.get("date") or ""), reverse=True)

    async def existing_email_ids(self, user_id: UserIds) -> set[str]:
        return {r.get("email_id") for r in await self.list(user_id) if r.get("email_id")}

    async def update(self, user_id: str, record_id: str, patch: dict[str, Any]) -> Optional[dict]:
        async with self._lock:
            data = self._read()
            for row in data.get(user_id, []):
                if row.get("id") == record_id:
                    row.update({k: v for k, v in patch.items() if k != "id"})
                    self._write(data)
                    return row
            return None

    async def delete(self, user_id: str, record_id: str) -> bool:
        async with self._lock:
            data = self._read()
            rows = data.get(user_id, [])
            remaining = [r for r in rows if r.get("id") != record_id]
            if len(remaining) == len(rows):
                return False
            data[user_id] = remaining
            self._write(data)
            return True


class FirestoreBackend:
    """Shares v1's `transactions` collection.

    v2 writes extra fields (status, confidence, issues, sources, steps); v1
    ignores unknown keys when it reads, so both versions can run against the
    same data. Document ids are `{user_id}__{email_id}`, which makes a re-sync
    of the same Gmail message an idempotent overwrite rather than a duplicate.
    """

    def __init__(self) -> None:
        self._db = firestore_client.client()
        self._collection = settings.firebase_transactions_collection

    def _col(self, user_id: str = ""):
        # Sample-inbox runs are throwaway. They must never land in the same
        # collection as someone's real ledger.
        if str(user_id).startswith(DEMO_PREFIX):
            return self._db.collection(settings.firebase_demo_collection)
        return self._db.collection(self._collection)

    async def save(self, user_id: str, record: dict[str, Any]) -> Optional[str]:
        email_id = record.get("email_id") or uuid.uuid4().hex
        doc_id = f"{user_id}__{email_id}"
        payload = {**record, "user_id": user_id, "email_id": email_id, "updated_at": _now()}
        await asyncio.to_thread(self._col(user_id).document(doc_id).set, payload, merge=True)
        return doc_id

    def _query_rows(self, user_ids: list[str]) -> list[dict[str, Any]]:
        from google.cloud.firestore_v1.base_query import FieldFilter

        rows: list[dict[str, Any]] = []
        # Firestore caps `in` at 30 values; batch rather than assume.
        for index in range(0, len(user_ids), 30):
            chunk = user_ids[index : index + 30]
            query = self._col(chunk[0]).where(filter=FieldFilter("user_id", "in", chunk))
            rows.extend({"id": doc.id, **(doc.to_dict() or {})} for doc in query.stream())
        return rows

    async def list(self, user_id: UserIds) -> list[dict[str, Any]]:
        user_ids = _as_list(user_id)
        rows = await asyncio.to_thread(self._query_rows, user_ids)
        return sorted(
            (_normalise(row) for row in rows),
            key=lambda r: str(r.get("date") or ""),
            reverse=True,
        )

    async def existing_email_ids(self, user_id: UserIds) -> set[str]:
        return {r.get("email_id") for r in await self.list(user_id) if r.get("email_id")}

    async def update(self, user_id: str, record_id: str, patch: dict[str, Any]) -> Optional[dict]:
        ref = self._col(user_id).document(record_id)
        snapshot = await asyncio.to_thread(ref.get)
        if not snapshot.exists:
            return None
        await asyncio.to_thread(
            ref.set, {k: v for k, v in patch.items() if k != "id"} | {"updated_at": _now()}, merge=True
        )
        refreshed = await asyncio.to_thread(ref.get)
        return _normalise({"id": record_id, **(refreshed.to_dict() or {})})

    async def delete(self, user_id: str, record_id: str) -> bool:
        ref = self._col(user_id).document(record_id)
        snapshot = await asyncio.to_thread(ref.get)
        if not snapshot.exists:
            return False
        await asyncio.to_thread(ref.delete)
        return True


def _build() -> Backend:
    if firestore_client.configured():
        try:
            return FirestoreBackend()
        except Exception as exc:  # noqa: BLE001 - never let storage setup kill boot
            print(f"[store] Firestore unavailable ({exc}); falling back to JSON store")
    return JsonBackend()


def describe() -> str:
    return "firestore" if isinstance(backend(), FirestoreBackend) else "json"


def _now() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat()


_backend: Optional[Backend] = None


def backend() -> Backend:
    global _backend
    if _backend is None:
        _backend = _build()
    return _backend


def use(custom: Backend) -> None:
    """Point the repository at a different backend (tests, demo mode)."""
    global _backend
    _backend = custom


async def save(user_id: str, record: dict[str, Any]) -> Optional[str]:
    return await backend().save(user_id, record)


async def list_records(user_id: UserIds) -> list[dict[str, Any]]:
    return await backend().list(user_id)


async def existing_email_ids(user_id: UserIds) -> set[str]:
    return await backend().existing_email_ids(user_id)


async def update(user_id: str, record_id: str, patch: dict[str, Any]) -> Optional[dict]:
    return await backend().update(user_id, record_id, patch)


async def delete(user_id: str, record_id: str) -> bool:
    return await backend().delete(user_id, record_id)

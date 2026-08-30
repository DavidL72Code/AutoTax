"""Persistence with two interchangeable backends.

JSON-on-disk is the default so the graph runs with zero external setup.
Firestore takes over automatically when Firebase credentials are configured,
matching where v1 already keeps its data.
"""
from __future__ import annotations

import asyncio
import json
import uuid
from collections import OrderedDict
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


class EphemeralBackend:
    """Demo sessions, held in the process and never written anywhere.

    A sample-inbox visitor is not a customer with data to keep. They are
    someone trying the thing for ten minutes. Persisting ~99 receipts per visit
    to Firestore left 1,579 orphaned documents across 22 throwaway users with
    nothing to clean them up, for data nobody would ever read again.

    Same semantics as the real backends, including that a caller may only touch
    their own rows: isolation here is the dict key, so it holds by construction.
    """

    def __init__(self, max_users: int = 50) -> None:
        self._rows: OrderedDict[str, list[dict[str, Any]]] = OrderedDict()
        self._max_users = max_users
        self._lock = asyncio.Lock()

    def _touch(self, user_id: str) -> list[dict[str, Any]]:
        rows = self._rows.setdefault(user_id, [])
        self._rows.move_to_end(user_id)
        # Nothing expires a demo session, so without a cap a long-lived process
        # accumulates every visitor who ever passed through.
        while len(self._rows) > self._max_users:
            self._rows.popitem(last=False)
        return rows

    async def save(self, user_id: str, record: dict[str, Any]) -> Optional[str]:
        async with self._lock:
            rows = self._touch(user_id)
            email_id = record.get("email_id") or uuid.uuid4().hex
            record_id = f"{user_id}__{email_id}"
            payload = {**record, "id": record_id, "user_id": user_id, "email_id": email_id, "updated_at": _now()}
            for index, row in enumerate(rows):
                if row.get("email_id") == email_id:
                    rows[index] = payload
                    return record_id
            rows.append(payload)
            return record_id

    async def list(self, user_id: UserIds) -> list[dict[str, Any]]:
        wanted = _as_list(user_id)
        rows = [_normalise(dict(row)) for key in wanted for row in self._rows.get(key, [])]
        return sorted(rows, key=lambda r: str(r.get("date") or ""), reverse=True)

    async def existing_email_ids(self, user_id: UserIds) -> set[str]:
        return {r.get("email_id") for r in await self.list(user_id) if r.get("email_id")}

    async def update(self, user_id: str, record_id: str, patch: dict[str, Any]) -> Optional[dict]:
        async with self._lock:
            for row in self._rows.get(user_id, []):
                if row.get("id") == record_id:
                    row.update({k: v for k, v in patch.items() if k != "id"}, updated_at=_now())
                    return _normalise(dict(row))
        return None

    async def delete(self, user_id: str, record_id: str) -> bool:
        async with self._lock:
            rows = self._rows.get(user_id, [])
            remaining = [r for r in rows if r.get("id") != record_id]
            if len(remaining) == len(rows):
                return False
            self._rows[user_id] = remaining
            return True

    def forget(self, user_id: str) -> int:
        return len(self._rows.pop(user_id, []))


def _owned_by(snapshot: Any, user_id: str) -> bool:
    """Reads are filtered by `user_id`, but writes address a document directly
    and the id is supplied by the caller. Ids are `{user_id}__{email_id}`, so
    without this a caller could name someone else's row and edit or delete it.
    Existence is not permission."""
    if not snapshot.exists:
        return False
    return str((snapshot.to_dict() or {}).get("user_id") or "") == str(user_id)


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
        if not _owned_by(snapshot, user_id):
            return None
        await asyncio.to_thread(
            ref.set, {k: v for k, v in patch.items() if k != "id"} | {"updated_at": _now()}, merge=True
        )
        refreshed = await asyncio.to_thread(ref.get)
        return _normalise({"id": record_id, **(refreshed.to_dict() or {})})

    async def delete(self, user_id: str, record_id: str) -> bool:
        ref = self._col(user_id).document(record_id)
        snapshot = await asyncio.to_thread(ref.get)
        if not _owned_by(snapshot, user_id):
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


def describe(user_id: str = "") -> str:
    if user_id and str(user_id).startswith(DEMO_PREFIX):
        return "in-memory (demo)"
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


_ephemeral = EphemeralBackend()


def _for(user_id: UserIds) -> Backend:
    """Demo sessions never reach durable storage. Routing here rather than
    inside a backend keeps it true whichever backend is configured, and means a
    visitor trying the sample inbox writes nothing at all."""
    if any(str(uid).startswith(DEMO_PREFIX) for uid in _as_list(user_id)):
        return _ephemeral
    return backend()


def forget_demo(user_id: str) -> int:
    """Drop a demo session's rows the moment it is abandoned."""
    return _ephemeral.forget(user_id)


def use(custom: Backend) -> None:
    """Point the repository at a different backend (tests, demo mode)."""
    global _backend
    _backend = custom


async def save(user_id: str, record: dict[str, Any]) -> Optional[str]:
    return await _for(user_id).save(user_id, record)


async def list_records(user_id: UserIds) -> list[dict[str, Any]]:
    return await _for(user_id).list(user_id)


async def existing_email_ids(user_id: UserIds) -> set[str]:
    return await _for(user_id).existing_email_ids(user_id)


async def update(user_id: str, record_id: str, patch: dict[str, Any]) -> Optional[dict]:
    return await _for(user_id).update(user_id, record_id, patch)


async def delete(user_id: str, record_id: str) -> bool:
    return await _for(user_id).delete(user_id, record_id)

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

DATA_DIR = Path(__file__).resolve().parents[2] / "data"


class Backend(Protocol):
    async def save(self, user_id: str, record: dict[str, Any]) -> Optional[str]: ...
    async def list(self, user_id: str) -> list[dict[str, Any]]: ...
    async def existing_email_ids(self, user_id: str) -> set[str]: ...
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

    async def list(self, user_id: str) -> list[dict[str, Any]]:
        rows = self._read().get(user_id, [])
        return sorted(rows, key=lambda r: (r.get("date") or ""), reverse=True)

    async def existing_email_ids(self, user_id: str) -> set[str]:
        return {r.get("email_id") for r in self._read().get(user_id, []) if r.get("email_id")}

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
    """Mirrors v1's collection layout so both versions can read the same data."""

    def __init__(self) -> None:
        import firebase_admin
        from firebase_admin import credentials, firestore

        if not firebase_admin._apps:
            if settings.firebase_service_account_json:
                cred = credentials.Certificate(json.loads(settings.firebase_service_account_json))
            elif settings.firebase_service_account_path:
                cred = credentials.Certificate(settings.firebase_service_account_path)
            else:
                cred = credentials.ApplicationDefault()
            firebase_admin.initialize_app(cred, {"projectId": settings.firebase_project_id})
        self._db = firestore.client()
        self._collection = settings.firebase_transactions_collection

    def _col(self):
        return self._db.collection(self._collection)

    def _doc_id(self, user_id: str, email_id: str) -> str:
        return f"{user_id}__{email_id}"

    async def save(self, user_id: str, record: dict[str, Any]) -> Optional[str]:
        email_id = record.get("email_id") or uuid.uuid4().hex
        doc_id = self._doc_id(user_id, email_id)
        payload = {**record, "user_id": user_id, "email_id": email_id}
        await asyncio.to_thread(self._col().document(doc_id).set, payload, merge=True)
        return doc_id

    async def list(self, user_id: str) -> list[dict[str, Any]]:
        docs = await asyncio.to_thread(lambda: list(self._col().where("user_id", "==", user_id).stream()))
        rows = [{"id": d.id, **d.to_dict()} for d in docs]
        return sorted(rows, key=lambda r: (r.get("date") or ""), reverse=True)

    async def existing_email_ids(self, user_id: str) -> set[str]:
        rows = await self.list(user_id)
        return {r.get("email_id") for r in rows if r.get("email_id")}

    async def update(self, user_id: str, record_id: str, patch: dict[str, Any]) -> Optional[dict]:
        ref = self._col().document(record_id)
        snapshot = await asyncio.to_thread(ref.get)
        if not snapshot.exists or (snapshot.to_dict() or {}).get("user_id") != user_id:
            return None
        await asyncio.to_thread(ref.set, {k: v for k, v in patch.items() if k != "id"}, merge=True)
        refreshed = await asyncio.to_thread(ref.get)
        return {"id": record_id, **(refreshed.to_dict() or {})}

    async def delete(self, user_id: str, record_id: str) -> bool:
        ref = self._col().document(record_id)
        snapshot = await asyncio.to_thread(ref.get)
        if not snapshot.exists or (snapshot.to_dict() or {}).get("user_id") != user_id:
            return False
        await asyncio.to_thread(ref.delete)
        return True


def _build() -> Backend:
    if settings.firebase_project_id and (
        settings.firebase_service_account_json or settings.firebase_service_account_path
    ):
        try:
            return FirestoreBackend()
        except Exception as exc:  # noqa: BLE001 - never let storage setup kill boot
            print(f"[store] Firestore unavailable ({exc}); falling back to JSON store")
    return JsonBackend()


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


async def list_records(user_id: str) -> list[dict[str, Any]]:
    return await backend().list(user_id)


async def existing_email_ids(user_id: str) -> set[str]:
    return await backend().existing_email_ids(user_id)


async def update(user_id: str, record_id: str, patch: dict[str, Any]) -> Optional[dict]:
    return await backend().update(user_id, record_id, patch)


async def delete(user_id: str, record_id: str) -> bool:
    return await backend().delete(user_id, record_id)

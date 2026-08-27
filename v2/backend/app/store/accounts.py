"""Account and session storage.

Two backends, same interface as the transaction repository: JSON on disk for
zero-setup local runs, Firestore when credentials resolve. v2 keeps accounts
and sessions in its own collections rather than reusing v1's `users` and
`google_credentials` — a shared session table between two auth models is a
foot-gun — but it does link to v1's user ids so an existing ledger stays
visible.
"""
from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional, Protocol

from ..config import settings
from . import firestore_client
from .repository import DATA_DIR

ACCOUNTS_COLLECTION = "receipts_v2_accounts"
SESSIONS_COLLECTION = "receipts_v2_sessions"


class AccountStore(Protocol):
    async def put_account(self, user_id: str, account: dict[str, Any]) -> None: ...
    async def get_account(self, user_id: str) -> Optional[dict[str, Any]]: ...
    async def put_session(self, token: str, session: dict[str, Any]) -> None: ...
    async def get_session(self, token: str) -> Optional[dict[str, Any]]: ...
    async def drop_session(self, token: str) -> None: ...


class JsonAccountStore:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path or (DATA_DIR / "accounts.json")
        self._lock = asyncio.Lock()

    def _read(self) -> dict:
        if not self.path.exists():
            return {"users": {}, "sessions": {}}
        try:
            data = json.loads(self.path.read_text() or "{}")
        except json.JSONDecodeError:
            return {"users": {}, "sessions": {}}
        data.setdefault("users", {})
        data.setdefault("sessions", {})
        return data

    def _write(self, data: dict) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, indent=2))
        tmp.chmod(0o600)
        tmp.replace(self.path)

    async def put_account(self, user_id: str, account: dict[str, Any]) -> None:
        async with self._lock:
            data = self._read()
            data["users"][user_id] = account
            self._write(data)

    async def get_account(self, user_id: str) -> Optional[dict[str, Any]]:
        return self._read()["users"].get(user_id)

    async def put_session(self, token: str, session: dict[str, Any]) -> None:
        async with self._lock:
            data = self._read()
            data["sessions"][token] = session
            self._write(data)

    async def get_session(self, token: str) -> Optional[dict[str, Any]]:
        return self._read()["sessions"].get(token)

    async def drop_session(self, token: str) -> None:
        async with self._lock:
            data = self._read()
            if data["sessions"].pop(token, None) is not None:
                self._write(data)


class FirestoreAccountStore:
    def __init__(self) -> None:
        self._db = firestore_client.client()

    async def put_account(self, user_id: str, account: dict[str, Any]) -> None:
        await asyncio.to_thread(
            self._db.collection(ACCOUNTS_COLLECTION).document(user_id).set, account, merge=True
        )

    async def get_account(self, user_id: str) -> Optional[dict[str, Any]]:
        snapshot = await asyncio.to_thread(self._db.collection(ACCOUNTS_COLLECTION).document(user_id).get)
        return snapshot.to_dict() if snapshot.exists else None

    async def put_session(self, token: str, session: dict[str, Any]) -> None:
        await asyncio.to_thread(self._db.collection(SESSIONS_COLLECTION).document(token).set, session)

    async def get_session(self, token: str) -> Optional[dict[str, Any]]:
        snapshot = await asyncio.to_thread(self._db.collection(SESSIONS_COLLECTION).document(token).get)
        return snapshot.to_dict() if snapshot.exists else None

    async def drop_session(self, token: str) -> None:
        await asyncio.to_thread(self._db.collection(SESSIONS_COLLECTION).document(token).delete)


async def legacy_user_ids(email: str) -> list[str]:
    """v1 user-document ids for this email address.

    v1 keyed transactions by its own user id. Carrying those ids forward is
    what makes an existing ledger show up in v2 instead of looking empty.
    """
    if not (email and firestore_client.configured()):
        return []

    def _lookup() -> list[str]:
        db = firestore_client.client()
        found = []
        for field in ("email", "username"):
            for doc in db.collection("users").where(field, "==", email.strip().lower()).stream():
                if doc.id not in found:
                    found.append(doc.id)
        return found

    try:
        return await asyncio.to_thread(_lookup)
    except Exception:  # noqa: BLE001 - a missing legacy table is not an error
        return []


_store: Optional[AccountStore] = None


def store() -> AccountStore:
    global _store
    if _store is None:
        _store = FirestoreAccountStore() if firestore_client.configured() else JsonAccountStore()
    return _store


def use(custom: AccountStore) -> None:
    global _store
    _store = custom


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()

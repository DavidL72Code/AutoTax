"""Sessions and Google credentials.

v2 has one identity: the Gmail account you connect. There is no separate
username/password to forget, and no second copy of your inbox behind a
password we'd have to store. The refresh token is encrypted at rest with the
same Fernet key v1 uses.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import secrets
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

from cryptography.fernet import Fernet, InvalidToken

from .config import settings
from .store.repository import DATA_DIR

SESSION_COOKIE = "receipts_session"
SESSION_TTL = timedelta(days=30)
_ACCOUNTS = DATA_DIR / "accounts.json"
_lock = asyncio.Lock()


class AuthError(RuntimeError):
    pass


def _fernet() -> Fernet:
    key = (settings.fernet_key or "").strip()
    if not key:
        raise AuthError("FERNET_KEY is not set — cannot store Google credentials safely")
    return Fernet(key.encode())


def encrypt(value: str) -> str:
    return _fernet().encrypt(value.encode()).decode()


def decrypt(value: str) -> str:
    try:
        return _fernet().decrypt(value.encode()).decode()
    except InvalidToken as exc:
        raise AuthError("stored Google credential could not be decrypted") from exc


def user_id_for(email: str) -> str:
    return hashlib.sha256((email or "").strip().lower().encode()).hexdigest()[:16]


def _read() -> dict:
    if not _ACCOUNTS.exists():
        return {"users": {}, "sessions": {}}
    try:
        data = json.loads(_ACCOUNTS.read_text() or "{}")
    except json.JSONDecodeError:
        return {"users": {}, "sessions": {}}
    data.setdefault("users", {})
    data.setdefault("sessions", {})
    return data


def _write(data: dict) -> None:
    _ACCOUNTS.parent.mkdir(parents=True, exist_ok=True)
    tmp = _ACCOUNTS.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2))
    tmp.chmod(0o600)
    tmp.replace(_ACCOUNTS)


async def link_google_account(email: str, refresh_token: str) -> str:
    """Store the credential and hand back a fresh session token."""
    user_id = user_id_for(email)
    token = secrets.token_urlsafe(32)
    async with _lock:
        data = _read()
        existing = data["users"].get(user_id, {})
        data["users"][user_id] = {
            "email": email,
            "refresh_token_enc": encrypt(refresh_token) if refresh_token else existing.get("refresh_token_enc"),
            "connected_at": existing.get("connected_at") or datetime.now(timezone.utc).isoformat(),
        }
        data["sessions"][token] = {
            "user_id": user_id,
            "expires_at": (datetime.now(timezone.utc) + SESSION_TTL).isoformat(),
        }
        _write(data)
    return token


async def resolve_session(token: Optional[str]) -> Optional[dict]:
    if not token:
        return None
    data = _read()
    session = data["sessions"].get(token)
    if not session:
        return None
    try:
        expires = datetime.fromisoformat(session["expires_at"])
    except (KeyError, ValueError):
        return None
    if expires < datetime.now(timezone.utc):
        await end_session(token)
        return None
    user = data["users"].get(session["user_id"])
    if not user:
        return None
    return {"user_id": session["user_id"], "email": user.get("email"), "connected_at": user.get("connected_at")}


async def end_session(token: Optional[str]) -> None:
    if not token:
        return
    async with _lock:
        data = _read()
        if data["sessions"].pop(token, None) is not None:
            _write(data)


async def refresh_token_for(user_id: str) -> Optional[str]:
    user = _read()["users"].get(user_id)
    encrypted = (user or {}).get("refresh_token_enc")
    return decrypt(encrypted) if encrypted else None


async def disconnect_google(user_id: str) -> None:
    async with _lock:
        data = _read()
        user = data["users"].get(user_id)
        if user:
            user.pop("refresh_token_enc", None)
            _write(data)

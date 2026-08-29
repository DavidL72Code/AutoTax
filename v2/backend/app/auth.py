"""Sessions and Google credentials.

v2 has one identity: the Gmail account you connect. There is no separate
username/password to forget, and no second copy of your inbox behind a
password we'd have to store. The refresh token is encrypted at rest with the
same Fernet key v1 uses, and is only ever decrypted to mint a Gmail client.
"""
from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional

from cryptography.fernet import Fernet, InvalidToken

from .config import settings
from .store import accounts

SESSION_COOKIE = "receipts_session"
SESSION_TTL = timedelta(days=30)


class AuthError(RuntimeError):
    pass


def _fernet() -> Fernet:
    key = (settings.fernet_key or "").strip()
    if not key:
        raise AuthError("FERNET_KEY is not set, cannot store Google credentials safely")
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


async def link_google_account(email: str, refresh_token: str, user_id: Optional[str] = None) -> str:
    """Store the credential and hand back a fresh session token."""
    user_id = user_id or user_id_for(email)
    store = accounts.store()
    existing = await store.get_account(user_id) or {}

    account = {
        "email": email,
        "connected_at": existing.get("connected_at") or accounts.now_iso(),
        "legacy_user_ids": existing.get("legacy_user_ids") or await accounts.legacy_user_ids(email),
    }
    if refresh_token:
        account["refresh_token_enc"] = encrypt(refresh_token)
    elif existing.get("refresh_token_enc"):
        account["refresh_token_enc"] = existing["refresh_token_enc"]

    await store.put_account(user_id, account)

    token = secrets.token_urlsafe(32)
    await store.put_session(
        token,
        {"user_id": user_id, "expires_at": (datetime.now(timezone.utc) + SESSION_TTL).isoformat()},
    )
    return token


async def resolve_session(token: Optional[str]) -> Optional[dict]:
    if not token:
        return None
    store = accounts.store()
    session = await store.get_session(token)
    if not session:
        return None
    try:
        expires = datetime.fromisoformat(session["expires_at"])
    except (KeyError, TypeError, ValueError):
        return None
    if expires < datetime.now(timezone.utc):
        await store.drop_session(token)
        return None

    account = await store.get_account(session["user_id"])
    if not account:
        return None
    return {
        "user_id": session["user_id"],
        # Reads span v2's id plus any v1 ids for the same address, so an
        # existing ledger is visible instead of looking empty.
        "user_ids": [session["user_id"], *(account.get("legacy_user_ids") or [])],
        "email": account.get("email"),
        "connected_at": account.get("connected_at"),
        "gmail_connected": bool(account.get("refresh_token_enc")),
    }


async def end_session(token: Optional[str]) -> None:
    if token:
        await accounts.store().drop_session(token)


async def refresh_token_for(user_id: str) -> Optional[str]:
    account = await accounts.store().get_account(user_id)
    encrypted = (account or {}).get("refresh_token_enc")
    return decrypt(encrypted) if encrypted else None


async def disconnect_google(user_id: str) -> None:
    store = accounts.store()
    account = await store.get_account(user_id)
    if account:
        account.pop("refresh_token_enc", None)
        await store.put_account(user_id, {**account, "refresh_token_enc": None})

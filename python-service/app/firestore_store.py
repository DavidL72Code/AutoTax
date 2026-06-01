from __future__ import annotations

import hashlib
import json
import os
import secrets
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from .config import settings

try:
    import firebase_admin
    from firebase_admin import credentials as firebase_credentials
    from firebase_admin import firestore as firebase_firestore
except Exception:
    firebase_admin = None
    firebase_credentials = None
    firebase_firestore = None

_FIREBASE_APP = None


@dataclass
class UserRecord:
    id: str
    username: str
    email: Optional[str] = None
    firebase_uid: Optional[str] = None
    password_hash: str = ""
    created_at: Optional[datetime] = None


@dataclass
class TransactionRecord:
    id: str
    user_id: str
    email_id: str
    vendor: str
    amount: float
    tax: Optional[float] = None
    date: Optional[datetime] = None
    category: Optional[str] = None
    payment_method: Optional[str] = None
    items: Optional[str] = None
    email_body: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


@dataclass
class VendorRecord:
    id: str
    name: str
    normalized_name: Optional[str] = None
    parser_type: Optional[str] = None
    created_at: Optional[datetime] = None


def firestore_enabled() -> bool:
    return bool(
        firebase_admin is not None
        and firebase_credentials is not None
        and firebase_firestore is not None
        and (
            settings.firebase_service_account_json
            or settings.firebase_service_account_path
            or os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
        )
    )


def get_firestore_app():
    global _FIREBASE_APP
    if _FIREBASE_APP is not None:
        return _FIREBASE_APP
    if not firestore_enabled():
        return None

    # Reuse an already-initialized default app (e.g. initialized by api.py)
    try:
        _FIREBASE_APP = firebase_admin.get_app()
        return _FIREBASE_APP
    except (ValueError, Exception):
        pass

    options = {}
    if settings.firebase_project_id:
        options["projectId"] = settings.firebase_project_id

    if settings.firebase_service_account_json:
        cred = firebase_credentials.Certificate(json.loads(settings.firebase_service_account_json))
    elif settings.firebase_service_account_path:
        cred = firebase_credentials.Certificate(settings.firebase_service_account_path)
    else:
        cred = firebase_credentials.ApplicationDefault()

    _FIREBASE_APP = firebase_admin.initialize_app(cred, options or None)
    return _FIREBASE_APP


def get_firestore_client():
    app = get_firestore_app()
    if app is None or firebase_firestore is None:
        return None
    return firebase_firestore.client(app=app)


def _users():
    return get_firestore_client().collection(settings.firebase_users_collection)


def _transactions():
    return get_firestore_client().collection(settings.firebase_transactions_collection)


def _vendors():
    return get_firestore_client().collection(settings.firebase_vendors_collection)


def _now() -> datetime:
    return datetime.utcnow()


def _clean_email(value: str | None) -> str:
    return (value or "").strip().lower()


def _clean_username(value: str | None) -> str:
    return (value or "").strip().lower()


def _user_from_doc(doc) -> UserRecord:
    data = doc.to_dict() or {}
    return UserRecord(
        id=doc.id,
        username=data.get("username") or "",
        email=data.get("email"),
        firebase_uid=data.get("firebase_uid"),
        password_hash=data.get("password_hash") or "",
        created_at=data.get("created_at"),
    )


def _transaction_from_doc(doc) -> TransactionRecord:
    data = doc.to_dict() or {}
    return TransactionRecord(
        id=doc.id,
        user_id=str(data.get("user_id") or ""),
        email_id=data.get("email_id") or "",
        vendor=data.get("vendor") or "Unknown",
        amount=float(data.get("amount") or 0.0),
        tax=float(data["tax"]) if data.get("tax") is not None else None,
        date=data.get("date"),
        category=data.get("category"),
        payment_method=data.get("payment_method"),
        items=data.get("items"),
        email_body=data.get("email_body"),
        created_at=data.get("created_at"),
        updated_at=data.get("updated_at"),
    )


def _vendor_from_doc(doc) -> VendorRecord:
    data = doc.to_dict() or {}
    return VendorRecord(
        id=doc.id,
        name=data.get("name") or "",
        normalized_name=data.get("normalized_name"),
        parser_type=data.get("parser_type"),
        created_at=data.get("created_at"),
    )


def _transaction_doc_id(user_id: str, email_id: str) -> str:
    digest = hashlib.sha1(email_id.encode("utf-8")).hexdigest()
    return f"{user_id}_{digest}"


def count_users() -> int:
    if not firestore_enabled():
        return 0
    return sum(1 for _ in _users().limit(2_000).stream())


def get_user_by_id(user_id: str | int | None) -> UserRecord | None:
    if not firestore_enabled() or user_id is None:
        return None
    doc = _users().document(str(user_id)).get()
    if not doc.exists:
        return None
    return _user_from_doc(doc)


def get_user_by_email(email: str | None) -> UserRecord | None:
    if not firestore_enabled() or not email:
        return None
    docs = _users().where("email", "==", _clean_email(email)).limit(1).stream()
    for doc in docs:
        return _user_from_doc(doc)
    return None


def get_user_by_username(username: str | None) -> UserRecord | None:
    if not firestore_enabled() or not username:
        return None
    docs = _users().where("username", "==", _clean_username(username)).limit(1).stream()
    for doc in docs:
        return _user_from_doc(doc)
    return None


def get_user_by_firebase_uid(firebase_uid: str | None) -> UserRecord | None:
    if not firestore_enabled() or not firebase_uid:
        return None
    docs = _users().where("firebase_uid", "==", firebase_uid).limit(1).stream()
    for doc in docs:
        return _user_from_doc(doc)
    return None


def username_exists(username: str, exclude_user_id: str | None = None) -> bool:
    existing = get_user_by_username(username)
    if not existing:
        return False
    return exclude_user_id is None or existing.id != str(exclude_user_id)


def next_available_username(preferred: str, exclude_user_id: str | None = None) -> str:
    base = _clean_username(preferred) or f"user_{secrets.token_hex(3)}"
    candidate = base[:150]
    if not username_exists(candidate, exclude_user_id=exclude_user_id):
        return candidate
    suffix = 1
    while True:
        suffix += 1
        candidate = f"{base[:140]}_{suffix}"
        if not username_exists(candidate, exclude_user_id=exclude_user_id):
            return candidate


def save_user_record(user: UserRecord) -> UserRecord:
    if not firestore_enabled():
        raise RuntimeError("Firestore is not configured")
    payload = {
        "username": _clean_username(user.username),
        "email": _clean_email(user.email) or None,
        "firebase_uid": user.firebase_uid,
        "password_hash": user.password_hash,
        "created_at": user.created_at or _now(),
    }
    _users().document(str(user.id)).set(payload, merge=True)
    return get_user_by_id(user.id)


def create_user_record(
    *,
    username: str,
    email: str | None = None,
    firebase_uid: str | None = None,
    password_hash: str = "",
    user_id: str | None = None,
    is_demo: bool = False,
) -> UserRecord:
    if not firestore_enabled():
        raise RuntimeError("Firestore is not configured")
    doc_id = str(user_id or firebase_uid or f"user_{secrets.token_hex(12)}")
    payload = {
        "username": _clean_username(username),
        "email": _clean_email(email) or None,
        "firebase_uid": firebase_uid,
        "password_hash": password_hash,
        "created_at": _now(),
        "is_demo": is_demo,
    }
    _users().document(doc_id).set(payload)
    return get_user_by_id(doc_id)


def ensure_demo_user(password_hash: str) -> UserRecord:
    existing = get_user_by_username("demo")
    if existing:
        return existing
    return create_user_record(
        username="demo",
        email="demo@local.invalid",
        password_hash=password_hash,
        user_id="demo",
        is_demo=True,
    )


def get_all_transactions(user_id: str | int | None = None) -> list[TransactionRecord]:
    if not firestore_enabled():
        return []
    query = _transactions()
    if user_id is not None:
        query = query.where("user_id", "==", str(user_id))
    docs = query.stream()
    return sorted((_transaction_from_doc(doc) for doc in docs), key=lambda t: t.date or datetime.min, reverse=True)


def get_transaction_by_id(transaction_id: str) -> TransactionRecord | None:
    if not firestore_enabled():
        return None
    doc = _transactions().document(str(transaction_id)).get()
    if not doc.exists:
        return None
    return _transaction_from_doc(doc)


def get_existing_email_ids(user_id: str | int | None = None) -> set[str]:
    return {t.email_id for t in get_all_transactions(user_id=user_id) if t.email_id}


def save_transaction_record(parsed_data: dict, *, user_id: str | int) -> TransactionRecord | None:
    if not firestore_enabled():
        return None
    email_id = parsed_data.get("email_id")
    if not email_id:
        return None
    user_id_str = str(user_id)
    doc_id = _transaction_doc_id(user_id_str, email_id)
    doc_ref = _transactions().document(doc_id)
    existing = doc_ref.get()
    if existing.exists:
        return _transaction_from_doc(existing)
    amount = parsed_data.get("amount")
    if amount is None:
        return None
    payload = {
        "user_id": user_id_str,
        "email_id": email_id,
        "vendor": parsed_data.get("vendor") or "Unknown",
        "amount": float(amount),
        "tax": float(parsed_data["tax"]) if parsed_data.get("tax") is not None else None,
        "date": parsed_data.get("date"),
        "category": parsed_data.get("category"),
        "payment_method": parsed_data.get("payment_method"),
        "items": parsed_data.get("items"),
        "email_body": parsed_data.get("email_body") or parsed_data.get("email body"),
        "created_at": _now(),
        "updated_at": _now(),
    }
    doc_ref.set(payload)
    return get_transaction_by_id(doc_id)


def delete_zero_amount_transactions(user_id: str | int | None = None) -> int:
    if not firestore_enabled():
        return 0
    to_delete = [
        t for t in get_all_transactions(user_id=user_id)
        if t.amount is None or abs(float(t.amount)) < 0.0001
    ]
    for transaction in to_delete:
        _transactions().document(transaction.id).delete()
    return len(to_delete)


def clear_transactions(user_id: str | int | None = None) -> int:
    if not firestore_enabled():
        return 0
    items = get_all_transactions(user_id=user_id)
    for transaction in items:
        _transactions().document(transaction.id).delete()
    return len(items)


def update_transaction(transaction_id: str, *, user_id: str | int | None, payload: dict) -> TransactionRecord | None:
    if not firestore_enabled():
        return None
    transaction = get_transaction_by_id(transaction_id)
    if not transaction:
        return None
    if user_id is not None and str(transaction.user_id) != str(user_id):
        return None

    updates = {"updated_at": _now()}
    if "vendor" in payload and (payload.get("vendor") or "").strip():
        updates["vendor"] = (payload.get("vendor") or "").strip()
    if "amount" in payload:
        updates["amount"] = float(str(payload["amount"]).replace("$", "").replace(",", "").strip())
    if "tax" in payload:
        raw_tax = str(payload["tax"]).replace("$", "").replace(",", "").strip()
        updates["tax"] = float(raw_tax) if raw_tax else None
    if "date" in payload and payload.get("date"):
        value = payload.get("date")
        if isinstance(value, datetime):
            updates["date"] = value
        else:
            from dateutil import parser as date_parser
            updates["date"] = date_parser.parse(str(value))

    _transactions().document(str(transaction_id)).set(updates, merge=True)
    return get_transaction_by_id(transaction_id)


def delete_transaction(transaction_id: str, *, user_id: str | int | None) -> bool:
    if not firestore_enabled():
        return False
    transaction = get_transaction_by_id(transaction_id)
    if not transaction:
        return False
    if user_id is not None and str(transaction.user_id) != str(user_id):
        return False
    _transactions().document(str(transaction_id)).delete()
    return True


def get_all_vendors() -> list[VendorRecord]:
    if not firestore_enabled():
        return []
    return [_vendor_from_doc(doc) for doc in _vendors().stream()]

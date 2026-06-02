import os
import threading
import json
import hashlib
import secrets
import base64 as b64
import uuid
import random
import re
from pathlib import Path

from fastapi import FastAPI, HTTPException, Body, Request
from fastapi.responses import RedirectResponse
from fastapi.middleware.cors import CORSMiddleware
from .data_helper import (
    clear_transactions_for_user,
    deduplicate_transactions_for_user,
    delete_transaction_for_user,
    delete_zero_amount_transactions,
    get_all_transactions,
    get_existing_email_ids,
    update_transaction_for_user,
)
from .database import SessionLocal
from .models import Transaction, User, AuthToken, GoogleCredential
from .config import settings
from cryptography.fernet import Fernet, InvalidToken
from google_auth_oauthlib.flow import Flow
from .email_scraper import credentials_from_refresh_token
from .ai_client import generate_text
from datetime import datetime, timedelta
import uvicorn
from dateutil import parser as date_parser
from collections import defaultdict
from io import StringIO, BytesIO
import base64
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from sqlalchemy import or_
from .ai_client import generate_text
from .firestore_store import (
    count_users as count_firestore_users,
    create_user_record,
    ensure_demo_user,
    firestore_enabled,
    get_all_transactions as get_all_firestore_transactions,
    get_firestore_client,
    get_transaction_by_id as get_firestore_transaction_by_id,
    get_user_by_email,
    get_user_by_firebase_uid,
    get_user_by_id,
    get_user_by_username,
    next_available_username as next_firestore_username,
    save_user_record,
)

try:
    import firebase_admin
    from firebase_admin import auth as firebase_auth
    from firebase_admin import credentials as firebase_credentials
    from firebase_admin import firestore as firebase_firestore
except Exception:
    firebase_admin = None
    firebase_auth = None
    firebase_credentials = None
    firebase_firestore = None

app = FastAPI()
DEMO_PARSE_RUNS = {}
DEMO_PARSE_LOCK = threading.Lock()
SYNC_RUNS = {}
SYNC_LOCK = threading.Lock()

# Allow your website to call the API
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, specify your domain
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

PASSWORD_ITERATIONS = 120_000
TOKEN_TTL_DAYS = 30
EMAIL_REGEX = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_FIREBASE_APP = None

def _hash_password(password: str) -> str:
    salt = os.urandom(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, PASSWORD_ITERATIONS)
    return f"{b64.b64encode(salt).decode()}${b64.b64encode(dk).decode()}"

def _verify_password(password: str, stored: str) -> bool:
    try:
        salt_b64, hash_b64 = stored.split("$", 1)
        salt = b64.b64decode(salt_b64.encode())
        expected = b64.b64decode(hash_b64.encode())
        dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, PASSWORD_ITERATIONS)
        return secrets.compare_digest(dk, expected)
    except Exception:
        return False

def _create_token(user_id: int) -> str:
    token = secrets.token_urlsafe(32)
    expires_at = datetime.utcnow() + timedelta(days=TOKEN_TTL_DAYS)
    db = SessionLocal()
    try:
        db.add(AuthToken(user_id=user_id, token=token, expires_at=expires_at))
        db.commit()
        return token
    finally:
        db.close()

def _normalize_username(value: str) -> str:
    return (value or "").strip().lower()

def _normalize_email(value: str) -> str:
    return (value or "").strip().lower()

def _sanitize_username(value: str) -> str:
    cleaned = re.sub(r"[^a-z0-9]+", "_", _normalize_username(value))
    cleaned = cleaned.strip("_")
    if len(cleaned) < 3:
        cleaned = f"user_{secrets.token_hex(3)}"
    return cleaned[:150]

def _validate_password(password: str) -> list[str]:
    requirements = []
    if len(password) < 8:
        requirements.append("at least 8 characters")
    if not re.search(r"[A-Z]", password):
        requirements.append("1 uppercase letter")
    if not re.search(r"\d", password):
        requirements.append("1 number")
    if not re.search(r"[^A-Za-z0-9]", password):
        requirements.append("1 special character")
    return requirements

def _claim_legacy_transactions(user_id: int):
    """Assign legacy transactions (user_id is NULL) to the only user in the system."""
    if firestore_enabled():
        return
    db = SessionLocal()
    try:
        user_count = db.query(User).count()
        if user_count != 1:
            return
        updated = (
            db.query(Transaction)
            .filter(Transaction.user_id.is_(None))
            .update({Transaction.user_id: user_id})
        )
        if updated:
            db.commit()
    finally:
        db.close()

def _firebase_enabled() -> bool:
    return bool(
        settings.firebase_service_account_json
        or settings.firebase_service_account_path
        or os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
    )

def _get_public_firebase_web_config() -> dict:
    config = {
        "apiKey": settings.firebase_web_api_key or "",
        "authDomain": settings.firebase_web_auth_domain or "",
        "projectId": settings.firebase_project_id or "",
        "appId": settings.firebase_web_app_id or "",
    }
    if settings.firebase_web_measurement_id:
        config["measurementId"] = settings.firebase_web_measurement_id
    return config

def _get_firebase_app():
    global _FIREBASE_APP
    if _FIREBASE_APP is not None:
        return _FIREBASE_APP
    if not _firebase_enabled():
        return None
    if firebase_admin is None or firebase_credentials is None:
        raise HTTPException(status_code=500, detail="firebase-admin is not installed")

    # Reuse an already-initialized default app (e.g. initialized by firestore_store.py)
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

def _verify_firebase_token(token: str) -> dict | None:
    if not token or not _firebase_enabled() or firebase_auth is None:
        return None
    try:
        app = _get_firebase_app()
        if app is None:
            return None
        return firebase_auth.verify_id_token(token, app=app)
    except Exception:
        return None

def _get_firestore_client():
    if firebase_firestore is None:
        return None
    app = _get_firebase_app()
    if app is None:
        return None
    return firebase_firestore.client(app=app)

def _next_available_username(db, preferred: str, exclude_user_id: int | None = None) -> str:
    if firestore_enabled():
        return next_firestore_username(preferred, exclude_user_id=str(exclude_user_id) if exclude_user_id is not None else None)
    base = _sanitize_username(preferred)
    candidate = base
    suffix = 1
    while True:
        query = db.query(User).filter(User.username == candidate)
        if exclude_user_id is not None:
            query = query.filter(User.id != exclude_user_id)
        if not query.first():
            return candidate
        suffix += 1
        candidate = f"{base[:140]}_{suffix}"

def _upsert_user_from_firebase_claims(claims: dict) -> User:
    firebase_uid = (claims or {}).get("uid")
    email = _normalize_email((claims or {}).get("email") or "")
    display_name = (claims or {}).get("name") or (email.split("@")[0] if email else "")
    if not firebase_uid:
        raise HTTPException(status_code=401, detail="Invalid Firebase token")

    if firestore_enabled():
        user = get_user_by_firebase_uid(firebase_uid)
        if not user and email:
            user = get_user_by_email(email)
        if user:
            updated = False
            if user.firebase_uid != firebase_uid:
                user.firebase_uid = firebase_uid
                updated = True
            if email and user.email != email:
                user.email = email
                updated = True
            preferred_username = _sanitize_username(display_name or user.username or email or "user")
            if user.username != preferred_username:
                user.username = _next_available_username(None, preferred_username, exclude_user_id=user.id)
                updated = True
            if updated:
                user = save_user_record(user)
            _claim_legacy_transactions(user.id)
            return user

        user = create_user_record(
            username=_next_available_username(None, display_name or email or "user"),
            email=email or None,
            firebase_uid=firebase_uid,
            password_hash=_hash_password(secrets.token_urlsafe(32)),
        )
        _claim_legacy_transactions(user.id)
        return user

    db = SessionLocal()
    try:
        user = db.query(User).filter(User.firebase_uid == firebase_uid).first()
        if not user and email:
            user = db.query(User).filter(User.email == email).first()

        if user:
            updated = False
            if user.firebase_uid != firebase_uid:
                user.firebase_uid = firebase_uid
                updated = True
            if email and user.email != email:
                user.email = email
                updated = True
            preferred_username = _sanitize_username(display_name or user.username or email or "user")
            if user.username != preferred_username:
                user.username = _next_available_username(db, preferred_username, exclude_user_id=user.id)
                updated = True
            if updated:
                db.commit()
                db.refresh(user)
            _claim_legacy_transactions(user.id)
            return user

        username = _next_available_username(db, display_name or email or "user")
        user = User(
            username=username,
            email=email or None,
            firebase_uid=firebase_uid,
            password_hash=_hash_password(secrets.token_urlsafe(32)),
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        _claim_legacy_transactions(user.id)
        return user
    finally:
        db.close()

def _firebase_doc_id_for_user(user: User) -> str:
    return user.firebase_uid or f"local-user-{user.id}"

def _save_google_refresh_token_for_user(user_id: int, email: str | None, enc_refresh: str):
    if firestore_enabled():
        user = get_user_by_id(user_id)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        firestore_client = _get_firestore_client()
        if firestore_client is None:
            raise HTTPException(status_code=500, detail="Firestore is not available")
        doc_ref = (
            firestore_client
            .collection(settings.firebase_firestore_tokens_collection)
            .document(_firebase_doc_id_for_user(user))
        )
        doc_ref.set(
            {
                "user_id": user.id,
                "firebase_uid": user.firebase_uid,
                "email": email or user.email,
                "refresh_token_enc": enc_refresh,
                "updated_at": datetime.utcnow(),
            },
            merge=True,
        )
        return

    db = SessionLocal()
    try:
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        firestore_client = _get_firestore_client()
        if firestore_client is not None:
            doc_ref = (
                firestore_client
                .collection(settings.firebase_firestore_tokens_collection)
                .document(_firebase_doc_id_for_user(user))
            )
            doc_ref.set(
                {
                    "user_id": user.id,
                    "firebase_uid": user.firebase_uid,
                    "email": email or user.email,
                    "refresh_token_enc": enc_refresh,
                    "updated_at": datetime.utcnow(),
                },
                merge=True,
            )
            return

        row = db.query(GoogleCredential).filter(GoogleCredential.user_id == user_id).first()
        if row:
            row.refresh_token_enc = enc_refresh
            row.email = email or row.email
        else:
            row = GoogleCredential(user_id=user_id, refresh_token_enc=enc_refresh, email=email)
            db.add(row)
        db.commit()
    finally:
        db.close()

def _get_user_from_request(request: Request):
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        return None
    token = auth.split(" ", 1)[1].strip()
    if not token:
        return None

    firebase_claims = _verify_firebase_token(token)
    if firebase_claims:
        return _upsert_user_from_firebase_claims(firebase_claims)

    db = SessionLocal()
    try:
        row = (
            db.query(AuthToken, User)
            .join(User, User.id == AuthToken.user_id)
            .filter(AuthToken.token == token)
            .first()
        )
        if not row:
            return None
        auth_token, user = row
        if auth_token.expires_at and auth_token.expires_at < datetime.utcnow():
            db.delete(auth_token)
            db.commit()
            return None
        return user
    finally:
        db.close()

def _require_user(request: Request) -> User:
    user = _get_user_from_request(request)
    if not user:
        raise HTTPException(status_code=401, detail="Unauthorized")
    return user

def _get_fernet() -> Fernet:
    key = settings.fernet_key or ""
    if not key:
        raise HTTPException(status_code=500, detail="FERNET_KEY is not configured")
    return Fernet(key.encode("utf-8"))

def _encrypt_token(raw: str) -> str:
    f = _get_fernet()
    return f.encrypt(raw.encode("utf-8")).decode("utf-8")

def _decrypt_token(enc: str) -> str:
    f = _get_fernet()
    return f.decrypt(enc.encode("utf-8")).decode("utf-8")

def _get_demo_user() -> User:
    """Ensure a shared demo user exists and return it."""
    if firestore_enabled():
        return ensure_demo_user(_hash_password(secrets.token_urlsafe(16)))
    db = SessionLocal()
    try:
        demo = db.query(User).filter(User.username == "demo").first()
        if demo:
            return demo
        demo = User(username="demo", password_hash=_hash_password(secrets.token_urlsafe(16)))
        db.add(demo)
        db.commit()
        db.refresh(demo)
        return demo
    finally:
        db.close()

def _get_google_refresh_token_for_user(user_id: int) -> str | None:
    if firestore_enabled():
        user = get_user_by_id(user_id)
        firestore_client = _get_firestore_client()
        if user and firestore_client is not None:
            doc = (
                firestore_client
                .collection(settings.firebase_firestore_tokens_collection)
                .document(_firebase_doc_id_for_user(user))
                .get()
            )
            if doc.exists:
                payload = doc.to_dict() or {}
                enc_value = payload.get("refresh_token_enc")
                if enc_value:
                    try:
                        return _decrypt_token(enc_value)
                    except InvalidToken:
                        return None
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.id == user_id).first()
        firestore_client = _get_firestore_client()
        if user and firestore_client is not None:
            doc = (
                firestore_client
                .collection(settings.firebase_firestore_tokens_collection)
                .document(_firebase_doc_id_for_user(user))
                .get()
            )
            if doc.exists:
                payload = doc.to_dict() or {}
                enc_value = payload.get("refresh_token_enc")
                if enc_value:
                    try:
                        return _decrypt_token(enc_value)
                    except InvalidToken:
                        return None
        row = db.query(GoogleCredential).filter(GoogleCredential.user_id == user_id).first()
        if not row:
            return None
        try:
            return _decrypt_token(row.refresh_token_enc)
        except InvalidToken:
            return None
    finally:
        db.close()

@app.get("/")
def root():
    return {"message": "Receipt Automation API", "status": "running"}

@app.get("/api/public-config")
def public_config():
    return {
        "firebase": _get_public_firebase_web_config(),
    }

@app.post("/api/auth/register")
def register(payload: dict = Body(...)):
    username = _normalize_username(payload.get("username") or "")
    email = _normalize_email(payload.get("email") or "")
    password = payload.get("password") or ""
    if len(username) < 3:
        raise HTTPException(status_code=400, detail="Username must be at least 3 characters.")
    if not email:
        raise HTTPException(status_code=400, detail="Email is required.")
    if not EMAIL_REGEX.match(email):
        raise HTTPException(status_code=400, detail="Enter a valid email address.")
    password_requirements = _validate_password(password)
    if password_requirements:
        raise HTTPException(
            status_code=400,
            detail=f"Password not strong enough. It needs {', '.join(password_requirements)}."
        )

    if firestore_enabled():
        existing = get_user_by_username(username)
        if existing:
            raise HTTPException(status_code=400, detail="Username already exists.")
        existing_email = get_user_by_email(email)
        if existing_email:
            raise HTTPException(status_code=400, detail="Email already exists.")
        user = create_user_record(username=username, email=email, password_hash=_hash_password(password))
        _claim_legacy_transactions(user.id)
        token = _create_token(user.id)
        return {"token": token, "user": {"id": user.id, "username": user.username, "email": user.email}}

    db = SessionLocal()
    try:
        existing = db.query(User).filter(User.username == username).first()
        if existing:
            raise HTTPException(status_code=400, detail="Username already exists.")
        existing_email = db.query(User).filter(User.email == email).first()
        if existing_email:
            raise HTTPException(status_code=400, detail="Email already exists.")
        user = User(username=username, email=email, password_hash=_hash_password(password))
        db.add(user)
        db.commit()
        db.refresh(user)
        _claim_legacy_transactions(user.id)
        token = _create_token(user.id)
        return {"token": token, "user": {"id": user.id, "username": user.username, "email": user.email}}
    finally:
        db.close()

@app.post("/api/auth/login")
def login(payload: dict = Body(...)):
    username = _normalize_username(payload.get("username") or payload.get("email") or "")
    password = payload.get("password") or ""

    if firestore_enabled():
        user = get_user_by_username(username) or get_user_by_email(username)
        if not user or not _verify_password(password, user.password_hash):
            raise HTTPException(status_code=401, detail="Invalid username/email or password.")
        _claim_legacy_transactions(user.id)
        token = _create_token(user.id)
        return {"token": token, "user": {"id": user.id, "username": user.username, "email": user.email}}

    db = SessionLocal()
    try:
        user = db.query(User).filter(or_(User.username == username, User.email == username)).first()
        if not user or not _verify_password(password, user.password_hash):
            raise HTTPException(status_code=401, detail="Invalid username/email or password.")
        _claim_legacy_transactions(user.id)
        token = _create_token(user.id)
        return {"token": token, "user": {"id": user.id, "username": user.username, "email": user.email}}
    finally:
        db.close()

@app.post("/api/auth/logout")
def logout(request: Request):
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        return {"status": "ok"}
    token = auth.split(" ", 1)[1].strip()
    if not token:
        return {"status": "ok"}
    db = SessionLocal()
    try:
        row = db.query(AuthToken).filter(AuthToken.token == token).first()
        if row:
            db.delete(row)
            db.commit()
        return {"status": "ok"}
    finally:
        db.close()

@app.get("/api/auth/me")
def auth_me(request: Request):
    user = _require_user(request)
    return {"id": user.id, "username": user.username, "email": user.email, "firebase_uid": user.firebase_uid}

@app.get("/api/gmail-status")
def gmail_status(request: Request):
    user = _require_user(request)
    connected = False
    email = None
    try:
        token = _get_google_refresh_token_for_user(user.id)
        connected = token is not None
        if connected:
            if firestore_enabled():
                fc = _get_firestore_client()
                if fc:
                    doc = fc.collection(settings.firebase_firestore_tokens_collection).document(_firebase_doc_id_for_user(user)).get()
                    if doc.exists:
                        email = (doc.to_dict() or {}).get("email")
            else:
                db = SessionLocal()
                try:
                    row = db.query(GoogleCredential).filter(GoogleCredential.user_id == user.id).first()
                    if row:
                        email = row.email
                finally:
                    db.close()
    except Exception:
        pass
    return {"connected": connected, "email": email}

@app.get("/api/google/auth-url")
def google_auth_url(request: Request):
    user = _require_user(request)
    client_id = settings.google_oauth_client_id or ""
    client_secret = settings.google_oauth_client_secret or ""
    redirect_uri = settings.google_oauth_redirect_uri or ""
    if not client_id or not client_secret or not redirect_uri:
        raise HTTPException(status_code=500, detail="Google OAuth config missing")

    state_payload = {
        "user_id": user.id,
        "nonce": secrets.token_urlsafe(12),
        "ts": datetime.utcnow().isoformat() + "Z",
    }
    state = _encrypt_token(json.dumps(state_payload))

    flow = Flow.from_client_config(
        {
            "web": {
                "client_id": client_id,
                "client_secret": client_secret,
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
            }
        },
        scopes=['https://www.googleapis.com/auth/gmail.readonly'],
        redirect_uri=redirect_uri,
    )
    auth_url, _ = flow.authorization_url(
        access_type="offline",
        include_granted_scopes="true",
        prompt="consent",
        state=state,
    )
    return {"auth_url": auth_url}

@app.get("/api/google/callback")
def google_oauth_callback(code: str = None, state: str = None, error: str = None):
    from fastapi.responses import HTMLResponse as _HTMLResponse
    frontend = (settings.frontend_url or "").rstrip("/")

    def _page(success: bool, message: str):
        color = "#4ade80" if success else "#f87171"
        label = "Gmail Connected" if success else "Connection Failed"
        redirect = f'<script>setTimeout(()=>{{window.location.href="{frontend}";}},2500);</script>' if frontend else ""
        back = f'<a href="{frontend}" style="color:#aaa;font-size:0.85rem;text-decoration:none;">Back to app</a>' if frontend else ""
        return _HTMLResponse(content=f"""<!DOCTYPE html><html><head><meta charset="UTF-8">
<title>{label}</title>
<style>body{{margin:0;background:#0a0a0a;color:#fff;font-family:system-ui,sans-serif;display:flex;align-items:center;justify-content:center;height:100vh;flex-direction:column;gap:16px;}}
.dot{{width:56px;height:56px;border-radius:50%;background:{color};display:flex;align-items:center;justify-content:center;font-size:1.6rem;}}
h2{{margin:0;font-size:1.2rem;}}p{{margin:0;color:#aaa;font-size:0.88rem;}}</style>
{redirect}</head><body>
<div class="dot">{"✓" if success else "✗"}</div>
<h2>{label}</h2><p>{message}</p>{back}
</body></html>""")

    if error:
        return _page(False, f"Google returned: {error}")

    client_id = settings.google_oauth_client_id or ""
    client_secret = settings.google_oauth_client_secret or ""
    redirect_uri = settings.google_oauth_redirect_uri or ""
    if not client_id or not client_secret or not redirect_uri:
        return _page(False, "OAuth credentials are not configured on the server.")

    try:
        state_data = json.loads(_decrypt_token(state))
        user_id = str(state_data.get("user_id"))
    except Exception:
        return _page(False, "Invalid session state. Please try again.")

    try:
        flow = Flow.from_client_config(
            {
                "web": {
                    "client_id": client_id,
                    "client_secret": client_secret,
                    "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                    "token_uri": "https://oauth2.googleapis.com/token",
                }
            },
            scopes=['https://www.googleapis.com/auth/gmail.readonly'],
            redirect_uri=redirect_uri,
        )
        flow.fetch_token(code=code)
        creds = flow.credentials
        if not creds or not creds.refresh_token:
            return _page(False, "No refresh token returned. Try revoking access in your Google account and connecting again.")

        enc_refresh = _encrypt_token(creds.refresh_token)
        email = getattr(creds, "account", None)
        _save_google_refresh_token_for_user(user_id, email, enc_refresh)
    except Exception as e:
        return _page(False, f"Token exchange failed: {e}")

    return _page(True, "Your Gmail is connected. You can now sync receipts." + (" Redirecting…" if frontend else ""))

def _nonzero_transactions(transactions):
    """Filter out transactions with amount 0 or None (no expenditure)."""
    out = []
    for t in transactions:
        if t.amount is None:
            continue
        try:
            amt = float(t.amount)
            if amt == 0 or abs(amt) < 0.0001:
                continue
        except (TypeError, ValueError):
            continue
        out.append(t)
    return out

@app.get("/api/transactions")
def get_transactions(request: Request):
    """Get all transactions from database (excludes zero-amount)."""
    try:
        user = _require_user(request)
        transactions = get_all_transactions(user_id=user.id)
        transactions = _nonzero_transactions(transactions)
        return [
            {
                "id": t.id,
                "date": t.date.strftime('%Y-%m-%d') if isinstance(t.date, datetime) else str(t.date),
                "vendor": t.vendor or "Unknown",
                "amount": float(t.amount) if t.amount else 0.0,
                "tax": float(t.tax) if t.tax else 0.0,
                "email_id": t.email_id,
                "category": t.category,
                "payment_method": t.payment_method,
                "items": t.items,
                "email_body": t.email_body,
            }
            for t in transactions
        ]
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching transactions: {str(e)}")

@app.get("/api/stats")
def get_stats(request: Request):
    """Get dashboard statistics (excludes zero-amount transactions)."""
    try:
        user = _require_user(request)
        transactions = _nonzero_transactions(get_all_transactions(user_id=user.id))
        total_spent = sum(t.amount for t in transactions if t.amount)
        total_receipts = len(transactions)
        unique_vendors = len(set(t.vendor for t in transactions if t.vendor))
        avg_transaction = total_spent / total_receipts if total_receipts > 0 else 0
        
        return {
            "total_spent": round(total_spent, 2),
            "total_receipts": total_receipts,
            "unique_vendors": unique_vendors,
            "avg_transaction": round(avg_transaction, 2)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching stats: {str(e)}")

@app.get("/api/top-vendors")
def get_top_vendors(request: Request):
    """Get top vendors by spending (excludes zero-amount transactions)."""
    try:
        user = _require_user(request)
        transactions = _nonzero_transactions(get_all_transactions(user_id=user.id))
        # Group by vendor
        vendor_totals = {}
        vendor_counts = {}
        
        for t in transactions:
            vendor = t.vendor or "Unknown"
            amount = t.amount or 0
            
            if vendor not in vendor_totals:
                vendor_totals[vendor] = 0
                vendor_counts[vendor] = 0
            
            vendor_totals[vendor] += amount
            vendor_counts[vendor] += 1
        
        # Sort by total spending
        top_vendors = sorted(vendor_totals.items(), key=lambda x: x[1], reverse=True)[:4]
        
        return [
            {
                "vendor": vendor,
                "total": round(amount, 2),
                "count": vendor_counts[vendor]
            }
            for vendor, amount in top_vendors
        ]
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching top vendors: {str(e)}")

@app.post("/api/transactions/deduplicate")
def deduplicate_transactions(request: Request):
    """Remove duplicate transactions (same order number or same vendor+amount+date)."""
    user = _require_user(request)
    removed = deduplicate_transactions_for_user(user_id=user.id)
    return {"status": "success", "removed": removed, "message": f"Removed {removed} duplicate(s)."}

@app.post("/api/cleanup-zero")
def cleanup_zero_transactions(request: Request):
    """Delete all transactions with amount 0 or null from the database. Returns count removed."""
    try:
        user = _require_user(request)
        deleted = delete_zero_amount_transactions(user_id=user.id)
        return {"status": "success", "deleted": deleted, "message": f"Removed {deleted} zero-amount transaction(s)."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Cleanup failed: {str(e)}")

def _update_sync_run(run_id: str, **kwargs):
    with SYNC_LOCK:
        run = SYNC_RUNS.get(run_id)
        if run:
            run.update(kwargs)

def _is_cancelled(run_id):
    if not run_id:
        return False
    with SYNC_LOCK:
        return SYNC_RUNS.get(run_id, {}).get("cancelled", False)

def _append_sync_log(run_id: str, line: str):
    if not run_id:
        return
    with SYNC_LOCK:
        run = SYNC_RUNS.get(run_id)
        if run is None:
            return
        run.setdefault("logs", [])
        run["logs"].append(f"[{datetime.utcnow().strftime('%H:%M:%S')}] {line}")
        if len(run["logs"]) > 500:
            run["logs"] = run["logs"][-500:]

def _run_sync(user_id: int, run_id: str | None = None, date_from: str | None = None, date_to: str | None = None):
    """Run email sync in background with optional progress tracking and date range."""
    def _status(status: str, message: str = ""):
        if run_id:
            _update_sync_run(run_id, status=status, message=message, updated_at=_now_iso())

    def _progress(message: str):
        """Update the live status message and append it to the scan log."""
        _status("running", message)
        _append_sync_log(run_id, message)

    try:
        _progress("Connecting to Gmail…")
        from .main import main
        refresh_token = _get_google_refresh_token_for_user(user_id)
        if not refresh_token:
            _status("failed", "Google account not connected. Use Connect Gmail to authorise.")
            _append_sync_log(run_id, "Google account not connected.")
            return
        client_id = settings.google_oauth_client_id or ""
        client_secret = settings.google_oauth_client_secret or ""
        if not client_id or not client_secret:
            _status("failed", "Server OAuth configuration missing.")
            _append_sync_log(run_id, "Server OAuth configuration missing.")
            return
        if _is_cancelled(run_id):
            _status("failed", "Cancelled.")
            return
        gmail_creds = credentials_from_refresh_token(refresh_token, client_id, client_secret)
        _progress("Searching inbox for receipts…")
        summary = main(
            user_id=user_id,
            gmail_creds=gmail_creds,
            date_from=date_from,
            date_to=date_to,
            run_id=run_id,
            is_cancelled=_is_cancelled,
            progress=_progress,
        )
        if _is_cancelled(run_id):
            _status("failed", "Cancelled.")
            return
        delete_zero_amount_transactions(user_id=user_id)
        removed = deduplicate_transactions_for_user(user_id=user_id)
        if removed:
            _append_sync_log(run_id, f"Removed {removed} duplicate transaction(s).")
        _print_db_snapshot(user_id=user_id)
        saved = (summary or {}).get("saved", 0)
        skipped = (summary or {}).get("skipped", 0)
        scanned = (summary or {}).get("scanned", 0)
        _append_sync_log(run_id, f"Done. Scanned {scanned}, saved {saved}, skipped {skipped}.")
        _status("completed", f"Scan finished — {saved} new receipt(s) saved.")
    except Exception as e:
        _status("failed", str(e))
        _append_sync_log(run_id, f"Error: {e}")
        print(f"❌ Sync failed: {e}")

def _require_api_key(request: Request):
    """Require X-API-Key when SYNC_API_KEY is set."""
    expected = os.getenv("SYNC_API_KEY")
    if not expected:
        return
    provided = request.headers.get("X-API-Key", "")
    if provided != expected:
        raise HTTPException(status_code=401, detail="Unauthorized")

def _demo_emails_path() -> Path:
    path = Path(__file__).resolve().parent / "reports" / "demo_emails.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path

def _now_iso() -> str:
    return datetime.utcnow().isoformat() + "Z"

def _init_demo_run(run_id: str, user_id: int, force_reprocess: bool = False):
    with DEMO_PARSE_LOCK:
        DEMO_PARSE_RUNS[run_id] = {
            "run_id": run_id,
            "user_id": user_id,
            "status": "queued",
            "total": 0,
            "processed": 0,
            "success": 0,
            "skipped": 0,
            "failed": 0,
            "force_reprocess": force_reprocess,
            "started_at": _now_iso(),
            "finished_at": None,
            "logs": [],
        }

def _append_demo_log(run_id: str, line: str):
    with DEMO_PARSE_LOCK:
        run = DEMO_PARSE_RUNS.get(run_id)
        if not run:
            return
        run["logs"].append(f"[{datetime.utcnow().strftime('%H:%M:%S')}] {line}")
        if len(run["logs"]) > 500:
            run["logs"] = run["logs"][-500:]

def _update_demo_run(run_id: str, **kwargs):
    with DEMO_PARSE_LOCK:
        run = DEMO_PARSE_RUNS.get(run_id)
        if not run:
            return
        run.update(kwargs)

def _get_demo_run(run_id: str):
    with DEMO_PARSE_LOCK:
        run = DEMO_PARSE_RUNS.get(run_id)
        return dict(run) if run else None

def _demo_email_id(email: dict) -> str:
    """Stable id for demo emails based on content so duplicates are skipped."""
    raw = "|".join(
        [
            str(email.get("from", "")),
            str(email.get("subject", "")),
            str(email.get("date", "")),
            str(email.get("body", "")),
        ]
    )
    return hashlib.sha256(raw.encode("utf-8", errors="ignore")).hexdigest()


def _prepare_demo_emails(emails):
    demo_rows = []
    for e in emails:
        email = {
            "id": e.get("id") or _demo_email_id(e),
            "from": e.get("from", "demo@example.com"),
            "subject": e.get("subject", "Demo receipt"),
            "date": e.get("date", datetime.utcnow().strftime("%Y-%m-%d")),
            "body": e.get("body", "Total: $10.00"),
        }
        demo_rows.append(email)
    return demo_rows

def _run_demo_parse(run_id: str, user_id: int, force_reprocess: bool = False):
    from .parser_select import vendor_search, vendor_regex_search, vendor_from_sender_domain
    from .parsers.generic_parser import parse_generic_emails_batch
    from .parsers.paypal_parser import paypal_parser
    from .parsers.amazon_parser import amazon_parser
    from .vendor_normalize import normalize_vendor_name
    from .data_helper import get_existing_email_ids, log_transaction

    try:
        _update_demo_run(run_id, status="running")
        path = _demo_emails_path()
        if not path.exists():
            _append_demo_log(run_id, "No demo_emails.json found. Generate demo emails first.")
            _update_demo_run(run_id, status="failed", finished_at=_now_iso())
            return

        emails = json.loads(path.read_text())
        if not isinstance(emails, list) or not emails:
            _append_demo_log(run_id, "Demo email list is empty. Generate demo emails first.")
            _update_demo_run(run_id, status="failed", finished_at=_now_iso())
            return

        existing_ids = get_existing_email_ids(user_id=user_id)

        # Separate already-processed from emails that need parsing
        to_process = []
        skipped = 0
        for email in emails:
            if not force_reprocess and email.get("id") in existing_ids:
                skipped += 1
            else:
                to_process.append(email)

        _update_demo_run(run_id, total=len(emails), processed=skipped, success=0, skipped=skipped, failed=0)
        _append_demo_log(run_id, f"Loaded {len(emails)} emails. {skipped} already processed, {len(to_process)} to parse.")

        if not to_process:
            _update_demo_run(run_id, status="completed", finished_at=_now_iso())
            _append_demo_log(run_id, "Nothing new to parse.")
            return

        # Route each email: specialized parsers (PayPal/Amazon) vs generic batch
        specialized: list[tuple[int, dict, str, callable]] = []
        generic: list[tuple[int, dict, str | None]] = []

        for i, email in enumerate(to_process):
            email_from = (email.get("from") or "").lower()
            email_subject = (email.get("subject") or "").lower()
            email_body = email.get("body") or ""

            vendor_name = vendor_search(email_from, email_subject, email_body)
            if not vendor_name:
                vendor_name = vendor_regex_search(email_subject, email_body)
            if not vendor_name:
                vendor_name = vendor_from_sender_domain(email_from)

            normalized = normalize_vendor_name(vendor_name, email_data=email) if vendor_name else None

            if normalized == "PayPal":
                specialized.append((i, email, normalized, paypal_parser))
            elif normalized == "Amazon":
                specialized.append((i, email, normalized, amazon_parser))
            else:
                generic.append((i, email, normalized))

        _append_demo_log(run_id, f"Routing: {len(generic)} generic (1 batch AI call), {len(specialized)} specialized.")

        # Parse all emails, collecting results by index
        all_parsed: dict[int, dict | None] = {}

        # Specialized parsers run individually (PayPal/Amazon rarely need AI)
        for i, email, vendor_name, parser_fn in specialized:
            try:
                all_parsed[i] = parser_fn(
                    email.get("subject") or "",
                    email.get("body") or "",
                    email.get("id"),
                    email.get("date"),
                    vendor_name,
                )
            except Exception as e:
                all_parsed[i] = None
                _append_demo_log(run_id, f"Error in specialized parser: {e}")

        # Generic emails: regex on all, then ONE batch AI call for failures
        if generic:
            _append_demo_log(run_id, f"Running regex + batch AI on {len(generic)} generic emails...")
            batch_items = [
                {
                    "email_subject": email.get("subject") or "",
                    "email_text": email.get("body") or "",
                    "email_id": email.get("id"),
                    "email_date": email.get("date"),
                    "vendor_name": vendor_name,
                }
                for _, email, vendor_name in generic
            ]
            batch_results = parse_generic_emails_batch(batch_items)
            for (i, _, _), parsed in zip(generic, batch_results):
                all_parsed[i] = parsed

        # Save results and log per-email outcome
        success = 0
        failed = 0
        processed = skipped

        for i, email in enumerate(to_process):
            parsed = all_parsed.get(i)
            email_id = email.get("id")
            subject = (email.get("subject") or "Demo receipt")[:80]
            processed += 1

            if not parsed or not isinstance(parsed, dict):
                failed += 1
                _append_demo_log(run_id, f"[{i+1}/{len(to_process)}] No result for: {subject}")
                _update_demo_run(run_id, processed=processed, success=success, skipped=skipped, failed=failed)
                continue

            meta = parsed.get("_meta") or {}
            vendor = parsed.get("vendor", "Unknown")
            amount = float(parsed.get("amount") or 0.0)
            vendor_ai_called = bool(meta.get("vendor_ai_called", False))
            amount_ai_called = bool(meta.get("ai_amount_tax_called", False))

            _append_demo_log(
                run_id,
                f"[{i+1}/{len(to_process)}] {subject[:60]} → vendor={vendor}, amount=${amount:.2f}"
            )
            _append_demo_log(
                run_id,
                "AI indicators -> "
                f"vendor_ai_called={vendor_ai_called}, "
                f"vendor_ai_success={bool(meta.get('vendor_ai_success'))}, "
                f"amount_ai_called={amount_ai_called}, "
                f"amount_ai_success={bool(meta.get('ai_amount_found'))}, "
                f"tax_ai_success={bool(meta.get('ai_tax_found'))}"
            )
            if amount_ai_called:
                _append_demo_log(run_id, f"AI amount/tax raw -> {str(meta.get('ai_amount_tax_raw', '')) or '(empty)'}")

            try:
                tx = log_transaction(parsed, user_id=user_id)
                if tx is not None:
                    success += 1
                    if email_id:
                        existing_ids.add(email_id)
                    _append_demo_log(run_id, f"Saved: vendor={vendor}, amount=${amount:.2f}")
                else:
                    failed += 1
                    _append_demo_log(run_id, f"Not saved (zero/duplicate): vendor={vendor}, amount=${amount:.2f}")
            except Exception as row_error:
                failed += 1
                _append_demo_log(run_id, f"Error saving: {row_error}")

            _update_demo_run(run_id, processed=processed, success=success, skipped=skipped, failed=failed)

        _update_demo_run(run_id, status="completed", finished_at=_now_iso())
        _append_demo_log(run_id, f"Run complete. success={success}, skipped={skipped}, failed={failed}")
    except Exception as e:
        _append_demo_log(run_id, f"Run crashed: {e}")
        _update_demo_run(run_id, status="failed", finished_at=_now_iso())

def _generate_demo_emails(count: int = 6):
    """Generate demo receipt emails via Gemini with tax/subtotal/total details."""
    run_nonce = uuid.uuid4().hex[:8]
    prompt = f"""Generate {count} fake receipt emails in JSON array format.
Return ONLY a JSON array with exactly {count} objects and NO extra text.

Each object must include:
- subject
- from
- date (YYYY-MM-DD)
- vendor
- subtotal (number)
- tax (number)
- total (number)
- body

Rules:
1. Choose variety of vendor names. Do not use a fixed repeated list.
2. Ensure Tax==subtotal*.0625
3. Ensure total == subtotal + tax.
4. Make the body messy and realistic: include extra sections like promo text, shipping/tracking, support footer, rewards, partial refunds, and authorization lines.
5. Include at least 5-10 additional dollar values in each body (item prices, discounts, shipping, credits, prior balance, pending charge), so parser must distinguish the true subtotal/tax/total.
6. Do NOT format body as a short clean 5-line summary.
7. For the true amounts section, avoid exact labels like "Tax:" and "Total:"; use less direct wording like "local levy", "merchandise sum", and "balance due now".
8. Keep vendor name present in body, but not always in the sender domain.
9. Create a fresh set of vendors and receipts for this run token: {run_nonce}
"""

    def _safe_float(value, default=0.0):
        try:
            return round(float(value), 2)
        except Exception:
            return round(float(default), 2)

    def _build_messy_body(vendor: str, date: str, subtotal: float, tax: float, total: float, extra: str = "") -> str:
        items = []
        item_count = random.randint(3, 6)
        running = 0.0
        for i in range(item_count):
            price = round(random.uniform(2.5, 45.0), 2)
            qty = random.randint(1, 3)
            line_total = round(price * qty, 2)
            running += line_total
            items.append(f"Item {i+1} x{qty} ............. ${line_total:.2f}")

        shipping = round(random.uniform(0, 12.99), 2)
        discount = round(random.uniform(0, 10.0), 2)
        credit = round(random.uniform(0, 7.5), 2)
        pending = round(random.uniform(1.0, 30.0), 2)
        auth_hold = round(random.uniform(total, total + 25), 2)
        prior_balance = round(random.uniform(0, 80), 2)
        rewards = random.randint(50, 4000)
        noise_note = extra.strip()
        if noise_note:
            noise_note = f"\nCustomer Note Snippet: {noise_note[:220]}"

        return (
            f"Subject Thread: Re: order update / invoice copy / receipt confirmation\n"
            f"Merchant Notice: This receipt may include pending holds and promotional adjustments.\n"
            f"Order Ref: {uuid.uuid4().hex[:10].upper()}  |  Tracking: 1Z{uuid.uuid4().hex[:14].upper()}\n"
            f"----- PAYMENT RECONCILIATION BLOCK -----\n"
            f"Document Date -> {date}\n"
            f"Merchant Legal Name -> {vendor}\n"
            f"Merchandise Sum (USD) -> ${subtotal:.2f}\n"
            f"Local Levy @ 6.25 pct -> ${tax:.2f}\n"
            f"Balance Due Now (final) -> ${total:.2f}\n"
            f"--------------------------------\n"
            f"Auth Hold (temporary): ${auth_hold:.2f}\n"
            f"Pending Charge (not final): ${pending:.2f}\n"
            f"Previous Balance: ${prior_balance:.2f}\n"
            f"Rewards Applied Equivalent: ${credit:.2f} ({rewards} pts)\n"
            f"Promo Banner: Save 15% on next order over $50.00\n"
            f"Line Items:\n- " + "\n- ".join(items) + "\n"
            f"Shipping Est.: ${shipping:.2f}\n"
            f"Coupon / Promo Deduction: -${discount:.2f}\n"
            f"Support Plan Offer: $4.99/mo (not included)\n"
            f"If questions, contact support within 30 days. This message may contain automated text.{noise_note}\n"
        )

    def _build_organized_body(vendor: str, date: str, subtotal: float, tax: float, total: float) -> str:
        templates = [
            (
                f"Receipt Confirmation\n"
                f"Date: {date}\n"
                f"Vendor: {vendor}\n"
                f"Order Summary\n"
                f"Subtotal: ${subtotal:.2f}\n"
                f"Tax: ${tax:.2f}\n"
                f"Total: ${total:.2f}\n"
                f"Thank you for your purchase.\n"
            ),
            (
                f"Payment Receipt\n"
                f"Merchant: {vendor}\n"
                f"Transaction Date: {date}\n"
                f"Summary\n"
                f"Amount Before Tax: ${subtotal:.2f}\n"
                f"Sales Tax: ${tax:.2f}\n"
                f"Amount Charged: ${total:.2f}\n"
                f"We appreciate your business.\n"
            ),
            (
                f"Invoice Paid\n"
                f"From: {vendor}\n"
                f"Email Date: {date}\n"
                f"Charges\n"
                f"Merchandise Total: ${subtotal:.2f}\n"
                f"Tax Amount: ${tax:.2f}\n"
                f"Grand Total: ${total:.2f}\n"
                f"Keep this email for your records.\n"
            ),
            (
                f"Order Receipt\n"
                f"Store: {vendor}\n"
                f"Date: {date}\n"
                f"Breakdown\n"
                f"Subtotal Amount: ${subtotal:.2f}\n"
                f"Tax Collected: ${tax:.2f}\n"
                f"Total Paid: ${total:.2f}\n"
                f"Status: Completed\n"
            ),
            (
                f"Purchase Confirmation\n"
                f"Vendor: {vendor}\n"
                f"Processed On: {date}\n"
                f"Receipt Details\n"
                f"Items Subtotal: ${subtotal:.2f}\n"
                f"Tax: ${tax:.2f}\n"
                f"Final Charge: ${total:.2f}\n"
                f"Thanks for shopping with us.\n"
            ),
        ]
        return random.choice(templates)

    def _normalize_demo_rows(rows):
        out = []
        for item in rows:
            if not isinstance(item, dict):
                continue
            vendor = (item.get("vendor") or "").strip() or f"Vendor {uuid.uuid4().hex[:6]}"
            subtotal = _safe_float(item.get("subtotal"), random.uniform(6, 120))
            tax = round(subtotal * 0.0625, 2)
            total = round(subtotal + tax, 2)

            date = item.get("date")
            if not date:
                days_ago = random.randint(0, 30)
                date = (datetime.utcnow() - timedelta(days=days_ago)).strftime("%Y-%m-%d")

            sender = (item.get("from") or "").strip()
            if not sender:
                sender = f"notification-{uuid.uuid4().hex[:6]}@billing-updates.net"

            subject = (item.get("subject") or "").strip() or f"Your receipt from {vendor}"
            source_body = (item.get("body") or "").strip()
            clean_target = min(5, count)
            use_messy = len(out) >= clean_target
            body = _build_messy_body(vendor, date, subtotal, tax, total, source_body) if use_messy else _build_organized_body(vendor, date, subtotal, tax, total)
            out.append({
                "subject": subject,
                "from": sender,
                "date": date,
                "vendor": vendor,
                "subtotal": subtotal,
                "tax": tax,
                "total": total,
                "body": body,
            })
            if len(out) >= count:
                break
        return out

    last_error = None
    for _ in range(2):
        try:
            text = generate_text(
                prompt,
                temperature=0.8,
                max_output_tokens=2400,
            )
            match = re.search(r'\[.*\]', text, re.DOTALL)
            if not match:
                last_error = "No JSON array found in model output"
                continue
            data = json.loads(match.group(0))
            if isinstance(data, list) and data:
                normalized = _normalize_demo_rows(data)
                if normalized:
                    return normalized
            last_error = "Model returned empty/invalid list"
        except Exception as e:
            last_error = str(e)
            continue

    print(f"⚠️ Demo generation failed, using realistic fallback: {last_error}")

    # Real-world fallback vendor pool (used only when AI generation fails).
    fallback_vendors = [
        "Target", "Walmart", "Costco", "Best Buy", "Home Depot", "Lowe's",
        "Kroger", "Safeway", "Whole Foods Market", "Trader Joe's", "CVS Pharmacy",
        "Walgreens", "Starbucks", "Dunkin'", "Chipotle", "McDonald's", "Subway",
        "Panera Bread", "Domino's", "Pizza Hut", "Uber", "Lyft", "Airbnb",
        "Delta Air Lines", "United Airlines", "American Airlines", "Marriott",
        "Hilton", "Amazon", "Etsy", "eBay", "Apple", "Microsoft", "Google Store",
        "AT&T", "Verizon", "T-Mobile", "Netflix", "Spotify", "Adobe",
    ]

    def _sender_from_vendor(vendor_name: str) -> str:
        return f"notification-{uuid.uuid4().hex[:6]}@billing-updates.net"

    out = []
    sampled_vendors = random.sample(fallback_vendors, k=min(count, len(fallback_vendors)))
    while len(sampled_vendors) < count:
        sampled_vendors.append(random.choice(fallback_vendors))
    clean_target = min(5, count)
    for i in range(count):
        vendor = sampled_vendors[i]
        subtotal = round(random.uniform(8, 160), 2)
        tax = round(subtotal * 0.0625, 2)
        total = round(subtotal + tax, 2)
        days_ago = random.randint(0, 30)
        date = (datetime.utcnow() - timedelta(days=days_ago)).strftime("%Y-%m-%d")
        out.append({
            "subject": f"Your receipt from {vendor}",
            "from": _sender_from_vendor(vendor),
            "date": date,
            "vendor": vendor,
            "subtotal": subtotal,
            "tax": tax,
            "total": total,
            "body": _build_messy_body(vendor, date, subtotal, tax, total) if i >= clean_target else _build_organized_body(vendor, date, subtotal, tax, total),
        })
    return out

def _print_db_snapshot(limit: int = 50, user_id: str | int | None = None):
    """Print a snapshot of the latest transactions (date, vendor, amount)."""
    rows = get_all_transactions(user_id=user_id)[:limit]
    print("🧾 DB Snapshot (latest transactions):")
    if not rows:
        print("  (no rows found)")
        return
    for t in reversed(rows):
        date = t.date.strftime('%Y-%m-%d') if hasattr(t.date, "strftime") else str(t.date)
        vendor = (t.vendor or "Unknown").strip()
        amount = t.amount if t.amount is not None else 0
        print(f"  {date} | {vendor} | ${float(amount):.2f}")

@app.post("/api/sync")
def sync_emails(request: Request, payload: dict = Body(default={})):
    """Start email scraper in background; returns a run_id for progress polling."""
    user = _require_user(request)
    if not _get_google_refresh_token_for_user(user.id):
        raise HTTPException(status_code=400, detail="Google OAuth not connected for this user.")
    date_from = payload.get("date_from")
    date_to   = payload.get("date_to")
    try:
        run_id = uuid.uuid4().hex
        with SYNC_LOCK:
            SYNC_RUNS[run_id] = {
                "run_id": run_id,
                "user_id": user.id,
                "status": "queued",
                "message": "Queued…",
                "logs": [],
                "started_at": _now_iso(),
                "updated_at": _now_iso(),
                "cancelled": False,
            }
        thread = threading.Thread(target=_run_sync, args=(user.id, run_id, date_from, date_to), daemon=True)
        thread.start()
        return {"status": "success", "run_id": run_id, "message": "Sync started."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Sync failed to start: {str(e)}")

@app.post("/api/sync-stop")
def sync_stop(request: Request, payload: dict = Body(default={})):
    _require_user(request)
    run_id = payload.get("run_id")
    if run_id:
        with SYNC_LOCK:
            if run_id in SYNC_RUNS:
                SYNC_RUNS[run_id]["cancelled"] = True
    return {"status": "ok"}

@app.get("/api/sync-status")
def sync_status(request: Request, run_id: str):
    """Poll sync progress for a run started by /api/sync."""
    user = _require_user(request)
    with SYNC_LOCK:
        run = SYNC_RUNS.get(run_id)
    if not run or run.get("user_id") != user.id:
        raise HTTPException(status_code=404, detail="Run not found")
    return run

@app.post("/api/demo-sync")
def demo_sync(request: Request):
    """Generate demo emails with AI, parse them, and store transactions."""
    try:
        demo_user = _get_demo_user()
        from .parser_select import parser_select
        from .data_helper import get_existing_email_ids, log_transaction
        emails = _generate_demo_emails(10)
        demo_rows = _prepare_demo_emails(emails)
        existing_ids = get_existing_email_ids(user_id=demo_user.id)
        for email in demo_rows:
            email_id = email.get("id")
            if email_id in existing_ids:
                continue
            try:
                parsed = parser_select(email)
                if parsed and isinstance(parsed, dict):
                    saved = log_transaction(parsed, user_id=demo_user.id)
                    if saved is not None:
                        existing_ids.add(email_id)
            except Exception as row_error:
                print(f"⚠️ Demo parse failed for {email_id}: {row_error}")
                continue

        _demo_emails_path().write_text(json.dumps(demo_rows, indent=2))
        return {"status": "success", "count": len(demo_rows)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Demo sync failed: {e}")

@app.post("/api/demo-generate")
def demo_generate(request: Request):
    """Generate demo emails only (no parsing)."""
    try:
        emails = _generate_demo_emails(10)
        demo_rows = _prepare_demo_emails(emails)
        _demo_emails_path().write_text(json.dumps(demo_rows, indent=2))
        return {"status": "success", "count": len(demo_rows)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Demo generation failed: {e}")

@app.post("/api/demo-parse")
def demo_parse(request: Request, force_reprocess: bool = False):
    """Parse existing demo emails in background and expose progress logs."""
    try:
        demo_user = _get_demo_user()
        run_id = uuid.uuid4().hex
        _init_demo_run(run_id, user_id=demo_user.id, force_reprocess=force_reprocess)
        thread = threading.Thread(target=_run_demo_parse, args=(run_id, demo_user.id, force_reprocess), daemon=True)
        thread.start()
        return {"status": "started", "run_id": run_id}
    except Exception as e:
        err = str(e)
        if "403" in err or "insufficient permissions" in err.lower():
            raise HTTPException(
                status_code=500,
                detail="Demo is unavailable: the server's Firestore service account lacks the required permissions. Check that the Firebase service account has the 'Cloud Datastore User' IAM role."
            )
        raise HTTPException(status_code=500, detail=f"Demo parse failed to start: {e}")

@app.get("/api/demo-parse-status")
def demo_parse_status(request: Request, run_id: str):
    demo_user = _get_demo_user()
    run = _get_demo_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    if run.get("user_id") != demo_user.id:
        raise HTTPException(status_code=404, detail="Run not found")
    return run

@app.get("/api/demo-emails")
def demo_emails(request: Request):
    """Return last generated demo emails."""
    path = _demo_emails_path()
    if not path.exists():
        return []
    try:
        return json.loads(path.read_text())
    except Exception:
        return []

@app.get("/api/demo/transactions")
def get_demo_transactions(request: Request):
    """Get demo transactions (shared demo user)."""
    demo_user = _get_demo_user()
    transactions = get_all_transactions(user_id=demo_user.id)
    transactions = _nonzero_transactions(transactions)
    return [
        {
            "id": t.id,
            "date": t.date.strftime('%Y-%m-%d') if isinstance(t.date, datetime) else str(t.date),
            "vendor": t.vendor or "Unknown",
            "amount": float(t.amount) if t.amount else 0.0,
            "tax": float(t.tax) if t.tax else 0.0,
            "email_id": t.email_id,
            "category": t.category,
            "payment_method": t.payment_method,
            "items": t.items,
            "email_body": t.email_body,
        }
        for t in transactions
    ]

@app.get("/api/demo/stats")
def get_demo_stats(request: Request):
    """Get demo stats (shared demo user)."""
    demo_user = _get_demo_user()
    transactions = _nonzero_transactions(get_all_transactions(user_id=demo_user.id))
    total_spent = sum(t.amount for t in transactions if t.amount)
    total_receipts = len(transactions)
    unique_vendors = len(set(t.vendor for t in transactions if t.vendor))
    avg_transaction = total_spent / total_receipts if total_receipts > 0 else 0
    return {
        "total_spent": round(total_spent, 2),
        "total_receipts": total_receipts,
        "unique_vendors": unique_vendors,
        "avg_transaction": round(avg_transaction, 2)
    }

@app.get("/api/demo/top-vendors")
def get_demo_top_vendors(request: Request):
    """Get top demo vendors by spending (shared demo user)."""
    demo_user = _get_demo_user()
    transactions = _nonzero_transactions(get_all_transactions(user_id=demo_user.id))
    vendor_totals = {}
    vendor_counts = {}
    for t in transactions:
        vendor = t.vendor or "Unknown"
        amount = t.amount or 0
        if vendor not in vendor_totals:
            vendor_totals[vendor] = 0
            vendor_counts[vendor] = 0
        vendor_totals[vendor] += amount
        vendor_counts[vendor] += 1
    top_vendors = sorted(vendor_totals.items(), key=lambda x: x[1], reverse=True)[:4]
    return [
        {
            "vendor": vendor,
            "total": round(amount, 2),
            "count": vendor_counts[vendor]
        }
        for vendor, amount in top_vendors
    ]

@app.delete("/api/demo/clear")
def clear_demo_transactions(request: Request):
    """Clear all demo transactions."""
    demo_user = _get_demo_user()
    deleted = clear_transactions_for_user(demo_user.id)
    return {"status": "success", "deleted": deleted}

@app.put("/api/demo/transactions/{transaction_id}")
def update_demo_transaction(transaction_id: str, payload: dict = Body(...)):
    """Update a demo transaction without auth."""
    demo_user = _get_demo_user()
    try:
        tx = update_transaction_for_user(str(transaction_id), payload, demo_user.id)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    if not tx:
        raise HTTPException(status_code=404, detail="Transaction not found")
    return {"status": "success", "id": tx.id}

@app.delete("/api/demo/transactions/{transaction_id}")
def delete_demo_transaction(transaction_id: str):
    """Delete a demo transaction without auth."""
    demo_user = _get_demo_user()
    deleted = delete_transaction_for_user(str(transaction_id), demo_user.id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Transaction not found")
    return {"status": "success", "id": str(transaction_id)}

@app.delete("/api/transactions/clear")
@app.post("/api/transactions/clear")
def clear_transactions(request: Request):
    """Delete all transactions for the current user."""
    user = _require_user(request)
    deleted = clear_transactions_for_user(user.id)
    return {"status": "success", "deleted": deleted}

@app.post("/api/vendor-pie")
async def vendor_pie(request: Request):
    """Generate a vendor spend pie chart from CSV body."""
    try:
        raw = await request.body()
        csv_text = raw.decode("utf-8", errors="ignore")
        if not csv_text.strip():
            raise HTTPException(status_code=400, detail="CSV body is empty")

        df = pd.read_csv(StringIO(csv_text))
        if df.empty:
            raise HTTPException(status_code=400, detail="CSV contains no rows")

        cols = {c.lower().strip(): c for c in df.columns}
        vendor_col = cols.get("vendor")
        amount_col = cols.get("amount")
        if not vendor_col or not amount_col:
            raise HTTPException(status_code=400, detail="CSV must include Vendor and Amount columns")

        amounts = (
            df[amount_col]
            .astype(str)
            .str.replace("$", "", regex=False)
            .str.replace(",", "", regex=False)
        )
        df["_amount"] = pd.to_numeric(amounts, errors="coerce")
        df = df.dropna(subset=["_amount"])
        df = df[df["_amount"] > 0]
        if df.empty:
            raise HTTPException(status_code=400, detail="No positive amounts to chart")

        grouped = df.groupby(vendor_col)["_amount"].sum().sort_values(ascending=False)
        totals = grouped.to_dict()
        total_sum = sum(totals.values())
        breakdown = [
            {"vendor": k, "total": float(v), "percent": float(v / total_sum * 100)}
            for k, v in totals.items()
        ]

        # Keep colors deterministic so legend matches chart
        palette = [
            "#ef4444", "#f97316", "#f59e0b", "#84cc16", "#10b981",
            "#14b8a6", "#06b6d4", "#0ea5e9", "#6366f1", "#8b5cf6",
            "#d946ef", "#ec4899",
        ]
        labels = list(totals.keys())
        values = list(totals.values())
        colors = [palette[i % len(palette)] for i in range(len(labels))]

        fig, ax = plt.subplots(figsize=(5, 5), dpi=150)
        ax.pie(
            values,
            labels=labels,
            colors=colors,
            autopct="%1.1f%%",
            startangle=90,
            textprops={"fontsize": 8},
        )
        ax.axis("equal")
        buf = BytesIO()
        fig.savefig(buf, format="png", bbox_inches="tight")
        plt.close(fig)
        buf.seek(0)
        image_b64 = base64.b64encode(buf.read()).decode("ascii")

        return {"image_base64": image_b64, "breakdown": breakdown, "colors": colors}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Chart generation failed: {e}")

@app.put("/api/transactions/{transaction_id}")
def update_transaction(request: Request, transaction_id: str, payload: dict = Body(...)):
    """Update a transaction's vendor, amount, tax, date, or category."""
    user = _require_user(request)
    try:
        tx = update_transaction_for_user(str(transaction_id), payload, user.id)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    if not tx:
        raise HTTPException(status_code=404, detail="Transaction not found")
    return {"status": "success", "id": tx.id}

@app.delete("/api/transactions/{transaction_id}")
def delete_transaction(request: Request, transaction_id: str):
    """Delete a transaction by ID."""
    user = _require_user(request)
    deleted = delete_transaction_for_user(str(transaction_id), user.id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Transaction not found")
    return {"status": "success", "id": str(transaction_id)}

def _build_spend_summary(transactions) -> str:
    """Build aggregated spend summary for the advisor — no raw email content or IDs."""
    if not transactions:
        return "No transaction data available yet. The user has not synced any receipts."

    now = datetime.utcnow()
    this_month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    last_month_end = this_month_start
    last_month_start = (this_month_start - timedelta(days=1)).replace(day=1)

    total_all = 0.0
    this_month_total = 0.0
    last_month_total = 0.0
    cat_totals: dict = defaultdict(float)
    vendor_totals: dict = defaultdict(float)
    monthly_totals: dict = defaultdict(float)
    valid_count = 0

    for t in transactions:
        amt = float(t.amount or 0)
        if amt <= 0:
            continue
        valid_count += 1
        total_all += amt

        date = t.date
        if date and isinstance(date, str):
            try:
                date = date_parser.parse(date)
            except Exception:
                date = None

        if date:
            if date >= this_month_start:
                this_month_total += amt
            if last_month_start <= date < last_month_end:
                last_month_total += amt
            key = date.strftime('%b %Y')
            monthly_totals[key] += amt

        cat = (getattr(t, 'category', None) or 'Uncategorized').strip()
        cat_totals[cat] += amt
        vendor = (getattr(t, 'vendor', None) or 'Unknown').strip()
        vendor_totals[vendor] += amt

    avg = total_all / valid_count if valid_count else 0
    top_cats = sorted(cat_totals.items(), key=lambda x: -x[1])[:8]
    top_vendors = sorted(vendor_totals.items(), key=lambda x: -x[1])[:6]
    recent_months = sorted(monthly_totals.items())[-6:]

    lines = [
        f"Total transactions: {valid_count}",
        f"All-time total spend: ${total_all:.2f}",
        f"This month: ${this_month_total:.2f}",
        f"Last month: ${last_month_total:.2f}",
        f"Average transaction: ${avg:.2f}",
        "",
        "Spending by category:",
    ]
    for cat, amt in top_cats:
        pct = (amt / total_all * 100) if total_all else 0
        lines.append(f"  {cat}: ${amt:.2f} ({pct:.1f}%)")
    lines += ["", "Top vendors:"]
    for vendor, amt in top_vendors:
        lines.append(f"  {vendor}: ${amt:.2f}")
    if recent_months:
        lines += ["", "Monthly trend (recent months):"]
        for month, amt in recent_months:
            lines.append(f"  {month}: ${amt:.2f}")
    return "\n".join(lines)


@app.post("/api/advisor/chat")
def advisor_chat(request: Request, body: dict = Body(...)):
    """AI financial advisor. Uses aggregated spend data only — no raw email content."""
    user = _require_user(request)
    message = (body.get("message") or "").strip()
    history = body.get("history") or []

    if not message:
        raise HTTPException(status_code=400, detail="Message is required.")
    if len(message) > 2000:
        raise HTTPException(status_code=400, detail="Message too long.")

    transactions = get_all_transactions(user_id=user.id)
    spend_summary = _build_spend_summary(transactions)

    history_text = ""
    for turn in history[-8:]:
        role = turn.get("role", "")
        content = (turn.get("content") or "").strip()[:800]
        if role == "user":
            history_text += f"\nUser: {content}"
        elif role == "assistant":
            history_text += f"\nAdvisor: {content}"

    prompt = f"""You are "RA Advisor", a friendly personal finance helper inside ReceiptAuto. You are NOT a licensed financial advisor — always make this clear when giving advice.

The user's spending summary (aggregated, no private identifiers):
{spend_summary}

YOUR SCOPE — only respond to:
- Budgeting, spending reduction, tracking habits
- Emergency fund building
- Saving strategies (high-yield savings, CDs, I-bonds)
- Retirement accounts (Roth IRA, Traditional IRA, 401k, 403b, SEP-IRA)
- Passive investing basics (index funds, ETFs, asset allocation)
- Debt payoff strategies (avalanche, snowball, consolidation)
- Housing basics (rent vs buy, down payment planning, mortgage concepts)
- General personal finance education and money mindset

OUT OF SCOPE — politely decline and redirect if asked about:
- Specific stock picks, options trading, crypto speculation
- Tax filing or legal advice
- Medical or insurance decisions
- Anything unrelated to personal finance
- Technical questions about ReceiptAuto

PRIVACY — never repeat raw transaction details verbatim. Reference spending patterns and categories to give personalized advice, but keep responses focused on actionable guidance.

FORMAT — be concise, warm, and practical. Use bullet points for action steps. Keep responses under 250 words. End with a short disclaimer line.
{history_text}
User: {message}
Advisor:"""

    try:
        response_text = generate_text(
            prompt,
            temperature=0.72,
            max_output_tokens=512,
            model=settings.gemini_model,
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=f"AI service unavailable: {exc}")

    return {"response": response_text, "status": "success"}


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)

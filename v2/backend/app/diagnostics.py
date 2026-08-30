"""Startup and on-demand readiness checks.

Every dependency here fails softly at runtime, no Gemini key means rules-only
parsing, no Firestore means the JSON store, so a silent misconfiguration is
easy to miss. This module makes the current state explicit, without printing
any secret value.
"""
from __future__ import annotations

import asyncio
from typing import Any
from urllib.parse import urlparse

from . import llm
from .config import settings
from .store import firestore_client, repository

OK, WARN, FAIL = "ok", "warning", "error"


def _check(name: str, status: str, detail: str, fix: str = "") -> dict[str, Any]:
    return {"name": name, "status": status, "detail": detail, "fix": fix}


async def _firestore() -> dict[str, Any]:
    if not firestore_client.configured():
        return _check(
            "Firestore",
            WARN,
            "Not configured, receipts are stored in backend/data/transactions.json",
            "Set FIREBASE_PROJECT_ID and FIREBASE_SERVICE_ACCOUNT_JSON (or _PATH) in .env",
        )

    def _probe() -> str:
        db = firestore_client.client()
        list(db.collection(settings.firebase_transactions_collection).limit(1).stream())
        return firestore_client.credential_source()

    try:
        source = await asyncio.to_thread(_probe)
        return _check("Firestore", OK, f"Connected to {settings.firebase_project_id} via {source}")
    except Exception as exc:  # noqa: BLE001
        return _check("Firestore", FAIL, f"Configured but unreachable: {type(exc).__name__}: {exc}",
                      "Check the service account has Cloud Datastore User on this project")


async def _gemini() -> dict[str, Any]:
    if not llm.available():
        return _check(
            "Gemini",
            WARN,
            "No API key, parsing runs on rules alone (vendors resolve, awkward totals do not)",
            "Set GOOGLE_API_KEY in .env",
        )
    try:
        verdict = await asyncio.wait_for(
            llm.TRIAGE.submit(
                {"sender": "receipts@starbucks.com", "subject": "Your receipt", "snippet": "Total: $4.15"}
            ),
            timeout=45,
        )
        if verdict is None:
            return _check("Gemini", WARN, f"{settings.gemini_model} answered but the response did not parse")
        return _check("Gemini", OK, f"{settings.gemini_model} responding")
    except Exception as exc:  # noqa: BLE001
        return _check("Gemini", FAIL, f"{settings.gemini_model} unreachable: {type(exc).__name__}: {exc}",
                      "Verify GOOGLE_API_KEY and that the model name exists for your key")


def _oauth(serving_port: int | None) -> list[dict[str, Any]]:
    checks = []
    if not (settings.google_oauth_client_id and settings.google_oauth_client_secret):
        checks.append(_check("Google OAuth", FAIL, "Client id or secret missing. Gmail cannot be connected",
                             "Set GOOGLE_OAUTH_CLIENT_ID and GOOGLE_OAUTH_CLIENT_SECRET in .env"))
        return checks

    redirect = settings.google_oauth_redirect_uri or ""
    parsed = urlparse(redirect)
    if not parsed.scheme or not parsed.netloc:
        checks.append(_check("Redirect URI", FAIL, "GOOGLE_OAUTH_REDIRECT_URI is not a URL",
                             "Set it to http://localhost:<api port>/api/google/callback"))
        return checks

    if not parsed.path.endswith("/api/google/callback"):
        checks.append(_check("Redirect URI", FAIL, f"Path is {parsed.path}; v2 serves the callback at /api/google/callback",
                             f"Change it to {parsed.scheme}://{parsed.netloc}/api/google/callback"))
    elif serving_port and parsed.port and parsed.port != serving_port:
        checks.append(_check(
            "Redirect URI", WARN,
            f"Registered for port {parsed.port} but the API is serving on {serving_port}",
            f"Either run the API on {parsed.port}, or add "
            f"http://localhost:{serving_port}/api/google/callback to the OAuth client "
            f"in Google Cloud Console and point GOOGLE_OAUTH_REDIRECT_URI at it",
        ))
    else:
        checks.append(_check("Google OAuth", OK, f"Callback registered at {redirect}"))
    return checks


def _fernet() -> dict[str, Any]:
    key = (settings.fernet_key or "").strip()
    if not key:
        return _check("Token encryption", FAIL, "FERNET_KEY is not set. Gmail cannot be connected",
                      'Generate one: python3 -c "from cryptography.fernet import Fernet; '
                      'print(Fernet.generate_key().decode())"')
    try:
        from cryptography.fernet import Fernet

        probe = Fernet(key.encode())
        assert probe.decrypt(probe.encrypt(b"ok")) == b"ok"
        return _check("Token encryption", OK, "FERNET_KEY is valid")
    except Exception:  # noqa: BLE001
        return _check("Token encryption", FAIL, "FERNET_KEY is set but not a valid Fernet key",
                      "Regenerate it; note that existing stored tokens will need reconnecting")


async def report(serving_port: int | None = None) -> dict[str, Any]:
    checks = [
        _check("Storage", OK, f"Using the {repository.describe()} backend"),
        await _firestore(),
        await _gemini(),
        _fernet(),
        *_oauth(serving_port),
    ]
    worst = FAIL if any(c["status"] == FAIL for c in checks) else (
        WARN if any(c["status"] == WARN for c in checks) else OK
    )
    return {"status": worst, "environment": settings.app_env, "checks": checks}

"""One place that knows how to reach Firestore.

Three credential paths, checked in order:

1. `FIRESTORE_EMULATOR_HOST`, local emulator, anonymous credentials. This is
   what the integration test uses, so the Firestore code path is exercised on
   every run without anyone's service-account key.
2. An explicit service account (`FIREBASE_SERVICE_ACCOUNT_JSON` inline, or
   `FIREBASE_SERVICE_ACCOUNT_PATH` on disk).
3. Application Default Credentials, for Cloud Run / GCE deployments.

Collections match v1's layout, so both versions read the same data.
"""
from __future__ import annotations

import json
import os
import threading
from typing import Optional

from ..config import ROOT, settings

_client = None
_lock = threading.Lock()


def _service_account_info() -> Optional[dict]:
    """Return the service-account dict, however it was supplied.

    `.env` files cannot hold a pretty-printed JSON blob: dotenv stops at the
    first newline, so `FIREBASE_SERVICE_ACCOUNT_JSON={` is all that survives.
    v1 hit this too and silently fell back to SQLite. Rather than ask anyone to
    re-flatten their key, read the raw file and take the whole brace-balanced
    block. Nothing is logged or written back.
    """
    raw = (settings.firebase_service_account_json or "").strip()
    if raw.startswith("{") and len(raw) > 2:
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            pass

    if settings.firebase_service_account_path:
        try:
            with open(settings.firebase_service_account_path) as handle:
                return json.load(handle)
        except (OSError, json.JSONDecodeError):
            pass

    for candidate in (ROOT / ".env", ROOT / "v2" / ".env"):
        block = _read_multiline_env(candidate, "FIREBASE_SERVICE_ACCOUNT_JSON")
        if block:
            try:
                return json.loads(block)
            except json.JSONDecodeError:
                continue
    return None


def _read_multiline_env(path, key: str) -> Optional[str]:
    try:
        with open(path) as handle:
            lines = handle.read().splitlines()
    except OSError:
        return None

    prefix = f"{key.lower()}="
    for index, line in enumerate(lines):
        # Env keys are case-insensitive, and this one is commonly written
        # FIREBASE_SERVICE_ACCOUNT_json by the Firebase console copy button.
        if not line.lower().startswith(prefix):
            continue
        collected = line.split("=", 1)[1].strip().strip("'\"")
        if not collected.startswith("{"):
            return None
        depth = collected.count("{") - collected.count("}")
        for follow in lines[index + 1 :]:
            collected += "\n" + follow
            depth += follow.count("{") - follow.count("}")
            if depth <= 0:
                break
        return collected.strip().strip("'\"")
    return None


def emulator_host() -> Optional[str]:
    return os.getenv("FIRESTORE_EMULATOR_HOST") or None


def configured() -> bool:
    """True when Firestore can actually be reached, not merely named."""
    if not settings.firebase_project_id:
        return False
    if emulator_host() or os.getenv("GOOGLE_APPLICATION_CREDENTIALS"):
        return True
    return _service_account_info() is not None


def credential_source() -> str:
    if emulator_host():
        return f"emulator at {emulator_host()}"
    info = _service_account_info()
    if info:
        return f"service account {info.get('client_email', 'unknown')}"
    if os.getenv("GOOGLE_APPLICATION_CREDENTIALS"):
        return "GOOGLE_APPLICATION_CREDENTIALS"
    return "none"


def build_client():
    from google.cloud import firestore

    project = settings.firebase_project_id

    if emulator_host():
        from google.auth.credentials import AnonymousCredentials

        return firestore.Client(project=project, credentials=AnonymousCredentials())

    info = _service_account_info()
    if info:
        return firestore.Client.from_service_account_info(info, project=project or info.get("project_id"))

    return firestore.Client(project=project)


def client():
    global _client
    if _client is None:
        with _lock:
            if _client is None:
                _client = build_client()
    return _client


def reset() -> None:
    """Drop the cached client, used by tests that switch backends."""
    global _client
    _client = None

from __future__ import annotations

import asyncio
import json
import secrets
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Body, Cookie, HTTPException, Query, Request, Response
from fastapi.responses import RedirectResponse, StreamingResponse

from .. import auth, llm, sync
from ..config import settings
from ..graph.state import Email
from ..ingest import gmail
from ..store import repository

router = APIRouter(prefix="/api")

_oauth_states: dict[str, float] = {}
OAUTH_SCOPES = ["https://www.googleapis.com/auth/gmail.readonly", "openid", "email"]


async def _require_user(session: Optional[str]) -> dict:
    user = await auth.resolve_session(session)
    if not user:
        raise HTTPException(status_code=401, detail="Not signed in")
    return user


# ── session ─────────────────────────────────────────────────────────────────

@router.get("/session")
async def session_info(receipts_session: Optional[str] = Cookie(default=None)):
    user = await auth.resolve_session(receipts_session)
    return {
        "signed_in": bool(user),
        "email": (user or {}).get("email"),
        "gmail_connected": bool((user or {}).get("gmail_connected")),
        "model_configured": llm.available(),
        "storage": repository.describe(),
        "linked_legacy_accounts": max(len((user or {}).get("user_ids") or []) - 1, 0),
    }


@router.post("/session/end")
async def sign_out(response: Response, receipts_session: Optional[str] = Cookie(default=None)):
    await auth.end_session(receipts_session)
    response.delete_cookie(auth.SESSION_COOKIE, path="/")
    return {"signed_in": False}


# ── google oauth ────────────────────────────────────────────────────────────

def _oauth_flow(state: Optional[str] = None):
    from google_auth_oauthlib.flow import Flow

    if not (settings.google_oauth_client_id and settings.google_oauth_client_secret):
        raise HTTPException(status_code=503, detail="Google OAuth is not configured on this server")
    return Flow.from_client_config(
        {
            "web": {
                "client_id": settings.google_oauth_client_id,
                "client_secret": settings.google_oauth_client_secret,
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
                "redirect_uris": [settings.google_oauth_redirect_uri],
            }
        },
        scopes=OAUTH_SCOPES,
        state=state,
        redirect_uri=settings.google_oauth_redirect_uri,
    )


@router.get("/google/auth-url")
async def google_auth_url():
    state = secrets.token_urlsafe(24)
    now = datetime.now(timezone.utc).timestamp()
    _oauth_states[state] = now
    for old, issued in list(_oauth_states.items()):
        if now - issued > 900:
            _oauth_states.pop(old, None)

    url, _ = _oauth_flow(state).authorization_url(
        access_type="offline", include_granted_scopes="true", prompt="consent"
    )
    return {"url": url}


@router.get("/google/callback")
async def google_callback(code: Optional[str] = None, state: Optional[str] = None, error: Optional[str] = None):
    frontend = settings.frontend_url.rstrip("/")
    if error or not code or not state or _oauth_states.pop(state, None) is None:
        return RedirectResponse(f"{frontend}/?connect=failed")

    flow = _oauth_flow(state)
    await asyncio.to_thread(flow.fetch_token, code=code)
    credentials = flow.credentials
    if not credentials.refresh_token:
        return RedirectResponse(f"{frontend}/?connect=no_refresh_token")

    email = await gmail.profile_email(credentials.refresh_token) or "unknown@gmail.com"
    token = await auth.link_google_account(email, credentials.refresh_token)

    response = RedirectResponse(f"{frontend}/?connect=ok")
    response.set_cookie(
        auth.SESSION_COOKIE,
        token,
        max_age=int(auth.SESSION_TTL.total_seconds()),
        httponly=True,
        samesite="lax",
        secure=settings.app_env != "development",
        path="/",
    )
    return response


@router.post("/google/disconnect")
async def google_disconnect(receipts_session: Optional[str] = Cookie(default=None)):
    user = await _require_user(receipts_session)
    await auth.disconnect_google(user["user_id"])
    return {"gmail_connected": False}


# ── syncing ─────────────────────────────────────────────────────────────────

@router.post("/sync")
async def start_sync(
    payload: dict = Body(default={}),
    receipts_session: Optional[str] = Cookie(default=None),
):
    user = await _require_user(receipts_session)
    run = sync.start(
        user["user_id"],
        user_ids=user["user_ids"],
        max_results=int(payload.get("max_results", 50)),
        days_back=int(payload.get("days_back", 180)),
        date_from=payload.get("date_from"),
        date_to=payload.get("date_to"),
    )
    return run.snapshot()


@router.post("/sync/{run_id}/stop")
async def stop_sync(run_id: str, receipts_session: Optional[str] = Cookie(default=None)):
    user = await _require_user(receipts_session)
    run = sync.get_run(run_id)
    if not run or run.user_id != user["user_id"]:
        raise HTTPException(status_code=404, detail="No such run")
    run.cancel()
    return run.snapshot()


@router.get("/sync/{run_id}/events")
async def sync_events(run_id: str, receipts_session: Optional[str] = Cookie(default=None)):
    user = await _require_user(receipts_session)
    run = sync.get_run(run_id)
    if not run or run.user_id != user["user_id"]:
        raise HTTPException(status_code=404, detail="No such run")

    async def event_stream():
        async for event in sync.stream(run):
            yield f"data: {json.dumps(event, default=str)}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ── transactions ────────────────────────────────────────────────────────────

@router.get("/transactions")
async def list_transactions(
    receipts_session: Optional[str] = Cookie(default=None),
    status: Optional[str] = Query(default=None),
    vendor: Optional[str] = Query(default=None),
    category: Optional[str] = Query(default=None),
    search: Optional[str] = Query(default=None),
):
    user = await _require_user(receipts_session)
    rows = await repository.list_records(user["user_ids"])
    if status:
        rows = [r for r in rows if r.get("status") == status]
    if vendor:
        rows = [r for r in rows if (r.get("vendor") or "").lower() == vendor.lower()]
    if category:
        rows = [r for r in rows if (r.get("category") or "") == category]
    if search:
        needle = search.lower()
        rows = [r for r in rows if needle in json.dumps(r, default=str).lower()]
    return {"transactions": rows}


@router.patch("/transactions/{record_id}")
async def edit_transaction(
    record_id: str,
    payload: dict = Body(...),
    receipts_session: Optional[str] = Cookie(default=None),
):
    user = await _require_user(receipts_session)
    allowed = {"vendor", "amount", "tax", "date", "category", "payment_method", "status", "order_number"}
    patch = {k: v for k, v in payload.items() if k in allowed}
    if not patch:
        raise HTTPException(status_code=400, detail="Nothing to update")
    for field in ("amount", "tax"):
        if field in patch and patch[field] is not None:
            try:
                patch[field] = round(float(patch[field]), 2)
            except (TypeError, ValueError):
                raise HTTPException(status_code=400, detail=f"{field} must be a number")
    # A human edit is ground truth; stop showing the record as unresolved.
    if patch.keys() & {"vendor", "amount"} and "status" not in patch:
        patch["status"] = "parsed"
        patch["confidence"] = 1.0
        patch["issues"] = []

    updated = await repository.update(user["user_id"], record_id, patch)
    if not updated:
        raise HTTPException(status_code=404, detail="No such transaction")
    return updated


@router.delete("/transactions/{record_id}")
async def remove_transaction(record_id: str, receipts_session: Optional[str] = Cookie(default=None)):
    user = await _require_user(receipts_session)
    if not await repository.delete(user["user_id"], record_id):
        raise HTTPException(status_code=404, detail="No such transaction")
    return {"deleted": record_id}


@router.get("/stats")
async def stats(receipts_session: Optional[str] = Cookie(default=None), months: int = Query(default=6)):
    user = await _require_user(receipts_session)
    rows = [r for r in await repository.list_records(user["user_ids"]) if r.get("status") != "skipped"]
    amounts = [float(r.get("amount") or 0) for r in rows]
    total = round(sum(amounts), 2)

    by_vendor: dict[str, float] = defaultdict(float)
    by_category: dict[str, float] = defaultdict(float)
    by_month: dict[str, float] = defaultdict(float)
    cutoff = (datetime.now(timezone.utc) - timedelta(days=31 * months)).date().isoformat()

    for row in rows:
        amount = float(row.get("amount") or 0)
        by_vendor[row.get("vendor") or "Unknown"] += amount
        by_category[row.get("category") or "Other"] += amount
        date = str(row.get("date") or "")[:7]
        if date and str(row.get("date")) >= cutoff:
            by_month[date] += amount

    def top(mapping: dict[str, float], limit: int = 8) -> list[dict]:
        return [
            {"name": name, "amount": round(value, 2)}
            for name, value in sorted(mapping.items(), key=lambda kv: kv[1], reverse=True)[:limit]
        ]

    return {
        "total_spent": total,
        "receipt_count": len(rows),
        "vendor_count": len(by_vendor),
        "average": round(total / len(rows), 2) if rows else 0,
        "needs_review": sum(1 for r in rows if r.get("status") == "needs_review"),
        "top_vendors": top(by_vendor),
        "by_category": top(by_category, 12),
        "by_month": [
            {"month": month, "amount": round(value, 2)} for month, value in sorted(by_month.items())
        ],
    }


# ── demo ────────────────────────────────────────────────────────────────────

@router.post("/demo")
async def start_demo(response: Response, receipts_session: Optional[str] = Cookie(default=None)):
    """Run the graph over sample receipts. No Gmail, no account, no API key
    required beyond whatever the server already has."""
    user = await auth.resolve_session(receipts_session)
    if not user:
        demo_id = f"demo_{secrets.token_hex(6)}"
        token = await auth.link_google_account(f"{demo_id}@sample.local", "", user_id=demo_id)
        response.set_cookie(
            auth.SESSION_COOKIE,
            token,
            max_age=int(auth.SESSION_TTL.total_seconds()),
            httponly=True,
            samesite="lax",
            secure=settings.app_env != "development",
            path="/",
        )
        user = await auth.resolve_session(token)

    from ..demo_data import demo_emails

    emails: list[Email] = demo_emails()
    run = sync.start(user["user_id"], user_ids=user["user_ids"], emails=emails)
    return run.snapshot()

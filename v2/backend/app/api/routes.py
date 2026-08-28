from __future__ import annotations

import asyncio
import json
import secrets
import time
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Literal, Optional

from fastapi import APIRouter, Body, Cookie, HTTPException, Query, Request, Response
from fastapi.responses import PlainTextResponse, RedirectResponse, StreamingResponse
from pydantic import BaseModel, ConfigDict, Field

from .. import advisor, auth, llm, notifications, sync
from ..config import settings
from ..graph import persistence, runner
from ..graph.state import Email
from ..ingest import gmail
from ..insights import anomalies, exports, recurring, reporting
from ..store import accounts, repository
from ..store.repository import DEMO_PREFIX

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
        # A sample-inbox session is not an account: no password, no OAuth, and
        # signing in with Google simply replaces it. The UI needs to know so it
        # can keep offering the real sign-in instead of hiding it behind a
        # sign-out the visitor never asked for.
        "is_demo": str((user or {}).get("user_id") or "").startswith(DEMO_PREFIX),
        "email": (user or {}).get("email"),
        "gmail_connected": bool((user or {}).get("gmail_connected")),
        "model_configured": llm.available(),
        "storage": repository.describe(str((user or {}).get("user_id") or "")),
        "linked_legacy_accounts": max(len((user or {}).get("user_ids") or []) - 1, 0),
    }


@router.post("/session/end")
async def sign_out(response: Response, receipts_session: Optional[str] = Cookie(default=None)):
    # A demo session's rows live in the process; drop them as it ends rather
    # than waiting for the eviction cap to notice.
    leaving = await auth.resolve_session(receipts_session)
    if leaving and str(leaving.get("user_id") or "").startswith(DEMO_PREFIX):
        repository.forget_demo(str(leaving["user_id"]))
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

class SyncRequest(BaseModel):
    """Bounded on purpose. An unbounded max_results is a way to make the server
    spend someone else's Gmail quota and this process's memory."""

    model_config = ConfigDict(extra="forbid")

    max_results: int = Field(default=50, ge=1, le=500)
    days_back: int = Field(default=180, ge=1, le=3650)
    date_from: Optional[str] = Field(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$")
    date_to: Optional[str] = Field(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$")


@router.post("/sync")
async def start_sync(
    payload: Optional[SyncRequest] = Body(default=None),
    receipts_session: Optional[str] = Cookie(default=None),
):
    user = await _require_user(receipts_session)
    payload = payload or SyncRequest()
    run = sync.start(
        user["user_id"],
        user_ids=user["user_ids"],
        max_results=payload.max_results,
        days_back=payload.days_back,
        date_from=payload.date_from,
        date_to=payload.date_to,
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


# ── review: resuming a paused graph thread ──────────────────────────────────

class ReviewAnswer(BaseModel):
    """What a reviewer sends back. This becomes the `Command(resume=...)`
    value, so it is validated tightly — it re-enters the graph."""

    model_config = ConfigDict(extra="forbid")

    action: Literal["confirm", "discard"] = "confirm"
    vendor: Optional[str] = Field(default=None, max_length=120)
    amount: Optional[float] = Field(default=None, ge=-1_000_000, le=1_000_000)
    tax: Optional[float] = Field(default=None, ge=-1_000_000, le=1_000_000)
    subtotal: Optional[float] = Field(default=None, ge=-1_000_000, le=1_000_000)
    date: Optional[str] = Field(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$")
    category: Optional[str] = Field(default=None, max_length=40)
    payment_method: Optional[str] = Field(default=None, max_length=60)


@router.get("/review")
async def review_queue(receipts_session: Optional[str] = Cookie(default=None)):
    """Receipts the graph stopped on.

    `live` says whether the thread is still sitting in the checkpointer. With
    the in-process checkpointer a restart loses it, and the answer is applied
    as a direct edit instead — same outcome for the ledger, minus the
    re-validation pass.
    """
    user = await _require_user(receipts_session)
    rows = [r for r in await repository.list_records(user["user_ids"]) if r.get("status") == "needs_review"]
    paused = {
        item["email_id"]: item
        for item in await runner.paused_threads(user["user_id"], [r.get("email_id") for r in rows if r.get("email_id")])
    }
    return {
        "checkpointer": persistence.describe(),
        # `source` is present only while the thread is live: it comes out of the
        # checkpoint, not out of storage. Once the checkpoint is gone so is it.
        "items": [
            {
                **row,
                "live": row.get("email_id") in paused,
                "source": (paused.get(row.get("email_id")) or {}).get("source"),
            }
            for row in rows
        ],
        "learned": await persistence.learned_for(user["user_id"]),
    }


@router.post("/review/{email_id}")
async def resolve_review(
    email_id: str,
    answer: ReviewAnswer = Body(...),
    receipts_session: Optional[str] = Cookie(default=None),
):
    user = await _require_user(receipts_session)
    payload = {**answer.model_dump(exclude_none=True), "at": datetime.now(timezone.utc).isoformat()}

    resumed = await runner.resume_review(user["user_id"], email_id, payload)
    if resumed:
        return {"resumed": True, "record": resumed}

    # No live thread: apply the same answer straight to the stored record.
    rows = await repository.list_records(user["user_ids"])
    row = next((r for r in rows if r.get("email_id") == email_id), None)
    if not row:
        raise HTTPException(status_code=404, detail="No such receipt")

    if answer.action == "discard":
        patch: dict = {"status": "discarded"}
    else:
        patch = {k: v for k, v in answer.model_dump(exclude_none=True).items() if k != "action"}
        patch.update({"status": "parsed", "reviewed": True, "confidence": 1.0, "issues": []})
        # The learning half still happens, so the next email from this sender
        # resolves on its own.
        if patch.get("vendor"):
            await persistence.remember_vendor(user["user_id"], row.get("sender") or "", patch["vendor"])
        if patch.get("vendor") and patch.get("category"):
            await persistence.remember_category(user["user_id"], patch["vendor"], patch["category"])

    updated = await repository.update(user["user_id"], row["id"], patch)
    return {"resumed": False, "record": updated}


# ── notifications ───────────────────────────────────────────────────────────

class ReadRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ids: Optional[list[str]] = Field(default=None, max_length=500)
    all: bool = False


@router.get("/notifications")
async def list_notifications(receipts_session: Optional[str] = Cookie(default=None)):
    user = await _require_user(receipts_session)
    rows = await _ledger(user)
    notes = notifications.build(rows)

    account = await accounts.store().get_account(user["user_id"]) or {}
    read_ids = account.get("notifications_read") or []
    return notifications.apply_read_state(notes, read_ids)


@router.post("/notifications/read")
async def mark_notifications_read(
    payload: ReadRequest = Body(default=None),
    receipts_session: Optional[str] = Cookie(default=None),
):
    user = await _require_user(receipts_session)
    payload = payload or ReadRequest()

    rows = await _ledger(user)
    notes = notifications.build(rows)

    store = accounts.store()
    account = await store.get_account(user["user_id"]) or {}
    read_ids = set(notifications.prune_read_state(notes, account.get("notifications_read") or []))

    if payload.all:
        read_ids |= {note["id"] for note in notes}
    elif payload.ids:
        live = {note["id"] for note in notes}
        read_ids |= {rid for rid in payload.ids if rid in live}

    await store.put_account(user["user_id"], {**account, "notifications_read": sorted(read_ids)})
    return notifications.apply_read_state(notes, sorted(read_ids))


# ── financial outputs ───────────────────────────────────────────────────────

async def _ledger(user: dict) -> list[dict]:
    """Everything that counts as spend: parsed and flagged rows, never skips."""
    rows = await repository.list_records(user["user_ids"])
    return [r for r in rows if r.get("status") != "skipped"]


@router.get("/insights")
async def insights(receipts_session: Optional[str] = Cookie(default=None)):
    user = await _require_user(receipts_session)
    rows = await _ledger(user)
    subscriptions = recurring.detect(rows)
    return {
        "subscriptions": subscriptions,
        "subscription_summary": recurring.summary(subscriptions),
        "anomalies": anomalies.detect(rows, subscriptions),
        "concentration": reporting.vendor_concentration(rows),
    }


@router.get("/statement")
async def statement(
    month: Optional[str] = Query(default=None, pattern=r"^\d{4}-\d{2}$"),
    receipts_session: Optional[str] = Cookie(default=None),
):
    user = await _require_user(receipts_session)
    rows = await _ledger(user)
    target = month or datetime.now(timezone.utc).strftime("%Y-%m")
    months = sorted({str(r.get("date"))[:7] for r in rows if r.get("date")}, reverse=True)
    return {"available_months": months, **reporting.monthly_statement(rows, target)}


@router.get("/tax-summary")
async def tax_summary(
    year: Optional[int] = Query(default=None, ge=2000, le=2100),
    receipts_session: Optional[str] = Cookie(default=None),
):
    user = await _require_user(receipts_session)
    rows = await _ledger(user)
    return reporting.tax_summary(rows, year or datetime.now(timezone.utc).year)


@router.get("/export/{shape}", response_class=PlainTextResponse)
async def export(
    shape: str,
    month: Optional[str] = Query(default=None, pattern=r"^\d{4}-\d{2}$"),
    receipts_session: Optional[str] = Cookie(default=None),
):
    user = await _require_user(receipts_session)
    writer = exports.FORMATS.get(shape)
    if not writer:
        raise HTTPException(status_code=404, detail=f"Unknown export: {shape}")

    rows = await _ledger(user)
    if month:
        rows = [r for r in rows if str(r.get("date", ""))[:7] == month]
    rows.sort(key=lambda r: str(r.get("date") or ""))
    filename = f"receipts-{shape}{f'-{month}' if month else ''}.csv"
    return PlainTextResponse(
        writer(rows),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ── demo ────────────────────────────────────────────────────────────────────

@router.post("/demo")
async def start_demo(
    response: Response,
    months: int = Query(default=6, ge=0, le=12),
    receipts_session: Optional[str] = Cookie(default=None),
):
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

    from ..demo_data import demo_emails, history_emails

    # With history the sample inbox can demonstrate what the ledger *learns* —
    # recurring charges, a price rise, a duplicate billing. months=0 falls back
    # to the quick ten-receipt set.
    emails: list[Email] = history_emails(months) if months else demo_emails()
    run = sync.start(user["user_id"], user_ids=user["user_ids"], emails=emails)
    return run.snapshot()


# ── advisor ─────────────────────────────────────────────────────────────────
#
# One model call per turn, so unlike parsing it is not batched — and unlike
# parsing it is user-triggered, which is why it is the one endpoint with a rate
# limit. In-process and per user: enough to stop a stuck client burning the
# quota, not a substitute for a real limiter behind a load balancer.

_ADVISOR_CALLS: dict[str, list[float]] = defaultdict(list)
_ADVISOR_MAX_PER_MINUTE = 12


def _advisor_rate_limit(user_id: str) -> None:
    now = time.monotonic()
    recent = [t for t in _ADVISOR_CALLS[user_id] if now - t < 60.0]
    if len(recent) >= _ADVISOR_MAX_PER_MINUTE:
        raise HTTPException(status_code=429, detail="Too many questions at once — try again shortly.")
    recent.append(now)
    _ADVISOR_CALLS[user_id] = recent


class AdvisorTurn(BaseModel):
    model_config = ConfigDict(extra="ignore")
    role: Literal["user", "assistant"]
    content: str = Field(max_length=advisor.MAX_TURN_CHARS)


class AdvisorAsk(BaseModel):
    model_config = ConfigDict(extra="ignore")
    message: str = Field(min_length=1, max_length=advisor.MAX_MESSAGE)
    history: list[AdvisorTurn] = Field(default_factory=list)


@router.post("/advisor/chat")
async def advisor_chat(
    body: AdvisorAsk = Body(...),
    receipts_session: Optional[str] = Cookie(default=None),
):
    """Answers from the aggregated ledger. Never sees an email body — v2 does
    not store them — and never receives a record row by row."""
    user = await _require_user(receipts_session)
    _advisor_rate_limit(user["user_id"])

    if not llm.available():
        raise HTTPException(status_code=503, detail="No model is configured, so the advisor is unavailable.")

    message = body.message.strip()
    if not message:
        raise HTTPException(status_code=400, detail="Ask a question first.")

    rows = await _ledger(user)
    try:
        reply = await advisor.answer(message, [turn.model_dump() for turn in body.history], rows)
    except Exception as exc:  # noqa: BLE001 - provider errors are opaque
        raise HTTPException(status_code=503, detail=f"The model could not be reached ({type(exc).__name__}).")

    return {"reply": reply, "receipts_considered": len(rows)}

"""Gmail ingestion.

Only two jobs: turn a stored refresh token into a client, and turn Gmail's
message format into the flat dict the graph expects. Nothing here decides
whether an email is a receipt. That is `triage`'s call.
"""
from __future__ import annotations

import asyncio
import base64
import re
from email.utils import parsedate_to_datetime
from typing import Iterable, Optional

from bs4 import BeautifulSoup
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

from ..config import settings

SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]

# Gmail-side prefilter. Deliberately loose: it is cheaper to let a few
# non-receipts through to `triage` than to silently drop a real one.
QUERY = (
    '(subject:"receipt" OR subject:"confirmation" OR subject:"payment" '
    'OR subject:"order" OR subject:"invoice") '
    '-subject:"shipping update" -subject:"out for delivery" -subject:"delivered" '
    '-subject:"newsletter" -category:promotions '
)


def credentials_from_refresh_token(refresh_token: str) -> Credentials:
    creds = Credentials(
        token=None,
        refresh_token=refresh_token,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=settings.google_oauth_client_id,
        client_secret=settings.google_oauth_client_secret,
        scopes=SCOPES,
    )
    if not creds.valid:
        creds.refresh(Request())
    return creds


def _header(headers: list[dict], name: str) -> str:
    for header in headers:
        if header.get("name", "").lower() == name.lower():
            return header.get("value", "")
    return ""


def _body(payload: dict) -> str:
    html_parts: list[str] = []

    data = (payload.get("body") or {}).get("data")
    if data:
        decoded = base64.urlsafe_b64decode(data).decode("utf-8", errors="ignore")
        if payload.get("mimeType") == "text/plain":
            return decoded
        if payload.get("mimeType") == "text/html":
            html_parts.append(decoded)

    for part in payload.get("parts") or []:
        mime = part.get("mimeType")
        part_data = (part.get("body") or {}).get("data")
        if mime == "text/plain" and part_data:
            return base64.urlsafe_b64decode(part_data).decode("utf-8", errors="ignore")
        if mime == "text/html" and part_data:
            html_parts.append(base64.urlsafe_b64decode(part_data).decode("utf-8", errors="ignore"))
        elif part.get("parts"):
            nested = _body(part)
            if nested:
                return nested

    if not html_parts:
        return ""

    soup = BeautifulSoup(" ".join(html_parts), "html.parser")
    for tag in soup(["script", "style", "meta", "noscript"]):
        tag.decompose()
    # Line structure has to survive: the regex pass is line-anchored and the
    # prompt snippet keeps whole lines near financial keywords.
    lines = (re.sub(r"[ \t]+", " ", line).strip() for line in soup.get_text("\n").splitlines())
    return "\n".join(line for line in lines if line)


def _to_email(message: dict) -> dict:
    headers = message["payload"]["headers"]
    raw_date = _header(headers, "Date")
    try:
        date = parsedate_to_datetime(raw_date).date().isoformat()
    except (TypeError, ValueError):
        date = None
    return {
        "id": message["id"],
        "sender": _header(headers, "From"),
        "subject": _header(headers, "Subject"),
        "date": date,
        "body": _body(message["payload"]),
    }


def _fetch_sync(
    creds: Credentials,
    max_results: int,
    days_back: int,
    date_from: Optional[str],
    date_to: Optional[str],
    skip_ids: set[str],
) -> list[dict]:
    service = build("gmail", "v1", credentials=creds, cache_discovery=False)
    query = QUERY
    if date_from:
        query += f'after:{date_from.replace("-", "/")} '
    if date_to:
        query += f'before:{date_to.replace("-", "/")} '
    if not date_from and not date_to:
        query += f"newer_than:{days_back}d"

    listed = service.users().messages().list(userId="me", q=query, maxResults=max_results).execute()
    messages = [m for m in listed.get("messages", []) if m["id"] not in skip_ids]

    emails = []
    for message in messages:
        try:
            full = service.users().messages().get(userId="me", id=message["id"], format="full").execute()
            emails.append(_to_email(full))
        except Exception as exc:  # noqa: BLE001 - skip the message, keep the sync
            print(f"[gmail] could not fetch {message['id']}: {exc}")
    return emails


async def fetch_receipts(
    refresh_token: str,
    *,
    max_results: int = 50,
    days_back: int = 180,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    skip_ids: Optional[Iterable[str]] = None,
) -> list[dict]:
    creds = await asyncio.to_thread(credentials_from_refresh_token, refresh_token)
    return await asyncio.to_thread(
        _fetch_sync, creds, max_results, days_back, date_from, date_to, set(skip_ids or ())
    )


async def profile_email(refresh_token: str) -> Optional[str]:
    def _run() -> Optional[str]:
        creds = credentials_from_refresh_token(refresh_token)
        service = build("gmail", "v1", credentials=creds, cache_discovery=False)
        return service.users().getProfile(userId="me").execute().get("emailAddress")

    try:
        return await asyncio.to_thread(_run)
    except Exception:  # noqa: BLE001
        return None

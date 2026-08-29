"""Notifications.

Derived, not stored. Everything worth telling someone about is already a fact
about the ledger, a duplicate charge, a subscription that went up, a thread
waiting on a human, a bill landing in three days. Recomputing them means they
can never go stale or contradict the data, and the only thing that needs
persisting is which ones have been read.

Ids are stable hashes of what the notification is *about*, so the same finding
keeps the same id across runs and stays read once you have read it.
"""
from __future__ import annotations

import hashlib
from datetime import date, datetime, timedelta, timezone
from typing import Any, Optional

from .insights import anomalies as anomaly_rules
from .insights import recurring

UPCOMING_WINDOW_DAYS = 4


def _id(kind: str, *parts: Any) -> str:
    raw = "|".join([kind, *(str(p) for p in parts)])
    return hashlib.sha1(raw.encode()).hexdigest()[:16]


def _note(
    *,
    kind: str,
    severity: str,
    title: str,
    body: str,
    href: str,
    identity: tuple,
    amount: Optional[float] = None,
    when: Optional[str] = None,
) -> dict[str, Any]:
    return {
        "id": _id(kind, *identity),
        "kind": kind,
        "severity": severity,
        "title": title,
        "body": body,
        "href": href,
        "amount": round(amount, 2) if amount is not None else None,
        "at": when or datetime.now(timezone.utc).isoformat(),
    }


def _parse(value: Any) -> Optional[date]:
    try:
        return date.fromisoformat(str(value)[:10])
    except (TypeError, ValueError):
        return None


def _upcoming(subscriptions: list[dict], today: date) -> list[dict[str, Any]]:
    """Bills about to land. The one notification here that is genuinely
    forward-looking rather than a report on something that already happened."""
    notes = []
    for sub in subscriptions:
        due = _parse(sub.get("next_expected"))
        if not due:
            continue
        days = (due - today).days
        if not 0 <= days <= UPCOMING_WINDOW_DAYS:
            continue
        when = "today" if days == 0 else "tomorrow" if days == 1 else f"in {days} days"
        notes.append(
            _note(
                kind="upcoming",
                severity="info",
                title=f"{sub['vendor']} bills {when}",
                body=f"{sub['cadence'].capitalize()} charge, typically "
                f"{sub['typical_amount']:.2f}. Last charged {sub['last_charged']}.",
                href="/insights",
                identity=(sub["vendor"], sub["next_expected"]),
                amount=sub.get("typical_amount"),
            )
        )
    return notes


SEVERITY_FROM_ANOMALY = {"action": "alert", "watch": "warning"}

HREF_FROM_KIND = {
    "duplicate": "/transactions",
    "outlier": "/transactions",
    "missing_tax": "/transactions",
    "price_increase": "/insights",
    "lapsed": "/insights",
    "needs_review": "/review",
}


def build(rows: list[dict[str, Any]], today: Optional[date] = None) -> list[dict[str, Any]]:
    """Everything currently worth surfacing, newest and loudest first."""
    today = today or date.today()
    subscriptions = recurring.detect(rows, today)
    findings = anomaly_rules.detect(rows, subscriptions)

    notes: list[dict[str, Any]] = []
    for finding in findings:
        notes.append(
            _note(
                kind=finding["kind"],
                severity=SEVERITY_FROM_ANOMALY.get(finding["severity"], "info"),
                title=finding["title"],
                body=finding["detail"],
                href=HREF_FROM_KIND.get(finding["kind"], "/insights"),
                # Anchored to the receipts involved, so re-running the rules
                # produces the same id rather than a fresh unread copy.
                identity=(finding["title"], *sorted(finding.get("transaction_ids") or [])),
                amount=finding.get("amount"),
            )
        )

    notes.extend(_upcoming(subscriptions, today))

    rank = {"alert": 0, "warning": 1, "info": 2}
    notes.sort(key=lambda n: (rank.get(n["severity"], 3), -(n["amount"] or 0)))
    return notes


def apply_read_state(notes: list[dict[str, Any]], read_ids: list[str]) -> dict[str, Any]:
    read = set(read_ids or [])
    items = [{**note, "read": note["id"] in read} for note in notes]
    return {
        "items": items,
        "unread": sum(1 for item in items if not item["read"]),
    }


def prune_read_state(notes: list[dict[str, Any]], read_ids: list[str]) -> list[str]:
    """Forget read-marks for notifications that no longer exist, so the stored
    list cannot grow without bound."""
    live = {note["id"] for note in notes}
    return [rid for rid in (read_ids or []) if rid in live]

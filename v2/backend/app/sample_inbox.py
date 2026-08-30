"""The generated emails a demo run parsed, kept so they can be read back.

A real receipt links to Gmail, because Gmail holds the authoritative copy and
this app deliberately stores no bodies. A generated one has nowhere to link to,
which leaves a demo visitor unable to check any figure they are shown: the whole
claim is that every number is traceable, and for the demo it was not.

So the sample run's emails are held here for the life of the session. This is
not a retreat from not storing bodies. These are fixtures the server wrote
itself moments earlier, they belong to a throwaway identity, they never touch
Firestore, and they are dropped when the demo ends.
"""
from __future__ import annotations

from collections import OrderedDict
from typing import Any, Optional

# user id -> email id -> the email as the graph received it.
_INBOXES: "OrderedDict[str, dict[str, dict[str, Any]]]" = OrderedDict()

# Bounded for the same reason the demo ledger is: nothing expires a session, so
# a long-lived process would otherwise accumulate every visitor who passed
# through.
MAX_INBOXES = 50


def put(user_id: str, emails: list[dict[str, Any]]) -> None:
    _INBOXES[user_id] = {str(email.get("id")): dict(email) for email in emails}
    _INBOXES.move_to_end(user_id)
    while len(_INBOXES) > MAX_INBOXES:
        _INBOXES.popitem(last=False)


def listing(user_id: str) -> list[dict[str, Any]]:
    """Envelopes only, newest first. The body is fetched one at a time."""
    inbox = _INBOXES.get(user_id) or {}
    rows = [
        {
            "id": email.get("id"),
            "sender": email.get("sender"),
            "subject": email.get("subject"),
            "date": email.get("date"),
            "preview": " ".join((email.get("body") or "").split())[:120],
        }
        for email in inbox.values()
    ]
    return sorted(rows, key=lambda r: str(r.get("date") or ""), reverse=True)


def get(user_id: str, email_id: str) -> Optional[dict[str, Any]]:
    return (_INBOXES.get(user_id) or {}).get(str(email_id))


def forget(user_id: str) -> int:
    return len(_INBOXES.pop(user_id, {}))

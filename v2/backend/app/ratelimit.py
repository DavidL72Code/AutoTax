"""In-process rate limits for the endpoints that cost something.

This is deliberately small. It is not a substitute for a limiter at the edge:
it lives in one process, so a second instance doubles every allowance, and it
forgets everything on restart. What it does do is stop the two failure modes
that have actually happened here, a stuck client retrying in a loop and a
visitor replaying the sample run, from draining a shared daily model quota.

Two kinds of limit, because they answer different questions:

* `allow` is per caller. It keeps one client from monopolising the service.
* `budget` is global. A per caller limit does nothing against many callers, and
  the model quota is shared by all of them, so the expensive path also has a
  ceiling that does not care who is asking.
"""
from __future__ import annotations

import time
from collections import defaultdict, deque
from typing import Optional

from fastapi import HTTPException, Request

_HITS: dict[str, deque[float]] = defaultdict(deque)
_TOTALS: dict[str, deque[float]] = defaultdict(deque)

# Nothing expires a key on its own, so a long-lived process would otherwise hold
# one deque per caller it has ever seen.
MAX_KEYS = 5000


def _prune(window: "deque[float]", now: float, seconds: float) -> None:
    while window and now - window[0] >= seconds:
        window.popleft()


def _record(store: dict[str, "deque[float]"], key: str, limit: int, seconds: float,
            cost: int = 1) -> bool:
    now = time.monotonic()
    window = store[key]
    _prune(window, now, seconds)
    if len(window) + cost > limit:
        return False
    window.extend([now] * cost)

    if len(store) > MAX_KEYS:
        for stale in [k for k, v in store.items() if not v][: len(store) - MAX_KEYS]:
            store.pop(stale, None)
    return True


def allow(bucket: str, caller: str, limit: int, seconds: float, message: str) -> None:
    """Per caller. Raises 429 rather than returning, so a route reads as one line."""
    if not _record(_HITS, f"{bucket}:{caller}", limit, seconds):
        raise HTTPException(status_code=429, detail=message)


def budget(bucket: str, limit: int, seconds: float, message: str, cost: int = 1) -> None:
    """Across every caller. The model quota is shared, so its ceiling is too.

    `cost` is for the case where requests are not the same size. Counting demo
    *runs* would let one caller ask for a run ten times the usual length and
    spend ten times the quota against the same single unit, so what gets counted
    there is receipts. Charge the requested size up front: it is an upper bound
    on what the run will actually parse, and the point is to refuse before the
    work happens, not to bill accurately afterwards.
    """
    if not _record(_TOTALS, bucket, limit, seconds, cost):
        raise HTTPException(status_code=429, detail=message)


def client_key(request: Request) -> str:
    """Who to attribute a request to when there is no account behind it.

    The demo mints a fresh identity per run by design, so a per user limit on it
    would count to one forever. The address is the only thing left, and it comes
    from `x-forwarded-for` because the API sits behind a proxy and would
    otherwise see the proxy on every request.

    A client can put anything in that header. The proxy in front of this
    overwrites it rather than appending to what arrived, so the first entry is
    the address it observed. Treat this as best effort: it raises the cost of
    replaying the sample run, it does not make it impossible.
    """
    forwarded = request.headers.get("x-forwarded-for") or ""
    first = forwarded.split(",")[0].strip()
    if first:
        return first[:64]
    client = request.client
    return (client.host if client else "unknown")[:64]


def forget(bucket: str, caller: Optional[str] = None) -> None:
    """For tests, so one case does not spend another's allowance."""
    if caller is None:
        for key in [k for k in _HITS if k.startswith(f"{bucket}:")]:
            _HITS.pop(key, None)
        _TOTALS.pop(bucket, None)
    else:
        _HITS.pop(f"{bucket}:{caller}", None)

from __future__ import annotations

import time
from typing import Any

from ..state import Step


def step(
    node: str,
    detail: str,
    started: float,
    confidence: float | None = None,
    *,
    key: str | None = None,
    params: dict[str, Any] | None = None,
) -> Step:
    """`detail` stays the English sentence, so anything reading a trace as text
    keeps working. `key` and `params` are what a localised UI renders instead:
    the same fact, without the grammar baked in."""
    out: Step = {"node": node, "detail": detail, "ms": int((time.perf_counter() - started) * 1000)}
    if confidence is not None:
        out["confidence"] = confidence
    if key is not None:
        out["key"] = key
        out["params"] = params or {}
    return out

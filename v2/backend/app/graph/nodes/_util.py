from __future__ import annotations

import time

from ..state import Step


def step(node: str, detail: str, started: float) -> Step:
    return {"node": node, "detail": detail, "ms": int((time.perf_counter() - started) * 1000)}

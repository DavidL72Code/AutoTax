"""Ground-truth cases for the benchmark, sourced from app.demo_data."""
from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from app.demo_data import demo_cases, to_graph_email  # noqa: E402


def make_cases(count: int = 10, seed: int | None = 7) -> tuple[list[dict], list[dict]]:
    cases = demo_cases(count, seed)
    emails = [to_graph_email(case) for case in cases]
    truth = [{"vendor": c["vendor"], "amount": float(c["total"]), "tax": float(c["tax"])} for c in cases]
    return emails, truth

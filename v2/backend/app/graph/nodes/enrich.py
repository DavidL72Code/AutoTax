"""Node 5, category and payment method.

Known merchants get their category from the registry for free. Only unknown
merchants reach the model, and those requests batch together too.
"""
from __future__ import annotations

import time

from ... import llm
from .. import patterns, persistence, vendors
from ..state import ReceiptState
from ._util import step


async def enrich(state: ReceiptState) -> dict:
    started = time.perf_counter()
    draft = state.get("draft") or {}
    email = state.get("email") or {}
    out: dict = {"draft": {}, "sources": {}}

    if not draft.get("payment_method"):
        method = patterns.extract_payment_method(f"{email.get('subject', '')}\n{email.get('body', '')}")
        if method:
            out["draft"]["payment_method"] = method
            out["sources"]["payment_method"] = "regex"

    vendor = draft.get("vendor")

    # A category a person chose beats both the registry and the model, and it
    # persists across threads, so the same merchant is never asked about twice.
    if vendor:
        learned = await persistence.recall_category(state.get("user_id") or "local", vendor)
        if learned:
            out["draft"]["category"] = learned
            out["sources"]["category"] = "memory"
            return {**out, "steps": [step("enrich", f"category {learned} from memory", started,
                        key="trace.enrich.memory", params={"category": learned})]}

    if draft.get("category"):
        return {**out, "steps": [step("enrich", f"category {draft['category']} from registry", started,
                        key="trace.enrich.registry", params={"category": draft["category"]})]}

    known = vendors.category_for(vendor) if vendor else None
    if known:
        out["draft"]["category"] = known
        out["sources"]["category"] = "registry"
        return {**out, "steps": [step("enrich", f"category {known} from registry", started,
                        key="trace.enrich.registry", params={"category": known})]}

    if vendor and llm.available():
        try:
            result = await llm.CATEGORIZE.submit({"vendor": vendor, "subject": email.get("subject", "")})
            category = str((result or {}).get("category") or "").strip()
            if category in vendors.CATEGORIES:
                out["draft"]["category"] = category
                out["sources"]["category"] = "llm"
                out["llm_calls"] = state.get("llm_calls", 0) + 1
                return {**out, "steps": [step("enrich", f"category {category} from model", started,
                        key="trace.enrich.model", params={"category": category})]}
        except Exception:  # noqa: BLE001 - category is optional, never block on it
            pass

    out["draft"]["category"] = "Other"
    out["sources"]["category"] = "heuristic"
    return {**out, "steps": [step("enrich", "category defaulted to Other", started, key="trace.enrich.default")]}

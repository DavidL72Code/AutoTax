"""Node 3 — who was paid?

Order of trust: learned memory > sender domain > known-vendor mention in the
body > phrase match. Payment processors are a special case: paypal.com really
did send the mail, but the merchant is inside the body, so the domain only
wins as a fallback.
"""
from __future__ import annotations

import time

from .. import persistence, vendors
from ..state import ReceiptState, missing_fields, score
from ._util import step


async def resolve(state: ReceiptState) -> dict:
    started = time.perf_counter()
    email = state.get("email") or {}
    subject = email.get("subject") or ""
    body = email.get("body") or ""

    domain_vendor, domain_category, is_processor = vendors.from_sender(email.get("sender", ""))

    vendor = None
    source = None

    # Anything a person corrected before outranks every heuristic. This is the
    # cross-thread store, so a correction made on one email settles every later
    # email from the same sender — including in other runs.
    learned = await persistence.recall_vendor(state.get("user_id") or "local", email.get("sender", ""))
    if learned:
        vendor, source = learned, "memory"
    elif domain_vendor and not is_processor:
        vendor, source = domain_vendor, "domain"
    else:
        text_vendor = vendors.from_text(subject, body)
        if text_vendor:
            vendor, source = text_vendor, "registry" if vendors.category_for(text_vendor) else "regex"
        elif domain_vendor:
            vendor, source = domain_vendor, "domain"

    draft: dict = {}
    sources: dict[str, str] = {}
    if vendor:
        draft["vendor"] = vendor
        sources["vendor"] = source
        category = vendors.category_for(vendor) or (domain_category if source == "domain" else None)
        if category:
            draft["category"] = category
            sources["category"] = "registry"

    merged = {**(state.get("draft") or {}), **draft}
    merged_sources = {**(state.get("sources") or {}), **sources}
    detail = f"vendor={vendor} via {source}" if vendor else "vendor unresolved by rules"
    return {
        "draft": draft,
        "sources": sources,
        "missing": missing_fields(merged),
        "steps": [step("resolve", detail, started,
                       score(merged, merged_sources, state.get("issues") or [],
                             state.get("model_confidence") or {}),
                       key="trace.resolve.found" if vendor else "trace.resolve.unresolved",
                       params={"vendor": vendor, "source": source})],
    }

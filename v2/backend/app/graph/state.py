from __future__ import annotations

from typing import Annotated, Any, Literal, NotRequired, Optional, TypedDict

Source = Literal["domain", "registry", "regex", "llm", "heuristic", "memory", "human", "none"]
Status = Literal["pending", "parsed", "needs_review", "skipped", "failed", "discarded"]


class Email(TypedDict, total=False):
    id: str
    sender: str
    subject: str
    body: str
    date: str


class Draft(TypedDict, total=False):
    vendor: Optional[str]
    amount: Optional[float]
    tax: Optional[float]
    subtotal: Optional[float]
    # Adjustments between the subtotal and the total, so the arithmetic check
    # can account for them instead of calling a good receipt broken.
    shipping: Optional[float]
    discount: Optional[float]
    tip: Optional[float]
    currency: str
    order_number: Optional[str]
    date: Optional[str]
    category: Optional[str]
    payment_method: Optional[str]


class Step(TypedDict):
    node: str
    detail: str
    ms: int
    # Score at the moment this node finished, so the trace shows what the
    # routing decision was made on, not just the number persist ended up with.
    confidence: NotRequired[float]
    # The same detail as a translation key and its values, so the UI can render
    # the sentence in the reader's language instead of ours.
    key: NotRequired[str]
    params: NotRequired[dict[str, Any]]


def append_steps(left: list[Step], right: list[Step]) -> list[Step]:
    return [*(left or []), *(right or [])]


def merge_draft(left: Draft, right: Draft) -> Draft:
    merged: Draft = dict(left or {})  # type: ignore[assignment]
    for key, value in (right or {}).items():
        if value is not None:
            merged[key] = value  # type: ignore[literal-required]
    return merged


def merge_sources(left: dict[str, Source], right: dict[str, Source]) -> dict[str, Source]:
    return {**(left or {}), **(right or {})}


class ReceiptState(TypedDict, total=False):
    email: Email
    user_id: str

    draft: Annotated[Draft, merge_draft]
    sources: Annotated[dict[str, Source], merge_sources]

    # What the model said about its own work, per field it filled. Only
    # `escalate` writes here, and it merges its own previous answer so a retry
    # does not erase the first attempt's numbers.
    model_confidence: dict[str, float]
    steps: Annotated[list[Step], append_steps]

    is_receipt: bool
    triage_reason: str
    missing: list[str]
    issues: list[str]
    attempts: int
    status: Status
    saved_id: Optional[str]
    llm_calls: int
    error: Optional[str]

    # Set when a human answered the interrupt at `await_review`. Kept in state
    # rather than applied and forgotten, so the trace shows who decided what.
    resolution: Optional[dict[str, Any]]
    reviewed: bool


# Issues that must not be auto-saved: they either leave the record unusable or
# mean its own numbers disagree. `graph` routes on this and `persist` marks
# status from it, so it lives here rather than in either of them.
BLOCKING = frozenset({"vendor_missing", "amount_missing", "amount_not_positive", "total_does_not_reconcile"})

# Issues that describe the run rather than the receipt. They belong in the trace
# so a reader knows why a record stalled, but they are not evidence that the
# data is wrong, so they must not cost the record confidence.
NON_DATA_ISSUES = frozenset({"model_unavailable"})

# Blocking defects the model would have been asked to fix. A record carrying one
# of these *and* `model_unavailable` is in the queue because the recovery path
# was down, not because a person is needed, retrying should clear it.
# `total_does_not_reconcile` is deliberately excluded: a working model is asked
# twice and still cannot settle a receipt that contradicts itself.
MODEL_FIXABLE = frozenset({"vendor_missing", "amount_missing", "amount_not_positive"})


def blocked_on_model(issues: list[str]) -> bool:
    found = set(issues or [])
    return "model_unavailable" in found and bool(found & MODEL_FIXABLE)

REQUIRED_FIELDS = ("vendor", "amount")
SCORED_FIELDS = ("vendor", "amount", "tax", "date")


def missing_fields(draft: Draft) -> list[str]:
    return [f for f in ("vendor", "amount", "tax") if draft.get(f) is None]


def score(
    draft: Draft,
    sources: dict[str, str],
    issues: list[str],
    model_confidence: Optional[dict[str, float]] = None,
) -> float:
    """Cheap, explainable confidence: field coverage weighted by source quality."""
    weights = {
        "human": 1.0,     # someone looked at the email and said so
        "memory": 1.0,    # learned from an earlier human correction
        "domain": 1.0,
        "registry": 1.0,
        "regex": 0.9,
        "llm": 0.8,
        "heuristic": 0.5,
        "none": 0.0,
    }
    total = 0.0
    for field in SCORED_FIELDS:
        if draft.get(field) is None:
            continue
        source = sources.get(field, "none")
        # A model-filled field is worth what the model said it was worth. The
        # 0.8 below is only the fallback for an answer that came back without a
        # self-assessment.
        reported = (model_confidence or {}).get(field)
        if source == "llm" and reported is not None:
            total += reported
        else:
            total += weights.get(source, 0.4)
    value = total / len(SCORED_FIELDS)
    value -= 0.15 * len([i for i in (issues or []) if i not in NON_DATA_ISSUES])
    return max(0.0, min(1.0, round(value, 3)))


def confidence(state: ReceiptState) -> float:
    return score(
        state.get("draft") or {},
        state.get("sources") or {},
        state.get("issues") or [],
        state.get("model_confidence") or {},
    )


def new_state(email: Email, user_id: str = "local") -> ReceiptState:
    return {
        "email": email,
        "user_id": user_id,
        "draft": {"currency": "USD"},
        "sources": {},
        "steps": [],
        "missing": [],
        "issues": [],
        "attempts": 0,
        "status": "pending",
        "llm_calls": 0,
    }


def as_record(state: ReceiptState) -> dict[str, Any]:
    draft = state.get("draft") or {}
    email = state.get("email") or {}
    return {
        "email_id": email.get("id"),
        "vendor": draft.get("vendor"),
        "amount": draft.get("amount"),
        "tax": draft.get("tax"),
        "subtotal": draft.get("subtotal"),
        "currency": draft.get("currency", "USD"),
        "order_number": draft.get("order_number"),
        "date": draft.get("date") or email.get("date"),
        "category": draft.get("category"),
        "payment_method": draft.get("payment_method"),
        "status": state.get("status"),
        "confidence": confidence(state),
        "issues": state.get("issues") or [],
        "blocked_on_model": blocked_on_model(state.get("issues") or []),
        "sources": state.get("sources") or {},
        "model_confidence": state.get("model_confidence") or {},
        "steps": state.get("steps") or [],
        "llm_calls": state.get("llm_calls", 0),
    }

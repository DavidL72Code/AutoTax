from __future__ import annotations

from typing import Annotated, Any, Literal, Optional, TypedDict

Source = Literal["domain", "registry", "regex", "llm", "heuristic", "none"]
Status = Literal["pending", "parsed", "needs_review", "skipped", "failed"]


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
    currency: str
    order_number: Optional[str]
    date: Optional[str]
    category: Optional[str]
    payment_method: Optional[str]


class Step(TypedDict):
    node: str
    detail: str
    ms: int


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


REQUIRED_FIELDS = ("vendor", "amount")
SCORED_FIELDS = ("vendor", "amount", "tax", "date")


def missing_fields(draft: Draft) -> list[str]:
    return [f for f in ("vendor", "amount", "tax") if draft.get(f) is None]


def confidence(state: ReceiptState) -> float:
    """Cheap, explainable confidence: field coverage weighted by source quality."""
    weights = {"domain": 1.0, "registry": 1.0, "regex": 0.9, "llm": 0.8, "heuristic": 0.5, "none": 0.0}
    draft = state.get("draft") or {}
    sources = state.get("sources") or {}
    total = 0.0
    for field in SCORED_FIELDS:
        if draft.get(field) is None:
            continue
        total += weights.get(sources.get(field, "none"), 0.4)
    score = total / len(SCORED_FIELDS)
    score -= 0.15 * len(state.get("issues") or [])
    return max(0.0, min(1.0, round(score, 3)))


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
        "sources": state.get("sources") or {},
        "steps": state.get("steps") or [],
        "llm_calls": state.get("llm_calls", 0),
    }

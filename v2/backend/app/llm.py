"""Gemini access for the graph nodes.

Every node calls this module instead of the provider SDK directly. Two things
happen here that the nodes should not have to care about:

1. Coalescing. Concurrent requests of the same kind are collected for a short
   window and sent as ONE prompt. Parsing 40 emails costs a handful of API
   calls instead of 40, without any node knowing it is part of a batch.
2. Pacing. A rolling RPM gate plus a minimum inter-call interval keeps the
   free tier from returning 429s.
"""
from __future__ import annotations

import asyncio
import json
import re
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from .config import settings

_JSON_BLOCK = re.compile(r"\[.*\]|\{.*\}", re.DOTALL)


class LLMUnavailable(RuntimeError):
    pass


@dataclass
class _Pending:
    payload: dict[str, Any]
    future: asyncio.Future


@dataclass
class BatchSpec:
    """How one kind of request turns into a prompt and back into results."""

    name: str
    instructions: str
    render_item: Callable[[int, dict[str, Any]], str]
    max_output_tokens_per_item: int = 90
    max_batch: int = field(default_factory=lambda: settings.llm_batch_max_size)


class _RateGate:
    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._calls: list[float] = []
        self._last = 0.0

    async def wait(self) -> None:
        async with self._lock:
            now = time.monotonic()
            self._calls = [t for t in self._calls if now - t < 60.0]
            if len(self._calls) >= settings.llm_rpm_limit:
                await asyncio.sleep(60.0 - (now - self._calls[0]) + 0.1)
                now = time.monotonic()
                self._calls = [t for t in self._calls if now - t < 60.0]
            gap = settings.llm_min_interval_seconds - (now - self._last)
            if gap > 0:
                await asyncio.sleep(gap)
            self._last = time.monotonic()
            self._calls.append(self._last)


_gate = _RateGate()
_model = None
_call_count = 0


def calls_made() -> int:
    return _call_count


def reset_calls() -> None:
    global _call_count
    _call_count = 0


def _get_model():
    global _model
    if _model is not None:
        return _model
    if not (settings.google_api_key or "").strip():
        raise LLMUnavailable("GOOGLE_API_KEY is not set")
    from langchain_google_genai import ChatGoogleGenerativeAI

    _model = ChatGoogleGenerativeAI(
        model=settings.gemini_model,
        google_api_key=settings.google_api_key,
        temperature=0.0,
        max_retries=0,
    )
    return _model


async def _invoke(prompt: str, max_tokens: int) -> str:
    global _call_count
    model = _get_model()
    last_error: Optional[Exception] = None
    for attempt in range(settings.llm_max_retries):
        await _gate.wait()
        try:
            _call_count += 1
            response = await model.ainvoke(prompt, max_output_tokens=max_tokens)
            text = response.content
            if isinstance(text, list):
                text = "".join(part.get("text", "") for part in text if isinstance(part, dict))
            if text and text.strip():
                return text.strip()
            last_error = RuntimeError("empty response")
        except Exception as exc:  # noqa: BLE001 - provider errors are opaque
            last_error = exc
            await asyncio.sleep(1.0 + attempt)
    raise RuntimeError(f"Gemini call failed: {last_error}")


def _parse_array(text: str, expected: int) -> list[Optional[dict]]:
    match = _JSON_BLOCK.search(text or "")
    if not match:
        return [None] * expected
    try:
        data = json.loads(match.group(0))
    except json.JSONDecodeError:
        return [None] * expected
    if isinstance(data, dict):
        data = [data]
    out: list[Optional[dict]] = [None] * expected
    for entry in data:
        if not isinstance(entry, dict):
            continue
        try:
            index = int(entry.get("i", entry.get("index", -1)))
        except (TypeError, ValueError):
            continue
        if 0 <= index < expected:
            out[index] = entry
    return out


class Batcher:
    """Collects same-kind requests for a short window, then sends one prompt.

    A single worker task owns the queue. It only stands down while holding the
    lock and only when the queue is empty, so there is no window in which a
    request is enqueued with nothing scheduled to drain it — an earlier version
    scheduled the follow-up flush conditionally and could strand the remainder
    of an over-sized batch forever.
    """

    def __init__(self, spec: BatchSpec) -> None:
        self.spec = spec
        self._queue: list[_Pending] = []
        self._lock = asyncio.Lock()
        self._worker: Optional[asyncio.Task] = None

    async def submit(self, payload: dict[str, Any]) -> Optional[dict]:
        loop = asyncio.get_running_loop()
        pending = _Pending(payload=payload, future=loop.create_future())
        async with self._lock:
            self._queue.append(pending)
            if self._worker is None or self._worker.done():
                self._worker = asyncio.create_task(self._drain())
        # A response that never arrives must not hang the whole sync.
        return await asyncio.wait_for(pending.future, timeout=settings.llm_request_timeout)

    async def _drain(self) -> None:
        while True:
            await asyncio.sleep(settings.llm_batch_window_ms / 1000)
            async with self._lock:
                if not self._queue:
                    self._worker = None
                    return
                batch = self._queue[: self.spec.max_batch]
                del self._queue[: self.spec.max_batch]
            await self._send(batch)

    async def _send(self, batch: list[_Pending]) -> None:
        body = "\n\n".join(self.spec.render_item(i, p.payload) for i, p in enumerate(batch))
        prompt = (
            f"{self.spec.instructions}\n\n"
            f"Return ONLY a JSON array with exactly {len(batch)} objects, each including its \"i\" index.\n\n"
            f"{body}"
        )
        try:
            text = await _invoke(prompt, self.spec.max_output_tokens_per_item * len(batch) + 40)
            results = _parse_array(text, len(batch))
        except Exception as exc:  # noqa: BLE001
            for pending in batch:
                if not pending.future.done():
                    pending.future.set_exception(exc)
            return
        for pending, result in zip(batch, results):
            if not pending.future.done():
                pending.future.set_result(result)


# ── the two request kinds the graph uses ────────────────────────────────────

def _render_extract(index: int, payload: dict[str, Any]) -> str:
    wanted = ", ".join(payload["missing"])
    return (
        f"--- EMAIL {index} (need: {wanted}) ---\n"
        f"from: {payload.get('sender', '')}\n"
        f"subject: {payload.get('subject', '')}\n"
        f"{payload.get('snippet', '')}"
    )


EXTRACT = Batcher(
    BatchSpec(
        name="extract",
        instructions=(
            "You read purchase receipt emails and pull out the financial facts.\n"
            'For each email return {"i": <index>, "vendor": <merchant name or null>, '
            '"amount": <grand total paid as a number or null>, "tax": <tax charged as a number or null>, '
            '"confidence": {"<field>": <0.0-1.0>}}.\n'
            "Rules: vendor is the merchant the buyer paid, not the email platform or payment processor. "
            "amount is the final total charged, never a subtotal, an item price, or a rewards balance. "
            "tax is 0 when the receipt shows no tax line. Use null when the email genuinely does not say.\n"
            "HTML receipts arrive flattened, so a label and its value may sit on "
            "different lines, and one amount may be split across several — a currency "
            "symbol, then the whole part, then a decimal point, then the cents. "
            "Reassemble those into one number.\n"
            "Score confidence per field you filled, and mean it — this number decides whether a human "
            "is asked to check the record. 0.95+ the email states the value in words you can point to; "
            "0.7-0.9 you are reading it off a layout that could be misread; below 0.6 you inferred it "
            "from context or picked between competing numbers. Do not default to a round high number."
        ),
        render_item=_render_extract,
        max_output_tokens_per_item=130,
    )
)


def _render_triage(index: int, payload: dict[str, Any]) -> str:
    return (
        f"--- EMAIL {index} ---\n"
        f"from: {payload.get('sender', '')}\n"
        f"subject: {payload.get('subject', '')}\n"
        f"{payload.get('snippet', '')}"
    )


TRIAGE = Batcher(
    BatchSpec(
        name="triage",
        instructions=(
            "Decide whether each email documents a completed purchase by the recipient "
            "(a receipt, order confirmation, invoice, or payment confirmation).\n"
            'Return {"i": <index>, "receipt": true|false, "why": "<one code>"}.\n'
            "`why` must be exactly one of these codes, never a sentence: "
            "purchase_confirmed, order_placed, payment_received, shipping_only, marketing, "
            "account_notice, unclear.\n"
            "Marketing, sales announcements, shipping-status updates, and account notices are not receipts."
        ),
        render_item=_render_triage,
        max_output_tokens_per_item=40,
    )
)


def _render_category(index: int, payload: dict[str, Any]) -> str:
    return f"--- {index}: {payload.get('vendor', '')} | {payload.get('subject', '')}"


CATEGORIZE = Batcher(
    BatchSpec(
        name="categorize",
        instructions=(
            "Assign each merchant a spending category from exactly this list: "
            "Groceries, Dining, Transport, Shopping, Subscriptions, Travel, Utilities, "
            "Health, Entertainment, Services, Other.\n"
            'Return {"i": <index>, "category": "<one of the listed categories>"}.'
        ),
        render_item=_render_category,
        max_output_tokens_per_item=25,
    )
)


async def ask(prompt: str, *, max_tokens: int = 512) -> str:
    """One prompt, one answer. The batchers above exist because parsing 40
    emails is 40 identical questions; a conversation turn is not, so it goes
    straight through — still behind the same rate gate and retry policy."""
    return await _invoke(prompt, max_tokens)


def available() -> bool:
    return bool((settings.google_api_key or "").strip())

"""Checkpointer and long-term store.

Two different kinds of memory, and they are not interchangeable:

* **Checkpointer** — per-thread, short-term. Every superstep of the graph is
  written to it, which is what makes `interrupt()` possible: the graph stops
  mid-run at `await_review`, the process can do other things, and a later
  `Command(resume=...)` picks the same thread up from exactly where it paused.
  One email is one thread.

* **Store** — cross-thread, long-term. What the system has *learned*: that this
  sender domain is that merchant, that this merchant is that category. Written
  when a human corrects a record, read by `resolve` and `enrich` on every
  later email, including emails in other threads and other runs.

The default checkpointer keeps threads in-process, which is enough for a
review that is answered in the same session. Set `CHECKPOINT_BACKEND=sqlite`
(and `pip install langgraph-checkpoint-sqlite`) to keep paused reviews across
restarts.
"""
from __future__ import annotations

from typing import Any, Optional

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.store.base import BaseStore
from langgraph.store.memory import InMemoryStore

from ..config import settings

_checkpointer = None
_store: Optional[BaseStore] = None
_backend_name = "memory"


def checkpointer():
    """The saver the graph compiles with. Built once, reused for the process."""
    global _checkpointer, _backend_name
    if _checkpointer is not None:
        return _checkpointer

    if settings.checkpoint_backend == "sqlite":
        try:
            from langgraph.checkpoint.sqlite import SqliteSaver

            path = settings.checkpoint_path or str(settings.data_dir / "checkpoints.sqlite")
            settings.data_dir.mkdir(parents=True, exist_ok=True)
            _checkpointer = SqliteSaver.from_conn_string(path).__enter__()
            _backend_name = f"sqlite ({path})"
            return _checkpointer
        except ImportError:
            print(
                "[graph] CHECKPOINT_BACKEND=sqlite but langgraph-checkpoint-sqlite "
                "is not installed; falling back to in-process checkpoints"
            )

    _checkpointer = InMemorySaver()
    _backend_name = "memory"
    return _checkpointer


def store() -> BaseStore:
    global _store
    if _store is None:
        _store = InMemoryStore()
    return _store


def use(*, saver: Any = None, memory: BaseStore | None = None) -> None:
    """Swap either layer — tests and evals want a clean slate per run."""
    global _checkpointer, _store
    if saver is not None:
        _checkpointer = saver
    if memory is not None:
        _store = memory


def describe() -> str:
    checkpointer()
    return _backend_name


# ── what the store holds ────────────────────────────────────────────────────
#
# Namespaces are per user, so one person's corrections never leak into
# another's ledger.

def vendor_namespace(user_id: str) -> tuple[str, ...]:
    return (str(user_id), "vendors")


def category_namespace(user_id: str) -> tuple[str, ...]:
    return (str(user_id), "categories")


def domain_key(sender: str) -> str:
    """Memory is keyed on the sending domain, not the full address: receipts
    arrive from no-reply@, orders@, auto-confirm@ and friends, all of which
    should share one learned identity."""
    address = (sender or "").lower()
    return address.rsplit("@", 1)[-1].strip("> ") if "@" in address else address.strip()


async def remember_vendor(user_id: str, sender: str, vendor: str) -> None:
    key = domain_key(sender)
    if not (key and vendor):
        return
    await store().aput(vendor_namespace(user_id), key, {"vendor": vendor, "source": "human"})


async def recall_vendor(user_id: str, sender: str) -> Optional[str]:
    key = domain_key(sender)
    if not key:
        return None
    item = await store().aget(vendor_namespace(user_id), key)
    return (item.value or {}).get("vendor") if item else None


async def remember_category(user_id: str, vendor: str, category: str) -> None:
    if not (vendor and category):
        return
    await store().aput(
        category_namespace(user_id), vendor.strip().lower(), {"category": category, "source": "human"}
    )


async def recall_category(user_id: str, vendor: str) -> Optional[str]:
    if not vendor:
        return None
    item = await store().aget(category_namespace(user_id), vendor.strip().lower())
    return (item.value or {}).get("category") if item else None


async def learned_for(user_id: str) -> dict[str, list[dict[str, Any]]]:
    """Everything the system has learned from this user's corrections."""
    vendors = await store().asearch(vendor_namespace(user_id), limit=200)
    categories = await store().asearch(category_namespace(user_id), limit=200)
    return {
        "vendors": [{"domain": item.key, **(item.value or {})} for item in vendors],
        "categories": [{"vendor": item.key, **(item.value or {})} for item in categories],
    }

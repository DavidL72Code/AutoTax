"""The receipt graph.

    ┌──────────────────────────── the model loop ────────────────────────────┐
    │                                                                        │
  triage ─not a receipt─► END                                                │
    │                                                                        │
  extract ─► resolve ─gaps─► escalate ─► enrich ─► validate ─fixable─────────┘
                │                          ▲          │        (bounded to 2)
                └─complete─────────────────┘          │
                                                      ├─clean─► persist ─► END
                                                      │
                                                 unresolved
                                                      │
                                                await_review  ◄──── interrupt()
                                                      │         Command(resume=…)
                                                      └─► back to validate

Two cycles, not one:

* **The model loop.** `validate` finds a defect a model could plausibly fix and
  sends the record back to `escalate` with only the suspect fields. Bounded by
  `MAX_ESCALATIONS`, because an unbounded retry is just a slower failure.

* **The human loop.** When the rules and the model have both run out, the graph
  *stops* at `await_review` via `interrupt()`. The thread's state goes to the
  checkpointer and the run ends. A later `Command(resume=…)` re-enters the same
  thread, and the human's values go back through `validate` — the same
  arithmetic the model had to satisfy — before anything is written.

The second cycle is the reason this is a state machine with a checkpointer
rather than a function that returns a dict.
"""
from __future__ import annotations

from langgraph.graph import END, START, StateGraph

from .. import llm
from .nodes.await_review import await_review
from .nodes.enrich import enrich
from .nodes.escalate import escalate
from .nodes.extract import extract
from .nodes.persist import persist
from .nodes.resolve import resolve
from .nodes.triage import triage
from .nodes.validate import validate
from .persistence import checkpointer, store
from .state import BLOCKING, ReceiptState

MAX_ESCALATIONS = 2

# `BLOCKING` (in state.py) is the set of defects a person can settle but a model
# cannot: the value simply is not in the email, or what is there does not add up.


def _after_triage(state: ReceiptState) -> str:
    return "extract" if state.get("is_receipt") else END


def _after_resolve(state: ReceiptState) -> str:
    if state.get("missing") and llm.available():
        return "escalate"
    return "enrich"


def _after_validate(state: ReceiptState) -> str:
    issues = set(state.get("issues") or [])

    # 1. Cheap fix first: ask the model again, for the suspect fields only.
    if state.get("missing") and llm.available() and state.get("attempts", 0) < MAX_ESCALATIONS:
        return "escalate"

    # 2. Out of automatic options, and it still does not hold up. Ask a person
    #    — once. A record that has already been reviewed goes through.
    if issues & BLOCKING and not state.get("reviewed"):
        return "await_review"

    return "persist"


def _after_review(state: ReceiptState) -> str:
    # A discarded receipt still gets written, with `discarded` status, so the
    # next sync recognises the message id and does not parse it again.
    return "persist" if state.get("status") == "discarded" else "validate"


def build_graph(*, interactive: bool = True):
    """`interactive=False` compiles the same nodes without the human loop, for
    benchmarks and for syncs that should never block."""
    builder = StateGraph(ReceiptState)
    builder.add_node("triage", triage)
    builder.add_node("extract", extract)
    builder.add_node("resolve", resolve)
    builder.add_node("escalate", escalate)
    builder.add_node("enrich", enrich)
    builder.add_node("validate", validate)
    builder.add_node("persist", persist)

    builder.add_edge(START, "triage")
    builder.add_conditional_edges("triage", _after_triage, {"extract": "extract", END: END})
    builder.add_edge("extract", "resolve")
    builder.add_conditional_edges("resolve", _after_resolve, {"escalate": "escalate", "enrich": "enrich"})
    builder.add_edge("escalate", "enrich")
    builder.add_edge("enrich", "validate")

    if interactive:
        builder.add_node("await_review", await_review)
        builder.add_conditional_edges(
            "validate",
            _after_validate,
            {"escalate": "escalate", "await_review": "await_review", "persist": "persist"},
        )
        builder.add_conditional_edges(
            "await_review", _after_review, {"validate": "validate", "persist": "persist"}
        )
    else:
        builder.add_conditional_edges(
            "validate",
            lambda state: "persist" if _after_validate(state) != "escalate" else "escalate",
            {"escalate": "escalate", "persist": "persist"},
        )

    builder.add_edge("persist", END)

    # The checkpointer is what makes `interrupt` and resume possible; the store
    # is cross-thread memory that `resolve` and `enrich` read from.
    return builder.compile(checkpointer=checkpointer(), store=store())


_compiled: dict[bool, object] = {}


def receipt_graph(*, interactive: bool = True):
    if interactive not in _compiled:
        _compiled[interactive] = build_graph(interactive=interactive)
    return _compiled[interactive]


def reset() -> None:
    """Drop compiled graphs — used after swapping the checkpointer in tests."""
    _compiled.clear()

"""The receipt graph.

    triage ─not a receipt─────────────────────────────────► END
       │
    extract ──► resolve ──complete?──► enrich ──► validate ──clean──► persist ──► END
                   │                     ▲            │
                   └──gaps──► escalate ──┘            └──fixable──► escalate
                                                         (once)

Each node owns exactly one question, records why it answered the way it did,
and hands the state on. Model calls live in `escalate` and the two optional
judgement calls in `triage`/`enrich` — everything else is deterministic, which
is what keeps a full inbox sync down to a handful of API requests.
"""
from __future__ import annotations

from langgraph.graph import END, START, StateGraph

from .. import llm
from .nodes.enrich import enrich
from .nodes.escalate import escalate
from .nodes.extract import extract
from .nodes.persist import persist
from .nodes.resolve import resolve
from .nodes.triage import triage
from .nodes.validate import validate
from .state import ReceiptState

MAX_ESCALATIONS = 2


def _after_triage(state: ReceiptState) -> str:
    return "extract" if state.get("is_receipt") else END


def _after_resolve(state: ReceiptState) -> str:
    if state.get("missing") and llm.available():
        return "escalate"
    return "enrich"


def _after_validate(state: ReceiptState) -> str:
    fixable = bool(state.get("missing"))
    if fixable and llm.available() and state.get("attempts", 0) < MAX_ESCALATIONS:
        return "escalate"
    return "persist"


def build_graph():
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
    builder.add_conditional_edges("validate", _after_validate, {"escalate": "escalate", "persist": "persist"})
    builder.add_edge("persist", END)
    return builder.compile()


_compiled = None


def receipt_graph():
    global _compiled
    if _compiled is None:
        _compiled = build_graph()
    return _compiled

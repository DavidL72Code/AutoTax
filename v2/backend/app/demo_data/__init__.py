"""Sample inboxes for demo mode and for the eval harness.

`receipts` holds the data model, `layouts` the sixteen ways a receipt can look,
`corpus` the assembly. See v2/docs/fixtures.md for why this is a package rather
than the pair of body builders it replaces.
"""
from .corpus import (
    demo_cases,
    demo_emails,
    history_cases,
    history_emails,
    to_graph_email,
)
from .layouts import BY_NAME, REGISTRY
from .receipts import Layout, LineItem, Path, Receipt

__all__ = [
    "demo_cases", "demo_emails", "history_cases", "history_emails", "to_graph_email",
    "REGISTRY", "BY_NAME", "Layout", "LineItem", "Path", "Receipt",
]

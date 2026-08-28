"""The receipt as data, before anyone decides how it looks on screen.

The point of this module is one invariant: a receipt's subtotal is the sum of
its own line items, and its total is built from that subtotal. The previous
generator drew item prices independently of the subtotal it was handed, so no
fixture's arithmetic held together and `validate` had nothing real to check.
Here the numbers are derived, so a layout that breaks them has to say so.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from enum import Enum
from typing import Callable, Optional


class Path(str, Enum):
    """Which way through the graph a layout is expected to send a receipt."""

    RULES_ONLY = "rules_only"   # patterns prove every field; no model call
    ESCALATE = "escalate"       # patterns leave a gap the model must fill
    REVIEW = "review"           # ends up flagged, whatever the model says
    SKIPPED = "skipped"         # triage rejects it; nothing downstream runs


@dataclass(frozen=True)
class LineItem:
    description: str
    qty: int
    unit_price: float

    @property
    def line_total(self) -> float:
        return round(self.qty * self.unit_price, 2)


@dataclass(frozen=True)
class Receipt:
    vendor: str
    domain: str
    when: date
    items: tuple[LineItem, ...]
    tax_rate: float = 0.0625
    shipping: float = 0.0
    discount: float = 0.0
    tip: float = 0.0
    currency: str = "USD"
    symbol: str = "$"
    minor_units: int = 2
    order_ref: str = ""
    # Set by a layout that renders a total which does not follow from the rest.
    # The rendered document says `stated_total`; the arithmetic says `total`.
    corrupt_total: Optional[float] = None

    def _round(self, value: float) -> float:
        return round(value, self.minor_units) if self.minor_units else float(round(value))

    @property
    def subtotal(self) -> float:
        return self._round(sum(item.line_total for item in self.items))

    @property
    def tax(self) -> float:
        return self._round(self.subtotal * self.tax_rate)

    @property
    def total(self) -> float:
        return self._round(self.subtotal + self.tax + self.shipping - self.discount + self.tip)

    @property
    def stated_total(self) -> float:
        """What the rendered document claims. Differs from `total` only when a
        layout deliberately corrupts it."""
        return self.total if self.corrupt_total is None else self._round(self.corrupt_total)

    @property
    def stamp(self) -> str:
        return self.when.strftime("%Y-%m-%d")

    def money(self, value: float) -> str:
        """Format in this receipt's own convention — including the European
        period/comma inversion and zero-decimal currencies."""
        if self.minor_units == 0:
            return f"{self.symbol}{value:,.0f}"
        text = f"{value:,.2f}"
        if self.currency == "EUR":
            text = text.translate(str.maketrans({",": ".", ".": ","}))
            return f"{text} {self.currency}"
        return f"{self.symbol}{text}"


@dataclass(frozen=True)
class Layout:
    """A way of rendering a receipt, plus what the harness should expect of it."""

    name: str
    render: Callable[[Receipt], str]
    expected_path: Path
    tests: str
    # Other outcomes that are also correct for this layout.
    also_acceptable: tuple[Path, ...] = ()
    # Kept out of the demo inbox. A ¥15,737 receipt recorded as $15,737 is the
    # right thing for the eval to measure and the wrong thing to put in a
    # dashboard total, so the two corpora differ here on purpose.
    eval_only: bool = False
    weight: float = 1.0
    expected_issues: tuple[str, ...] = ()
    # Some layouts state a number the pipeline cannot be expected to get right
    # (a non-USD amount recorded as USD). Those are measured, not failed.
    tolerate_currency_loss: bool = False
    subject: Optional[Callable[[Receipt], str]] = None
    sender: Optional[Callable[[Receipt], str]] = None
    expect_receipt: bool = True
    # When the document states no total at all, the truthful expectation for
    # `amount` is the derived one — there is nothing to read off the page.
    expected_amount: Optional[Callable[[Receipt], Optional[float]]] = None
    expected_tax: Optional[Callable[[Receipt], Optional[float]]] = None
    expected_vendor: Optional[Callable[[Receipt], Optional[str]]] = None
    notes: tuple[str, ...] = field(default_factory=tuple)

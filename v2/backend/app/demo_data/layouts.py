"""Sixteen ways a receipt can look, and what each one is here to prove.

Every layout is a pure function of a `Receipt`, so the numbers on the page are
always the receipt's own. The metadata beside each one is what turns the corpus
from a pile of documents into a test: `expected_path` asserts routing,
`expected_issues` asserts what `validate` should find.

On HTML: `ingest/gmail.py::_body` prefers `text/plain`, and when only HTML
exists it runs the markup through BeautifulSoup and collapses whitespace before
the graph sees anything. So the HTML layouts here are written as the *flattened*
result, tags gone, table cells landing on separate lines. Shipping raw markup
would test a path that does not exist.
"""
from __future__ import annotations

import random

from .receipts import Layout, Path, Receipt


def _items_block(receipt: Receipt, *, leader: bool = False) -> str:
    lines = []
    for item in receipt.items:
        if leader:
            dots = "." * max(3, 34 - len(item.description))
            lines.append(f"{item.description} x{item.qty} {dots} {receipt.money(item.line_total)}")
        else:
            lines.append(f"- {item.description} (x{item.qty}) {receipt.money(item.line_total)}")
    return "\n".join(lines)


# ── rules-only: the patterns should prove every field, with no model call ────

def plain_labeled(r: Receipt) -> str:
    return (
        f"Receipt Confirmation\n"
        f"Date: {r.stamp}\n"
        f"Vendor: {r.vendor}\n"
        f"{_items_block(r)}\n"
        f"Subtotal: {r.money(r.subtotal)}\n"
        f"Tax: {r.money(r.tax)}\n"
        f"Total: {r.money(r.stated_total)}\n"
        f"Thank you for your purchase.\n"
    )


def table_dot_leader(r: Receipt) -> str:
    return (
        f"ORDER RECEIPT, {r.vendor}\n"
        f"Order {r.order_ref}   {r.stamp}\n"
        f"{'-' * 46}\n"
        f"{_items_block(r, leader=True)}\n"
        f"{'-' * 46}\n"
        f"Subtotal ................... {r.money(r.subtotal)}\n"
        f"Sales Tax .................. {r.money(r.tax)}\n"
        f"Total Paid ................. {r.money(r.stated_total)}\n"
    )


def receipt_header_block(r: Receipt) -> str:
    return (
        f"Payment Receipt\n\n"
        f"Merchant: {r.vendor}\n"
        f"Transaction Date: {r.stamp}\n"
        f"Reference: {r.order_ref}\n\n"
        f"Amount Before Tax: {r.money(r.subtotal)}\n"
        f"Sales Tax: {r.money(r.tax)}\n"
        f"Amount Charged: {r.money(r.stated_total)}\n\n"
        f"Paid with card ending in 4242.\n"
    )


# ── escalation: the patterns cannot prove it; the model should ───────────────

def reconciliation_block(r: Receipt) -> str:
    """The decoy-heavy body from the original generator, kept because it is a
    good adversarial case, every competing number is a plausible answer."""
    auth_hold = round(r.stated_total * 1.08, 2)
    pending = round(r.stated_total * 0.4, 2)
    prior = round(r.stated_total * 1.6, 2)
    return (
        f"Subject Thread: Re: order update / invoice copy / receipt confirmation\n"
        f"Merchant Notice: This receipt may include pending holds.\n"
        f"Order Ref: {r.order_ref}\n"
        f"----- PAYMENT RECONCILIATION BLOCK -----\n"
        f"Document Date -> {r.stamp}\n"
        f"Merchant Legal Name -> {r.vendor}\n"
        f"Merchandise Sum (USD) -> {r.money(r.subtotal)}\n"
        f"Local Levy @ 6.25 pct -> {r.money(r.tax)}\n"
        f"Balance Due Now (final) -> {r.money(r.stated_total)}\n"
        f"--------------------------------\n"
        f"Auth Hold (temporary): {r.money(auth_hold)}\n"
        f"Pending Charge (not final): {r.money(pending)}\n"
        f"Previous Balance: {r.money(prior)}\n"
        f"Line Items:\n{_items_block(r)}\n"
        f"Promo Banner: Save 15% on next order over $50.00\n"
    )


def flattened_html_cells(r: Receipt) -> str:
    """A `<table>` after BeautifulSoup: each cell on its own line, so every
    label is separated from its value. This is what `extract_amount`'s
    cross-line fallback exists for, and nothing tested it before."""
    return (
        f"{r.vendor}\n"
        f"Your order is confirmed\n"
        f"Order Date\n{r.stamp}\n"
        f"Order Number\n{r.order_ref}\n"
        f"Item\nQty\nPrice\n"
        + "".join(f"{i.description}\n{i.qty}\n{r.money(i.line_total)}\n" for i in r.items)
        + f"Subtotal\n{r.money(r.subtotal)}\n"
        f"Tax\n{r.money(r.tax)}\n"
        f"Order Total\n{r.money(r.stated_total)}\n"
        f"View order  |  Contact us  |  Unsubscribe\n"
    )


def flattened_html_inline(r: Receipt) -> str:
    """Styled spans that split a single amount across elements, so the currency
    symbol, the dollars and the cents each land on their own line."""
    whole, cents = f"{r.stated_total:.2f}".split(".")
    return (
        f"{r.vendor}\n"
        f"Thanks for your order\n"
        f"Placed\n{r.stamp}\n"
        f"{_items_block(r)}\n"
        f"Subtotal\n{r.money(r.subtotal)}\n"
        f"Estimated tax\n{r.money(r.tax)}\n"
        f"Total\n"
        f"{r.symbol}\n{whole}\n.\n{cents}\n"
        f"This is not a bill. Card charged automatically.\n"
    )


def no_explicit_total(r: Receipt) -> str:
    """The total is stated nowhere. It has to be summed from the items, so the
    honest expectation is the derived number."""
    return (
        f"Thanks for shopping with {r.vendor}!\n"
        f"Placed on {r.stamp}.\n\n"
        f"Your items:\n{_items_block(r)}\n\n"
        f"Tax collected: {r.money(r.tax)}\n"
        f"Your card has been charged. No further action needed.\n"
    )


def forwarded_thread(r: Receipt) -> str:
    """A reply chain carrying two receipts. The stale quoted one is older and
    cheaper; the live one at the top is the answer."""
    stale = round(r.stated_total * 0.37, 2)
    return (
        f"Fwd: receipt, please file\n"
        f"Forwarded message from accounts@{r.domain}\n\n"
        f"Merchant: {r.vendor}\n"
        f"Date: {r.stamp}\n"
        f"Subtotal: {r.money(r.subtotal)}\n"
        f"Tax: {r.money(r.tax)}\n"
        f"Total charged: {r.money(r.stated_total)}\n\n"
        f"> On an earlier date, {r.vendor} wrote:\n"
        f"> Receipt\n"
        f"> Total: {r.money(stale)}\n"
        f"> Thank you for your purchase.\n"
        f"> This message has been superseded.\n"
    )


def installments(r: Receipt) -> str:
    """An order total and a smaller amount actually charged today. The charge is
    the transaction; the order total is the decoy."""
    today = round(r.stated_total / 2, 2)
    return (
        f"{r.vendor}, payment 1 of 2\n"
        f"Date: {r.stamp}\n"
        f"{_items_block(r)}\n"
        f"Order value: {r.money(r.stated_total)}\n"
        f"Charged today: {r.money(today)}\n"
        f"Remaining balance due in 30 days: {r.money(round(r.stated_total - today, 2))}\n"
    )


def processor_relay(r: Receipt) -> str:
    """Sent by a payment processor. The vendor is in the body, and the sender
    domain is a trap, `resolve` has to refuse it."""
    return (
        f"You sent a payment\n"
        f"Date: {r.stamp}\n"
        f"Merchant: {r.vendor}\n"
        f"Subtotal: {r.money(r.subtotal)}\n"
        f"Sales Tax: {r.money(r.tax)}\n"
        f"Amount: {r.money(r.stated_total)}\n"
        f"Paid with your linked account. This is your receipt.\n"
    )


# ── non-USD: the number is readable, the currency is not recorded ────────────

def eur_comma_decimal(r: Receipt) -> str:
    return (
        f"Zahlungsbestätigung, {r.vendor}\n"
        f"Belegdatum: {r.stamp}\n"
        f"{_items_block(r)}\n"
        f"Zwischensumme: {r.money(r.subtotal)}\n"
        f"MwSt: {r.money(r.tax)}\n"
        f"Gesamtbetrag: {r.money(r.stated_total)}\n"
    )


def jpy_no_decimals(r: Receipt) -> str:
    return (
        f"{r.vendor}. Receipt / 領収書\n"
        f"Date: {r.stamp}\n"
        f"{_items_block(r)}\n"
        f"Subtotal: {r.money(r.subtotal)}\n"
        f"Consumption Tax: {r.money(r.tax)}\n"
        f"Total: {r.money(r.stated_total)}\n"
    )


# ── layouts that must produce an issue ───────────────────────────────────────

def mismatched_total(r: Receipt) -> str:
    """States a subtotal, a tax and a total that do not add up. This is the only
    layout that can trip `total_does_not_reconcile`, and therefore the only one
    that exercises the retry loop and the review queue."""
    return (
        f"Invoice Paid\n"
        f"From: {r.vendor}\n"
        f"Email Date: {r.stamp}\n"
        f"Merchandise Total: {r.money(r.subtotal)}\n"
        f"Tax Amount: {r.money(r.tax)}\n"
        f"Grand Total: {r.money(r.stated_total)}\n"
        f"Keep this email for your records.\n"
    )


def shipping_and_discount(r: Receipt) -> str:
    """A legitimate receipt whose total includes shipping and a discount, with
    the subtotal stated. `validate` reconciles subtotal + tax against the total
    and knows nothing about either adjustment, so it reports a drift that is not
    an error. The layout exists to keep that gap visible."""
    return (
        f"Order Receipt\n"
        f"Store: {r.vendor}\n"
        f"Date: {r.stamp}\n"
        f"{_items_block(r)}\n"
        f"Subtotal Amount: {r.money(r.subtotal)}\n"
        f"Shipping: {r.money(r.shipping)}\n"
        f"Promotion: -{r.money(r.discount)}\n"
        f"Tax Collected: {r.money(r.tax)}\n"
        f"Total Paid: {r.money(r.stated_total)}\n"
    )


def zero_total(r: Receipt) -> str:
    return (
        f"Receipt\n"
        f"Vendor: {r.vendor}\n"
        f"Date: {r.stamp}\n"
        f"Subtotal: {r.money(0.0)}\n"
        f"Tax: {r.money(0.0)}\n"
        f"Total: {r.money(0.0)}\n"
        f"Your free trial month starts today.\n"
    )


def image_only(r: Receipt) -> str:
    """Almost nothing to read. The requirement is that nothing is invented."""
    return (
        f"{r.vendor}\n"
        f"[image: receipt]\n"
        f"View this receipt in your browser\n"
        f"Questions? Contact support.\n"
    )


# ── the registry ────────────────────────────────────────────────────────────

REGISTRY: tuple[Layout, ...] = (
    Layout(
        name="plain_labeled", render=plain_labeled, expected_path=Path.RULES_ONLY, weight=3.0,
        tests="baseline: labelled total on one line",
    ),
    Layout(
        name="table_dot_leader", render=table_dot_leader, expected_path=Path.RULES_ONLY, weight=2.0,
        tests="dot leaders and column alignment around the value",
    ),
    Layout(
        name="receipt_header_block", render=receipt_header_block, expected_path=Path.RULES_ONLY, weight=2.0,
        tests="blank-line separated blocks, 'Amount Charged' phrasing",
    ),
    Layout(
        name="reconciliation_block", render=reconciliation_block, expected_path=Path.ESCALATE, weight=2.0,
        tests="decoys: auth hold, pending charge, prior balance",
    ),
    Layout(
        name="flattened_html_cells", render=flattened_html_cells, expected_path=Path.RULES_ONLY, weight=2.0,
        tests="every label separated from its value by a newline",
        notes=("declared ESCALATE on assumption; extract_amount's cross-line fallback handles it",),
    ),
    Layout(
        name="flattened_html_inline", render=flattened_html_inline, expected_path=Path.ESCALATE, weight=1.0,
        tests="one amount split across symbol / dollars / cents lines",
    ),
    Layout(
        name="no_explicit_total", render=no_explicit_total, expected_path=Path.ESCALATE, weight=1.5,
        tests="no total stated anywhere; must be summed from line items",
    ),
    Layout(
        name="forwarded_thread", render=forwarded_thread, expected_path=Path.RULES_ONLY, weight=1.0,
        tests="quoted stale receipt below the live one",
        notes=("_labelled_value scans top-down, so the live total wins over the quoted one",),
        subject=lambda r: f"Fwd: Your receipt from {r.vendor}",
    ),
    Layout(
        name="installments", render=installments, expected_path=Path.ESCALATE, weight=1.0,
        tests="order value vs the amount actually charged today",
        expected_amount=lambda r: round(r.stated_total / 2, 2),
        expected_tax=lambda r: None,
        notes=("the charge is the transaction, not the order value",
               "the document states no tax line, so none is expected",),
    ),
    Layout(
        name="processor_relay", render=processor_relay, expected_path=Path.ESCALATE, weight=1.0,
        tests="vendor is in the body; the sender domain is a processor",
        sender=lambda r: "service@paypal.com",
        subject=lambda r: f"You sent a payment to {r.vendor}",
    ),
    Layout(
        name="eur_comma_decimal", render=eur_comma_decimal, expected_path=Path.ESCALATE, weight=1.0,
        tests="1.234,56 EUR, period and comma inverted", tolerate_currency_loss=True,
    ),
    Layout(
        name="jpy_no_decimals", render=jpy_no_decimals, expected_path=Path.ESCALATE, weight=1.0,
        tests="zero-decimal currency", tolerate_currency_loss=True, eval_only=True,
    ),
    Layout(
        name="mismatched_total", render=mismatched_total, expected_path=Path.REVIEW, weight=1.0,
        tests="subtotal + tax != total; the only path to the retry loop",
        expected_issues=("total_does_not_reconcile",),
        expected_amount=lambda r: r.stated_total,
    ),
    Layout(
        name="shipping_and_discount", render=shipping_and_discount, expected_path=Path.REVIEW, weight=1.0,
        tests="legitimate total with shipping and a discount; validate cannot model either",
        expected_issues=("total_does_not_reconcile",),
        notes=("expected issue documents a validator gap, not a bad receipt",),
    ),
    Layout(
        name="zero_total", render=zero_total, expected_path=Path.REVIEW,
        also_acceptable=(Path.SKIPPED,), weight=0.5,
        tests="a zero total is valid data but must not be banked silently",
        expected_issues=("amount_not_positive",),
        expected_amount=lambda r: 0.0, expected_tax=lambda r: 0.0,
    ),
    Layout(
        name="image_only", render=image_only, expected_path=Path.SKIPPED,
        also_acceptable=(Path.REVIEW,), weight=0.5,
        tests="nothing to extract; must not invent a number",
        expect_receipt=False,
        expected_amount=lambda r: None, expected_tax=lambda r: None,
        expected_vendor=lambda r: None,
        notes=("triage rejects it, which is right: there is no purchase record here",),
    ),
)

BY_NAME = {layout.name: layout for layout in REGISTRY}


def pick(rng: random.Random) -> Layout:
    return rng.choices(REGISTRY, weights=[layout.weight for layout in REGISTRY], k=1)[0]

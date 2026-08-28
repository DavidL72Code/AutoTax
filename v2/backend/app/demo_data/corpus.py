"""Building corpora out of receipts and layouts.

Public API is unchanged from the single-module version this replaces, so
`/api/demo` and the eval harness did not have to move: `demo_cases`,
`demo_emails`, `history_cases`, `history_emails`, `to_graph_email`.
"""
from __future__ import annotations

import hashlib
import random
import uuid
from datetime import datetime, timedelta
from typing import Any, Optional

from .layouts import BY_NAME, REGISTRY, pick
from .receipts import LineItem, Layout, Path, Receipt

# vendor, domain, cadence days, charged amount, (month price rises from, new price)
_RECURRING = [
    ("Netflix", "netflix.com", 30, 15.49, (3, 17.99)),
    ("Spotify", "spotify.com", 30, 11.99, None),
    ("Adobe", "adobe.com", 30, 59.99, (4, 69.99)),
    ("GitHub", "github.com", 30, 21.00, None),
]

# vendor, domain, spacing days, subtotal ceiling
_ONE_OFF = [
    ("Whole Foods", "wholefoods.com", 40, 190),
    ("Home Depot", "homedepot.com", 25, 320),
    ("Uber", "uber.com", 9, 48),
    ("Chipotle", "chipotle.com", 11, 34),
    ("Delta", "delta.com", 180, 640),
    ("CVS Pharmacy", "cvspharmacy.com", 8, 55),
    ("Best Buy", "bestbuy.com", 60, 410),
]

_ITEM_WORDS = (
    "Cotton tee", "USB-C cable", "Trail mix", "Notebook", "Espresso beans",
    "Phone case", "Batteries AA", "Desk lamp", "Socks 3-pack", "Hand soap",
    "Screwdriver set", "Paper towels", "Almond milk", "Sunscreen", "Headphones",
)

_CURRENCY_BY_LAYOUT = {
    "eur_comma_decimal": ("EUR", "€", 2, 1.0),
    "jpy_no_decimals": ("JPY", "¥", 0, 150.0),
}


def _items(rng: random.Random, target: float, *, minor_units: int) -> tuple[LineItem, ...]:
    """Line items that add up to roughly `target`. The receipt's subtotal is
    whatever they actually sum to — the target only sets the scale."""
    count = rng.randint(1, 4)
    shares = [rng.uniform(0.5, 1.5) for _ in range(count)]
    scale = target / sum(shares)
    items = []
    for share in shares:
        qty = rng.choice((1, 1, 1, 2, 3))
        unit = (share * scale) / qty
        unit = float(round(unit)) if minor_units == 0 else round(max(0.5, unit), 2)
        items.append(LineItem(rng.choice(_ITEM_WORDS), qty, unit))
    return tuple(items)


def _receipt(
    rng: random.Random,
    vendor: str,
    domain: str,
    when: datetime,
    target_subtotal: float,
    layout: Layout,
    *,
    exact_total: Optional[float] = None,
) -> Receipt:
    currency, symbol, minor_units, fx = _CURRENCY_BY_LAYOUT.get(layout.name, ("USD", "$", 2, 1.0))

    shipping = discount = tip = 0.0
    if layout.name == "shipping_and_discount":
        shipping = round(rng.uniform(4.99, 14.99), 2)
        discount = round(rng.uniform(2.0, 12.0), 2)

    if exact_total is not None:
        # A subscription charges a known amount, so work backwards to the
        # subtotal that produces it and keep the receipt to one line item.
        subtotal = round(exact_total / 1.0625, 2)
        items = (LineItem(f"{vendor} monthly plan", 1, subtotal),)
    else:
        items = _items(rng, target_subtotal * fx, minor_units=minor_units)

    receipt = Receipt(
        vendor=vendor, domain=domain, when=when.date(), items=items,
        shipping=shipping, discount=discount, tip=tip,
        currency=currency, symbol=symbol, minor_units=minor_units,
        order_ref=uuid.uuid4().hex[:10].upper(),
    )

    if layout.name == "mismatched_total":
        # Break it by more than validate's tolerance (5c or 2%, whichever is
        # larger) so the drift is unambiguous rather than a rounding artefact.
        drift = max(1.0, receipt.total * 0.12)
        receipt = Receipt(**{**receipt.__dict__, "corrupt_total": round(receipt.total + drift, 2)})

    return receipt


def _case(receipt: Receipt, layout: Layout) -> dict[str, Any]:
    subject = layout.subject(receipt) if layout.subject else f"Your receipt from {receipt.vendor}"
    sender = layout.sender(receipt) if layout.sender else f"no-reply@{receipt.domain}"

    amount = layout.expected_amount(receipt) if layout.expected_amount else receipt.stated_total
    tax = layout.expected_tax(receipt) if layout.expected_tax else receipt.tax
    vendor = layout.expected_vendor(receipt) if layout.expected_vendor else receipt.vendor

    return {
        "subject": subject,
        "from": sender,
        "date": receipt.stamp,
        "body": layout.render(receipt),
        # ground truth
        "vendor": vendor,
        "subtotal": receipt.subtotal,
        "tax": tax,
        "total": amount,
        # what the harness asserts beyond the values
        "layout": layout.name,
        "expected_path": layout.expected_path.value,
        "acceptable_paths": [layout.expected_path.value, *(p.value for p in layout.also_acceptable)],
        "expected_issues": list(layout.expected_issues),
        "expect_receipt": layout.expect_receipt,
        "currency": receipt.currency,
        "tolerate_currency_loss": layout.tolerate_currency_loss,
        "tests": layout.tests,
    }


def _email_id(case: dict) -> str:
    raw = "|".join([str(case.get("from", "")), str(case.get("subject", "")),
                    str(case.get("date", "")), str(case.get("body", ""))])
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def to_graph_email(case: dict) -> dict:
    return {
        "id": _email_id(case),
        "sender": case.get("from", ""),
        "subject": case.get("subject", ""),
        "date": case.get("date", ""),
        "body": case.get("body", ""),
    }


def _ensure_every_layout(cases: list[dict], rng: random.Random, make, *, demo: bool = False) -> list[dict]:
    """A layout that never gets sampled is a layout with no coverage. Any that
    the draw missed are appended explicitly."""
    seen = {case["layout"] for case in cases}
    for layout in REGISTRY:
        if demo and layout.eval_only:
            continue
        if layout.name not in seen:
            cases.append(make(layout))
    return cases


def _pick_for_demo(rng: random.Random) -> Layout:
    layout = pick(rng)
    while layout.eval_only:
        layout = pick(rng)
    return layout


def demo_cases(count: int = 10, seed: Optional[int] = 7) -> list[dict]:
    """Receipts with their ground truth and expected routing attached."""
    rng = random.Random(seed)
    today = datetime.utcnow()
    pool = _ONE_OFF + [(v, d, c, a) for v, d, c, a, _ in _RECURRING]

    def make(layout: Layout, index: int = 0) -> dict:
        vendor, domain, _, ceiling = pool[index % len(pool)]
        when = today - timedelta(days=rng.randint(0, 30))
        return _case(_receipt(rng, vendor, domain, when, rng.uniform(ceiling * 0.2, ceiling), layout), layout)

    cases = [make(pick(rng), i) for i in range(count)]
    cases = _ensure_every_layout(cases, rng, lambda layout: make(layout, rng.randrange(len(pool))))
    cases.sort(key=lambda case: case["date"])
    return cases


def demo_emails(count: int = 10, seed: Optional[int] = None) -> list[dict]:
    return [to_graph_email(case) for case in demo_cases(count, seed)]


def history_cases(months: int = 6, seed: Optional[int] = 11) -> list[dict]:
    """Six months of receipts containing recurring charges, a price rise and one
    duplicate billing — the patterns the Insights page is built to find. Layouts
    are drawn per receipt, so the same subscription arrives in different shapes,
    which is closer to a real mailbox than one template per vendor."""
    rng = random.Random(seed)
    today = datetime.utcnow()
    cases: list[dict] = []

    for index, (vendor, domain, cadence, amount, change) in enumerate(_RECURRING):
        for period in range(months):
            when = today - timedelta(days=cadence * (months - 1 - period), hours=index)
            charged = change[1] if change and period >= change[0] else amount
            # A subscription with a known price needs a layout that states a
            # total, or the planted price rise is not visible in the ledger.
            layout = _pick_for_demo(rng)
            while layout.expected_path is Path.REVIEW or layout.name == "no_explicit_total":
                layout = _pick_for_demo(rng)
            cases.append(_case(_receipt(rng, vendor, domain, when, charged, layout, exact_total=charged), layout))

    for index, (vendor, domain, spacing, ceiling) in enumerate(_ONE_OFF):
        day = 0
        while day < months * 30:
            when = today - timedelta(days=day)
            layout = _pick_for_demo(rng)
            cases.append(_case(_receipt(rng, vendor, domain, when, rng.uniform(ceiling * 0.2, ceiling), layout), layout))
            day += spacing + rng.randint(-2, 4)

    # A double billing: same vendor, same amount, next day, different message.
    plain = BY_NAME["plain_labeled"]
    for offset in (4, 3):
        when = today - timedelta(days=offset)
        cases.append(_case(_receipt(rng, "Uber", "uber.com", when, 41.20, plain, exact_total=41.20), plain))

    cases = _ensure_every_layout(
        cases, rng,
        lambda layout: _case(
            _receipt(rng, *(_ONE_OFF[rng.randrange(len(_ONE_OFF))][:2]),
                     today - timedelta(days=rng.randint(0, months * 30)), rng.uniform(12, 180), layout),
            layout,
        ),
        demo=True,
    )
    cases.sort(key=lambda case: case["date"])
    return cases


def history_emails(months: int = 6, seed: Optional[int] = 11) -> list[dict]:
    return [to_graph_email(case) for case in history_cases(months, seed)]

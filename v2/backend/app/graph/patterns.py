"""Deterministic extraction. Runs before any model call and, on well-formed
receipts, is the only thing that runs."""
from __future__ import annotations

import re
from typing import Optional

_TOTAL_LABEL = (
    r"grand\s+total|order\s+total|total\s+amount|amount\s+charged|amount\s+due|"
    r"balance\s+due(?:\s+now)?|total\s+paid|total\s+charged|charged|charge|total"
)
_STRONG_TOTAL_LABEL = (
    r"grand\s+total|order\s+total|total\s+amount|amount\s+charged|amount\s+due|"
    r"balance\s+due(?:\s+now)?|total\s+paid|total\s+charged"
)
_TAX_LABEL = (
    r"sales\s+tax|estimated\s+tax|tax\s+amount|tax\s+collected|tax\s+charged|"
    r"local\s+levy(?:\s*@[^:]+)?|vat|gst|hst|tax"
)
_SUBTOTAL_LABEL = r"subtotal|sub\s+total|subtotal\s+amount|item\s+total|merchandise\s+total"

_MONEY = r"\$?\s*([\d,]+\.\d{2})"
_PRE_TAX = re.compile(r"\b(?:before\s+tax|pre[-\s]?tax)\b", re.IGNORECASE)
_SUBTOTAL_CTX = re.compile(r"\b(?:subtotal|sub\s+total|before\s+tax|pre[-\s]?tax)\b", re.IGNORECASE)

_FINANCIAL_KW = re.compile(
    r"\$[\d,]+\.?\d*"
    r"|\b(?:total|tax|levy|subtotal|amount|charged|due|vendor|merchant|store|"
    r"receipt|invoice|balance|payment|paid)\b",
    re.IGNORECASE,
)

_ORDER_NUMBER = re.compile(
    r"(?:order\s*(?:#|number|id|no\.?|reference)|confirmation\s*(?:#|number|code)|receipt\s*(?:#|number))"
    r"\s*[:\-#]?\s*([A-Z0-9][A-Z0-9\-]{3,30})",
    re.IGNORECASE,
)
_BARE_ORDER_NUMBER = re.compile(r"\border\s+([0-9]{6,})\b", re.IGNORECASE)

_CARD = re.compile(
    r"\b(visa|mastercard|master\s?card|amex|american\s+express|discover|paypal|"
    r"apple\s+pay|google\s+pay|venmo|cash\s+app)\b(?:.{0,30}?(\d{4}))?",
    re.IGNORECASE,
)
_CARD_TAIL = re.compile(r"(?:ending\s+in|ending|\*{2,}|x{4,})\s*(\d{4})", re.IGNORECASE)

PROMO_SUBJECT = re.compile(
    r"\b(deals?|sale|% off|discount|coupon|promo|offer|flash|saving|app.only|"
    r"exclusive|download.to.get|limited.time|special.price|participating.store)\b",
    re.IGNORECASE,
)
PROMO_BODY = re.compile(
    r"you are receiving this email because you (are a registered member|subscribed|signed up)"
    r"|this is a marketing email"
    r"|to stop receiving (promotional|marketing)",
    re.IGNORECASE,
)
PURCHASE_SIGNAL = re.compile(
    r"\border\s*(#|number|id|confirmation)\b"
    r"|\b(?:order|grand)\s+total\b"
    r"|\border\s+[0-9]{6,}\b"
    r"|\btotal\s*(due|charged|paid|amount)\b"
    r"|\breceipt\s*(#|number|for)\b"
    r"|\byour\s*(order|purchase|payment)\s*(has been|was|is)\b"
    r"|\bamount\s*(charged|paid|due)\b",
    re.IGNORECASE,
)
SHIPPING_ONLY = re.compile(
    r"\b(has shipped|out for delivery|is on its way|tracking number|arriving (today|tomorrow)|"
    r"delivered|shipment)\b",
    re.IGNORECASE,
)


def money(raw: str) -> Optional[float]:
    try:
        return round(float(str(raw).replace(",", "").replace("$", "").strip()), 2)
    except (TypeError, ValueError):
        return None


def _labelled_value(text: str, label: str, *, skip: Optional[re.Pattern] = None) -> Optional[float]:
    """Find `label: $12.34` on a single line, tolerating a few separator styles."""
    patterns = (
        rf"^\s*(?:{label})\s*[:\-]\s*(?:USD?|US)?\s*{_MONEY}\b",
        rf"^\s*(?:{label})\s+(?:USD?|US)?\s*{_MONEY}\b",
        rf"^\s*{_MONEY}\s*(?:{label})\b",
    )
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or (skip and skip.search(line)):
            continue
        for pattern in patterns:
            match = re.search(pattern, line, re.IGNORECASE)
            if match:
                value = money(match.group(1))
                if value is not None:
                    return value
    return None


def extract_amount(text: str) -> Optional[float]:
    value = _labelled_value(text, _TOTAL_LABEL, skip=_SUBTOTAL_CTX)
    if value is not None:
        return value
    # HTML receipts often split label and value across table cells, so the two
    # land on different lines. Only unambiguous labels are safe here.
    match = re.search(rf"\b(?:{_STRONG_TOTAL_LABEL})\b\s*[:\-]?\s*(?:USD?|US)?\s*{_MONEY}\b", text, re.IGNORECASE)
    return money(match.group(1)) if match else None


def extract_tax(text: str) -> Optional[float]:
    value = _labelled_value(text, _TAX_LABEL, skip=_PRE_TAX)
    if value is not None:
        return value
    match = re.search(rf"(?<!before )(?<!pre )\btax[:\s\-]+{_MONEY}\b", text, re.IGNORECASE)
    return money(match.group(1)) if match else None


def extract_subtotal(text: str) -> Optional[float]:
    return _labelled_value(text, _SUBTOTAL_LABEL)


def extract_order_number(text: str) -> Optional[str]:
    for line in text.splitlines():
        match = _ORDER_NUMBER.search(line)
        if match:
            candidate = match.group(1).strip()
            if candidate.isdigit() and len(candidate) < 6:
                continue
            return candidate
    match = _BARE_ORDER_NUMBER.search(text)
    return match.group(1).strip() if match else None


def extract_payment_method(text: str) -> Optional[str]:
    match = _CARD.search(text)
    if not match:
        return None
    label = " ".join(word.capitalize() for word in match.group(1).split())
    label = {"Master Card": "Mastercard", "Amex": "American Express"}.get(label, label)
    tail = match.group(2) or ""
    if not tail:
        tail_match = _CARD_TAIL.search(text)
        tail = tail_match.group(1) if tail_match else ""
    return f"{label} ••{tail}" if tail else label


def financial_snippet(text: str, max_chars: int = 500) -> str:
    """Keep only lines that carry financial signal, plus one line of context on
    each side. Cuts prompt size roughly 70% versus sending the whole body."""
    lines = text.splitlines()
    keep: set[int] = set()
    for i, line in enumerate(lines):
        if _FINANCIAL_KW.search(line):
            keep.update(range(max(0, i - 1), min(len(lines), i + 2)))
    result = "\n".join(lines[i] for i in sorted(keep))
    return (result or text)[:max_chars]

"""Vendor identity and category lookup, the deterministic half of resolution.

The sender domain is the most reliable signal available, so it wins over
anything regex or a model produces. Only when the domain is a generic mail
relay (billing-updates.net, sendgrid.net, ...) does resolution fall through.
"""
from __future__ import annotations

import re
from typing import Optional

KNOWN_VENDORS: dict[str, tuple[str, str]] = {
    # domain token -> (display name, category)
    "adidas": ("Adidas", "Shopping"),
    "adobe": ("Adobe", "Subscriptions"),
    "airbnb": ("Airbnb", "Travel"),
    "aldi": ("Aldi", "Groceries"),
    "aliexpress": ("AliExpress", "Shopping"),
    "amazon": ("Amazon", "Shopping"),
    "americanairlines": ("American Airlines", "Travel"),
    "americanexpress": ("American Express", "Services"),
    "amex": ("American Express", "Services"),
    "apple": ("Apple", "Subscriptions"),
    "bestbuy": ("Best Buy", "Shopping"),
    "booking": ("Booking.com", "Travel"),
    "cashapp": ("Cash App", "Services"),
    "chase": ("Chase", "Services"),
    "chewy": ("Chewy", "Shopping"),
    "chipotle": ("Chipotle", "Dining"),
    "costco": ("Costco", "Groceries"),
    "cvs": ("CVS Pharmacy", "Health"),
    "cvspharmacy": ("CVS Pharmacy", "Health"),
    "delta": ("Delta", "Travel"),
    "dominos": ("Domino's", "Dining"),
    "doordash": ("DoorDash", "Dining"),
    "dropbox": ("Dropbox", "Subscriptions"),
    "dunkin": ("Dunkin'", "Dining"),
    "ebay": ("eBay", "Shopping"),
    "epicgames": ("Epic Games", "Entertainment"),
    "etsy": ("Etsy", "Shopping"),
    "expedia": ("Expedia", "Travel"),
    "fidelity": ("Fidelity", "Services"),
    "github": ("GitHub", "Subscriptions"),
    "grubhub": ("Grubhub", "Dining"),
    "homedepot": ("Home Depot", "Shopping"),
    "hulu": ("Hulu", "Entertainment"),
    "ikea": ("IKEA", "Shopping"),
    "instacart": ("Instacart", "Groceries"),
    "kohls": ("Kohl's", "Shopping"),
    "kroger": ("Kroger", "Groceries"),
    "lowes": ("Lowe's", "Shopping"),
    "lyft": ("Lyft", "Transport"),
    "macys": ("Macy's", "Shopping"),
    "microsoft": ("Microsoft", "Subscriptions"),
    "netflix": ("Netflix", "Entertainment"),
    "nike": ("Nike", "Shopping"),
    "nordstrom": ("Nordstrom", "Shopping"),
    "openai": ("OpenAI", "Subscriptions"),
    "paypal": ("PayPal", "Services"),
    "petco": ("Petco", "Shopping"),
    "playstation": ("PlayStation", "Entertainment"),
    "postmates": ("Postmates", "Dining"),
    "publix": ("Publix", "Groceries"),
    "safeway": ("Safeway", "Groceries"),
    "sephora": ("Sephora", "Shopping"),
    "shopify": ("Shopify", "Services"),
    "southwest": ("Southwest Airlines", "Travel"),
    "spotify": ("Spotify", "Subscriptions"),
    "square": ("Square", "Services"),
    "starbucks": ("Starbucks", "Dining"),
    "steam": ("Steam", "Entertainment"),
    "steampowered": ("Steam", "Entertainment"),
    "stripe": ("Stripe", "Services"),
    "target": ("Target", "Shopping"),
    "traderjoes": ("Trader Joe's", "Groceries"),
    "uber": ("Uber", "Transport"),
    "ubereats": ("Uber Eats", "Dining"),
    "ulta": ("Ulta Beauty", "Shopping"),
    "united": ("United Airlines", "Travel"),
    "venmo": ("Venmo", "Services"),
    "walgreens": ("Walgreens", "Health"),
    "walmart": ("Walmart", "Shopping"),
    "wayfair": ("Wayfair", "Shopping"),
    "wholefoods": ("Whole Foods", "Groceries"),
    "wholefoodsmarket": ("Whole Foods", "Groceries"),
    "xbox": ("Xbox", "Entertainment"),
    "zoom": ("Zoom", "Subscriptions"),
}

CATEGORIES = (
    "Groceries", "Dining", "Transport", "Shopping", "Subscriptions",
    "Travel", "Utilities", "Health", "Entertainment", "Services", "Other",
)

# Mail relays and generic mailbox names, never a merchant identity.
GENERIC_TOKENS = {
    "account", "alerts", "billing", "billing-updates", "email", "gmail", "google",
    "hello", "hotmail", "info", "invoice", "invoices", "mail", "mailer", "mailers",
    "mailgun", "mandrillapp", "message", "messages", "news", "no-reply", "noreply",
    "notification", "notifications", "outlook", "pay", "payments", "receipt",
    "receipts", "sendgrid", "sparkpostmail", "support", "service", "team",
    "transaction", "transactions", "updates", "yahoo",
}

_GENERIC = {re.sub(r"[^a-z0-9]", "", token) for token in GENERIC_TOKENS}

# Substrings that mark a domain as a mail relay rather than a merchant, e.g.
# "billing-updates.net" or "order-notify.com".
_GENERIC_PARTS = re.compile(
    r"billing|invoic|receipt|notif|update|alert|mailer|noreply|no-reply|"
    r"transact|payment|confirm|delivery|smtp|relay|cdn|email|mail\b"
)

# Payment processors: real senders, but they relay someone else's purchase, so
# the merchant still has to come from the body.
PROCESSORS = {"paypal", "stripe", "square", "venmo", "cashapp"}

_STOP_WORDS = {
    "you", "your", "purchase", "order", "receipt", "merchant", "vendor",
    "confirmation", "summary", "support", "service", "account", "payment", "the",
}

_VENDOR_PHRASES = (
    r"(?:receipt|invoice)\s+from\s+([A-Za-z0-9&'’\.\- ]{2,40})",
    r"(?:vendor|merchant|store|sold\s+by)\s*[:\-]\s*([A-Za-z0-9&'’\.\- ]{2,40})",
    r"(?:payment\s+to|paid\s+to|purchase\s+at|order\s+from)\s+([A-Za-z0-9&'’\.\- ]{2,40})",
    r"thanks?\s+for\s+(?:shopping|ordering|your\s+order)\s+(?:at|with|from)\s+([A-Za-z0-9&'’\.\- ]{2,40})",
)


def _tokens(sender: str) -> list[str]:
    match = re.search(r"@([a-z0-9.\-]+\.[a-z]{2,})", (sender or "").lower())
    if not match:
        return []
    parts = match.group(1).split(".")
    return [re.sub(r"[^a-z0-9]", "", part) for part in parts[:-1]]


def from_sender(sender: str) -> tuple[Optional[str], Optional[str], bool]:
    """Return (vendor, category, is_processor). Vendor is None for relay domains."""
    for token in reversed(_tokens(sender)):
        if not token or token in _GENERIC or _GENERIC_PARTS.search(token):
            continue
        if token in KNOWN_VENDORS:
            name, category = KNOWN_VENDORS[token]
            return name, category, token in PROCESSORS
        return token.replace("-", " ").title(), None, False
    return None, None, False


def from_text(subject: str, body: str) -> Optional[str]:
    text = f"{subject or ''}\n{body or ''}"
    for token, (name, _) in KNOWN_VENDORS.items():
        if re.search(rf"\b{re.escape(name.lower())}\b", text.lower()):
            if token in PROCESSORS:
                continue
            return name
    for pattern in _VENDOR_PHRASES:
        for match in re.finditer(pattern, text, re.IGNORECASE):
            candidate = re.sub(r"\s+", " ", match.group(1) or "").strip(" -:;,.")
            candidate = re.split(r"[|\n]|\s{2,}", candidate)[0].strip(" -:;,.")
            if not (2 <= len(candidate) <= 40) or not re.search(r"[A-Za-z]", candidate):
                continue
            if all(word in _STOP_WORDS for word in candidate.lower().split()):
                continue
            return candidate
    return None


def category_for(vendor: str) -> Optional[str]:
    key = re.sub(r"[^a-z0-9]", "", (vendor or "").lower())
    for token, (name, category) in KNOWN_VENDORS.items():
        if key == token or key == re.sub(r"[^a-z0-9]", "", name.lower()):
            return category
    return None

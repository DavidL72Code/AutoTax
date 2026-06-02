from .parsers.paypal_parser import paypal_parser
from .parsers.amazon_parser import amazon_parser
from .parsers.generic_parser import generic_parser
from .database import SessionLocal 
from .models import Vendor
import re
from .vendor_normalize import normalize_vendor_name

def _contains_word(text: str, word: str) -> bool:
    if not text or not word:
        return False
    return re.search(rf"\b{re.escape(word.lower())}\b", text.lower()) is not None

_PROMO_SUBJECT = re.compile(
    r'\b(deals?|sale|% off|discount|coupon|promo|offer|flash|saving|app.only|exclusive|download.to.get|limited.time|special.price|participating.store)\b',
    re.IGNORECASE,
)
# NOTE: do not include a bare "unsubscribe" here — nearly every commercial
# email (including legitimate receipts) has an unsubscribe link in its footer,
# so it is not a reliable marketing signal and was dropping real receipts.
_PROMO_BODY = re.compile(
    r'you are receiving this email because you (are a registered member|subscribed|signed up)'
    r'|this is a marketing email'
    r'|to stop receiving (promotional|marketing)',
    re.IGNORECASE,
)
_PURCHASE_SIGNALS = re.compile(
    r'\border\s*(#|number|id|confirmation)\b'
    r'|\b(?:order|grand)\s+total\b'                  # "Order total $11.60" / "Grand total"
    r'|\border\s+[0-9]{6,}\b'                         # "order 8210689700343416"
    r'|\btotal\s*(due|charged|paid|amount)\b'
    r'|\breceipt\s*(#|number|for)\b'
    r'|\byour\s*(order|purchase|payment)\s*(has been|was|is)\b'
    r'|\bamount\s*(charged|paid|due)\b',
    re.IGNORECASE,
)

def _is_promotional(subject: str, body: str) -> bool:
    """Return True if this email looks like marketing/ads rather than a real receipt."""
    has_promo_subject = bool(_PROMO_SUBJECT.search(subject or ''))
    has_promo_body = bool(_PROMO_BODY.search(body or ''))
    has_purchase_signal = bool(_PURCHASE_SIGNALS.search(body or '') or _PURCHASE_SIGNALS.search(subject or ''))
    # Promotional if it has promo signals AND no clear purchase evidence
    return (has_promo_subject or has_promo_body) and not has_purchase_signal

def parser_select(email_data:dict)->dict:
    email_body=email_data.get('body','')
    email_from=email_data.get('from','').lower()
    email_subject=email_data.get('subject','').lower()
    email_id=email_data.get('id')
    email_date=email_data.get('date')

    if _is_promotional(email_subject, email_body):
        print(f"[SKIP] Promotional/marketing email: {email_subject[:60]}")
        return None

    # Sender domain is the most reliable signal — always use it when available
    vendor_name = vendor_from_sender_domain(email_from)
    vendor_locked = bool(vendor_name)   # don't let AI override a domain-derived vendor

    if not vendor_name:
        vendor_name = vendor_regex_search(email_subject, email_body)

    normalized_vendor = (
        normalize_vendor_name(vendor_name, email_data=email_data)
        if vendor_name else None
    )

    if normalized_vendor == "PayPal":
        parsed = paypal_parser(email_subject,email_body, email_id,email_date, normalized_vendor)
    elif normalized_vendor == "Amazon":
        parsed = amazon_parser(email_subject,email_body, email_id,email_date,normalized_vendor)
    else:
        parsed = generic_parser(email_subject,email_body, email_id,email_date, normalized_vendor)

    if isinstance(parsed, dict):
        meta = parsed.get("_meta") or {}
        if "vendor_ai_called" not in meta:
            meta["vendor_ai_called"] = False
        if "vendor_ai_success" not in meta:
            meta["vendor_ai_success"] = False
        if "vendor_ai_raw" not in meta:
            meta["vendor_ai_raw"] = ""
        parsed["_meta"] = meta
        # Sender domain vendor always wins — never let regex/AI override it
        if vendor_locked and normalized_vendor:
            parsed["vendor"] = normalized_vendor
    return parsed

def vendor_search(email_from: str, subject: str, body: str) -> str:
    if 'paypal.com' in email_from:
        return 'PayPal'
    elif 'amazon.com' in email_from or 'amazon.co' in email_from:
        return 'Amazon'
    elif 'aliexpress.com' in email_from or 'alibaba.com' in email_from:
        return 'AliExpress'
    elif 'ebay.com' in email_from:
        return 'eBay'
    elif 'uber.com' in email_from and 'eats' in subject:
        return 'UberEats'
    elif 'uber.com' in email_from:
        return 'Uber'
    elif 'doordash.com' in email_from:
        return 'DoorDash'
    elif 'grubhub.com' in email_from:
        return 'Grubhub'
    elif 'instacart.com' in email_from:
        return 'Instacart'
    elif 'chase.com' in email_from:
        return 'Chase'
    elif 'fidelity.com' in email_from:
        return 'Fidelity Investments'
    elif 'americanexpress.com' in email_from or 'amex' in email_from:
        return 'American Express'
    elif 'starbucks.com' in email_from:
        return 'Starbucks'
    elif 'apple.com' in email_from:
        return 'Apple'
    elif 'netflix.com' in email_from:
        return 'Netflix'
    elif 'spotify.com' in email_from:
        return 'Spotify'
    elif 'google.com' in email_from and ('payment' in subject or 'receipt' in subject or 'order' in subject):
        return 'Google'
    elif 'walmart.com' in email_from:
        return 'Walmart'
    elif 'target.com' in email_from:
        return 'Target'
    elif 'bestbuy.com' in email_from:
        return 'Best Buy'
    elif 'etsy.com' in email_from:
        return 'Etsy'
    elif 'shopify.com' in email_from:
        return 'Shopify'
    
    if _contains_word(subject, 'paypal'):
        return "Paypal"
    elif _contains_word(subject, 'amazon'):
        return "Amazon"
    elif _contains_word(subject, 'chase'):
        return "Chase"
    elif _contains_word(subject, 'fidelity'):
        return "Fidelity Investments"
    elif _contains_word(subject, 'american express') or _contains_word(subject, 'amex'):
        return "American Express"
    elif _contains_word(subject, 'starbucks'):
        return "Starbucks"
    
    # fallback: try body keywords for common vendors
    if _contains_word(body, 'paypal'):
        return "Paypal"
    elif _contains_word(body, 'amazon'):
        return "Amazon"
    elif _contains_word(body, 'chase'):
        return "Chase"
    elif _contains_word(body, 'fidelity'):
        return "Fidelity Investments"
    elif _contains_word(body, 'american express') or _contains_word(body, 'amex'):
        return "American Express"
    elif _contains_word(body, 'starbucks'):
        return "Starbucks"
    
    return None

def vendor_regex_search(subject: str, body: str) -> str:
    text = f"{subject or ''}\n{body or ''}"
    patterns = [
        r'(?:receipt\s+from|from)\s+([A-Za-z0-9&\'\.\- ]{2,50})',
        r'(?:vendor|merchant)\s*[:\-]\s*([A-Za-z0-9&\'\.\- ]{2,50})',
        r'(?:payment\s+to|paid\s+to)\s+([A-Za-z0-9&\'\.\- ]{2,50})',
    ]
    stop_tokens = {
        "you", "your", "purchase", "order", "receipt", "merchant", "vendor",
        "confirmation", "summary", "support", "service", "account", "payment",
    }

    for pattern in patterns:
        for match in re.finditer(pattern, text, re.IGNORECASE):
            candidate = (match.group(1) or "").strip()
            candidate = re.sub(r'\s+', ' ', candidate).strip(" -:;,.")
            if not candidate:
                continue

            # Trim at common delimiters to avoid pulling full sentences.
            candidate = re.split(r'[\|\n]|(?:\s{2,})', candidate)[0].strip(" -:;,.")
            if len(candidate) < 2 or len(candidate) > 40:
                continue

            words = candidate.lower().split()
            if words and all(w in stop_tokens for w in words):
                continue

            # Basic sanity: must contain at least one alphabetic character.
            if not re.search(r'[A-Za-z]', candidate):
                continue
            return candidate

    return None

_DOMAIN_VENDOR_MAP = {
    "paypal": "PayPal",
    "amazon": "Amazon",
    "aliexpress": "AliExpress",
    "alibaba": "Alibaba",
    "ebay": "eBay",
    "uber": "Uber",
    "ubereats": "Uber Eats",
    "doordash": "DoorDash",
    "grubhub": "Grubhub",
    "instacart": "Instacart",
    "starbucks": "Starbucks",
    "apple": "Apple",
    "netflix": "Netflix",
    "spotify": "Spotify",
    "walmart": "Walmart",
    "target": "Target",
    "bestbuy": "Best Buy",
    "etsy": "Etsy",
    "shopify": "Shopify",
    "stripe": "Stripe",
    "square": "Square",
    "chase": "Chase",
    "amex": "American Express",
    "americanexpress": "American Express",
    "fidelity": "Fidelity",
    "venmo": "Venmo",
    "cashapp": "Cash App",
    "airbnb": "Airbnb",
    "booking": "Booking.com",
    "expedia": "Expedia",
    "lyft": "Lyft",
    "postmates": "Postmates",
    "chewy": "Chewy",
    "wayfair": "Wayfair",
    "homedepot": "Home Depot",
    "lowes": "Lowe's",
    "costco": "Costco",
    "kohls": "Kohl's",
    "macys": "Macy's",
    "nordstrom": "Nordstrom",
    "gap": "Gap",
    "nike": "Nike",
    "adidas": "Adidas",
    "steam": "Steam",
    "epicgames": "Epic Games",
    "playstation": "PlayStation",
    "xbox": "Xbox",
    "microsoft": "Microsoft",
    "adobe": "Adobe",
    "dropbox": "Dropbox",
    "github": "GitHub",
}

_GENERIC_SENDER_TOKENS = {
    "gmail", "google", "outlook", "yahoo", "hotmail", "mail",
    "receipt", "receipts", "billing", "invoice", "invoices",
    "notification", "notifications", "noreply", "no-reply",
    "updates", "alerts", "support", "service", "message", "messages",
    "mailer", "mailers", "transactions", "transaction", "pay", "payments",
    "info", "hello", "team", "news", "account",
}

def vendor_from_sender_domain(email_from: str) -> str:
    if not email_from:
        return None
    match = re.search(r'@([a-z0-9.-]+\.[a-z]{2,})', email_from.lower())
    if not match:
        return None
    domain = match.group(1)
    parts = domain.split(".")
    # Walk from second-to-last part leftward to find the first non-generic token
    for i in range(len(parts) - 2, -1, -1):
        core = re.sub(r"[^a-z0-9]", "", parts[i])
        if not core or core in _GENERIC_SENDER_TOKENS:
            continue
        # Check the known map first for proper capitalisation
        if core in _DOMAIN_VENDOR_MAP:
            return _DOMAIN_VENDOR_MAP[core]
        # Fall back to title-cased core if it's not a noise token
        return core.replace("-", " ").title()
    return None

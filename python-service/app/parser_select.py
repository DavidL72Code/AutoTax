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

def parser_select(email_data:dict)->dict:
    email_body=email_data.get('body','')
    email_from=email_data.get('from','').lower()
    email_subject=email_data.get('subject','').lower()
    email_id=email_data.get('id')
    email_date=email_data.get('date')
    vendor_name=vendor_search(email_from,email_subject,email_body)

    if not vendor_name:
        vendor_name = vendor_regex_search(email_subject, email_body)

    if not vendor_name:
        vendor_name = vendor_from_sender_domain(email_from)

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
        # Vendor AI is now handled in generic_parser as part of one combined AI call.
        if "vendor_ai_called" not in meta:
            meta["vendor_ai_called"] = False
        if "vendor_ai_success" not in meta:
            meta["vendor_ai_success"] = False
        if "vendor_ai_raw" not in meta:
            meta["vendor_ai_raw"] = ""
        parsed["_meta"] = meta
    return parsed

def vendor_search(email_from: str, subject: str, body: str) -> str:
    if 'paypal.com' in email_from:
        return 'PayPal'
    elif 'amazon.com' in email_from or "amazon.co" in email_from:
        return 'Amazon'
    elif 'uber.com' in email_from and 'eats' in subject:
        return 'UberEats'
    elif 'chase.com' in email_from:
        return 'Chase'
    elif 'fidelity.com' in email_from:
        return 'Fidelity Investments'
    elif 'americanexpress.com' in email_from or 'amex' in email_from:
        return 'American Express'
    elif 'starbucks.com' in email_from:
        return 'Starbucks'
    
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

def vendor_from_sender_domain(email_from: str) -> str:
    if not email_from:
        return None
    match = re.search(r'@([a-z0-9.-]+\.[a-z]{2,})', email_from.lower())
    if not match:
        return None
    domain = match.group(1)
    host = domain.split(".")
    if len(host) < 2:
        return None
    core = host[-2]
    if core in {"co", "com", "org", "net"} and len(host) >= 3:
        core = host[-3]
    core = re.sub(r"[^a-z0-9-]", "", core)
    generic_sender_tokens = {
        "gmail", "google", "outlook", "yahoo", "hotmail", "mail",
        "receipt", "receipts", "billing", "invoice", "invoices",
        "notification", "notifications", "noreply", "no-reply",
        "updates", "alerts", "support", "service", "message", "messages",
        "mailer", "mailers", "transactions", "transaction", "pay", "payments",
    }
    if not core:
        return None
    core_tokens = [t for t in core.split("-") if t]
    if core in generic_sender_tokens:
        return None
    if core_tokens and all(t in generic_sender_tokens for t in core_tokens):
        return None
    return core.replace("-", " ").title()

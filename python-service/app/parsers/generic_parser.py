from __future__ import annotations

import re
from dateutil import parser as date_parser
import json
from typing import Optional
from ..ai_client import generate_text


_FINANCIAL_KW = re.compile(
    r'\$[\d,]+\.?\d*'
    r'|\b(?:total|tax|levy|subtotal|amount|charged|due|vendor|merchant|store|receipt|invoice|balance|payment|paid)\b',
    re.IGNORECASE,
)

def _extract_financial_lines(text: str, max_chars: int = 500) -> str:
    """Return only lines likely to contain financial data, plus one line of context each side."""
    lines = text.splitlines()
    keep: set[int] = set()
    for i, line in enumerate(lines):
        if _FINANCIAL_KW.search(line):
            keep.update(range(max(0, i - 1), min(len(lines), i + 2)))
    result = "\n".join(lines[i] for i in sorted(keep))
    return result[:max_chars] if result else text[:max_chars]


def _parse_currency_value(raw_value: str) -> Optional[float]:
    try:
        return float(str(raw_value).replace(',', '').strip())
    except Exception:
        return None


def _extract_amount_value(email_text: str) -> Optional[float]:
    amount_patterns = [
        r'^\s*(?:grand\s+total|order\s+total|total\s+amount|amount\s+charged|amount\s+due|balance\s+due(?:\s+now)?|charged|charge|total)\s*[:\-]\s*\$?([\d,]+\.\d{2})\b',
        r'^\s*(?:grand\s+total|order\s+total|total\s+amount|amount\s+charged|amount\s+due|balance\s+due(?:\s+now)?|charged|charge|total)\s+\$?([\d,]+\.\d{2})\b',
        r'^\s*\$?\s*([\d,]+\.\d{2})\s*(?:grand\s+total|order\s+total|total|charged)\b',
    ]
    ignored_amount_context = re.compile(r'\b(?:subtotal|sub\s+total|before\s+tax|pre[-\s]?tax)\b', re.IGNORECASE)

    for raw_line in email_text.splitlines():
        line = raw_line.strip()
        if not line or ignored_amount_context.search(line):
            continue
        for pattern in amount_patterns:
            match = re.search(pattern, line, re.IGNORECASE)
            if not match:
                continue
            parsed_value = _parse_currency_value(match.group(1))
            if parsed_value is not None:
                return parsed_value

    # Fallback: in HTML receipts the label and amount often sit in separate
    # table cells, landing on separate lines. Search the whole text and allow
    # a whitespace/newline gap between a *strong* total label and the amount.
    # Only unambiguous "final total" labels here — bare "total" is too risky
    # in a whole-text search (it would match line items like "Item total").
    cross_line = re.search(
        r'\b(?:grand\s+total|order\s+total|total\s+amount|amount\s+charged|'
        r'amount\s+due|balance\s+due(?:\s+now)?)\b'
        r'\s*[:\-]?\s*(?:USD?|US)?\s*\$?\s*([\d,]+\.\d{2})\b',
        email_text,
        re.IGNORECASE,
    )
    if cross_line:
        return _parse_currency_value(cross_line.group(1))
    return None


def _extract_tax_value(email_text: str) -> Optional[float]:
    tax_patterns = [
        r'^\s*(?:sales\s+tax|estimated\s+tax|tax\s+amount|tax\s+collected|local\s+levy(?:\s*@[^:]+)?|vat|gst|hst|tax)\s*[:\-]\s*\$?([\d,]+\.\d{2})\b',
        r'^\s*(?:sales\s+tax|estimated\s+tax|tax\s+amount|tax\s+collected|local\s+levy(?:\s*@[^:]+)?|vat|gst|hst|tax)\s+\$?([\d,]+\.\d{2})\b',
    ]
    ignored_tax_context = re.compile(r'\b(?:before\s+tax|pre[-\s]?tax)\b', re.IGNORECASE)

    for raw_line in email_text.splitlines():
        line = raw_line.strip()
        if not line or ignored_tax_context.search(line):
            continue
        for pattern in tax_patterns:
            match = re.search(pattern, line, re.IGNORECASE)
            if not match:
                continue
            parsed_value = _parse_currency_value(match.group(1))
            if parsed_value is not None:
                return parsed_value

    fallback_match = re.search(
        r'(?<!before )(?<!pre )\btax[:\s\-]+\$?([\d,]+\.\d{2})\b',
        email_text,
        re.IGNORECASE,
    )
    if fallback_match:
        return _parse_currency_value(fallback_match.group(1))
    return None


_ORDER_NUMBER_RE = re.compile(
    r'(?:order\s*(?:#|number|id|no\.?|reference)|confirmation\s*(?:#|number|code)|receipt\s*(?:#|number))'
    r'\s*[:\-#]?\s*([A-Z0-9][A-Z0-9\-]{3,30})',
    re.IGNORECASE,
)

# Bare "order 8210689700343416" with no #/number/id keyword (e.g. AliExpress).
# Require 6+ digits so it can't match words like "order confirmed" / "order total".
_BARE_ORDER_NUMBER_RE = re.compile(r'\border\s+([0-9]{6,})\b', re.IGNORECASE)

def _extract_order_number(text: str) -> str | None:
    for line in text.splitlines():
        m = _ORDER_NUMBER_RE.search(line)
        if m:
            candidate = m.group(1).strip()
            # Skip purely numeric short strings that are likely prices or zip codes
            if candidate.isdigit() and len(candidate) < 6:
                continue
            return candidate
    # Fallback: keyword-less "order <digits>"
    for line in text.splitlines():
        m = _BARE_ORDER_NUMBER_RE.search(line)
        if m:
            return m.group(1).strip()
    return None

def regex_parsing(email_text: str) -> dict:
    regex_info = {}
    amount_value = _extract_amount_value(email_text)
    if amount_value is not None:
        regex_info['amount'] = amount_value
    tax_value = _extract_tax_value(email_text)
    if tax_value is not None:
        regex_info["tax"] = tax_value
    order_number = _extract_order_number(email_text)
    if order_number:
        regex_info["order_number"] = order_number
    return regex_info


def _build_base_result(
    email_subject: str,
    email_text: str,
    email_id: str,
    email_date: str,
    vendor_name: str,
) -> tuple[dict, list[str]]:
    """Run regex pass and return (result_dict, missing_fields)."""
    result = {
        'email_id': email_id,
        'vendor': vendor_name or "Unknown",
        'email body': email_text,
        'amount': 0.0,
        'date': email_date,
        'tax': 0.0,
        '_meta': {
            'amount_regex_found': False,
            'tax_regex_found': False,
            'ai_amount_tax_called': False,
            'ai_amount_found': False,
            'ai_tax_found': False,
            'vendor_ai_called': False,
            'vendor_ai_success': False,
            'vendor_ai_raw': '',
            'ai_amount_tax_raw': '',
        }
    }

    regex_result = regex_parsing(email_text)
    result.update(regex_result)

    # Order numbers often live in the subject line (e.g. AliExpress
    # "Order 8210701771043416: order shipped") rather than the body.
    # Scan the subject too so multi-status emails for one order dedup correctly.
    if not regex_result.get('order_number') and email_subject:
        subject_order = _extract_order_number(email_subject)
        if subject_order:
            result['order_number'] = subject_order

    has_amount = regex_result.get('amount') is not None
    has_tax = regex_result.get('tax') is not None
    result['_meta']['amount_regex_found'] = bool(has_amount)
    result['_meta']['tax_regex_found'] = bool(has_tax)

    missing_info = []
    if not vendor_name or str(vendor_name).strip().lower() == "unknown":
        missing_info.append('vendor')
    if not has_amount:
        missing_info.append('amount')
    if not has_tax:
        missing_info.append('tax')

    return result, missing_info


def _apply_ai_result(result: dict, ai_result: dict, missing_info: list[str]):
    """Merge AI result into a parsed result dict in-place."""
    raw = ai_result.get('_ai_raw') or ''
    result['_meta']['ai_amount_tax_raw'] = raw
    result['_meta']['vendor_ai_raw'] = raw

    if ai_result.get('vendor') and 'vendor' in missing_info:
        result['vendor'] = str(ai_result['vendor']).strip()
        result['_meta']['vendor_ai_success'] = True

    if ai_result.get('amount') and 'amount' in missing_info:
        result['amount'] = ai_result['amount']
        result['_meta']['ai_amount_found'] = True

    if ai_result.get('tax') and not result.get('tax'):
        result['tax'] = ai_result['tax']
        result['_meta']['ai_tax_found'] = True


def batch_ai_search(items: list[dict]) -> list[Optional[dict]]:
    """
    Send multiple emails to the LLM in one call.

    items: list of {"subject": str, "body": str, "missing": list[str]}
    Returns list of ai_result dicts in the same order (None on per-item failure).
    Falls back to all-None if the whole call fails.
    """
    if not items:
        return []

    receipt_blocks = []
    for i, item in enumerate(items, start=1):
        subject = (item.get("subject") or "")[:120]
        body = _extract_financial_lines(item.get("body") or "")
        missing = ", ".join(item.get("missing") or ["vendor", "amount", "tax"])
        receipt_blocks.append(
            f"[{i}] need={missing}\n{subject}\n{body}"
        )

    receipts_text = "\n\n".join(receipt_blocks)
    max_tokens = max(70 * len(items), 200)

    prompt = (
        f'Extract vendor, amount, tax from each receipt. '
        f'Return ONLY a JSON array of {len(items)} objects: [{{"vendor":null,"amount":null,"tax":null}},...]\n'
        f'vendor=store name; amount=final total (no $); tax=levy/tax (no $); '
        f'"balance due now"=amount, "local levy"=tax. Use null if not found.\n\n'
        f'{receipts_text}\n\nJSON array:'
    )

    ai_text = ""
    try:
        ai_text = generate_text(prompt, temperature=0.1, max_output_tokens=max_tokens)
        match = re.search(r'\[.*\]', ai_text, re.DOTALL)
        if not match:
            print(f"⚠️ Batch AI: no JSON array in response")
            return [None] * len(items)

        data = json.loads(match.group(0))
        if not isinstance(data, list):
            return [None] * len(items)

        results: list[Optional[dict]] = []
        for entry in data[:len(items)]:
            if not isinstance(entry, dict):
                results.append(None)
                continue
            r: dict = {"_ai_raw": ai_text}
            if entry.get("vendor"):
                v = str(entry["vendor"]).strip().split('\n')[0].strip('"\'.,;: ')
                if v:
                    r["vendor"] = v
            if entry.get("amount") is not None:
                try:
                    r["amount"] = float(entry["amount"])
                except (TypeError, ValueError):
                    pass
            if entry.get("tax") is not None:
                try:
                    r["tax"] = float(entry["tax"])
                except (TypeError, ValueError):
                    pass
            results.append(r)

        while len(results) < len(items):
            results.append(None)
        return results

    except Exception as e:
        print(f"Batch AI search failed: {e}")
        return [None] * len(items)


def parse_generic_emails_batch(items: list[dict]) -> list[dict]:
    """
    Two-pass batch parser for generic emails.

    items: list of dicts with keys:
        email_subject, email_text, email_id, email_date, vendor_name

    Pass 1 — regex on every email.
    Pass 2 — one LLM call for all emails that still have missing fields.
    Returns list of parsed result dicts in the same order.
    """
    base_results: list[tuple[dict, list[str]]] = []
    needs_ai: list[tuple[int, dict]] = []  # (result_index, original_item)

    for item in items:
        result, missing_info = _build_base_result(
            item['email_subject'],
            item['email_text'],
            item['email_id'],
            item['email_date'],
            item['vendor_name'],
        )
        base_results.append((result, missing_info))
        if missing_info:
            needs_ai.append((len(base_results) - 1, item))

    if needs_ai:
        batch_inputs = [
            {
                "subject": items[i]['email_subject'],
                "body": items[i]['email_text'],
                "missing": base_results[i][1],
            }
            for i, _ in needs_ai
        ]
        ai_outputs = batch_ai_search(batch_inputs)

        for (idx, _), ai_result in zip(needs_ai, ai_outputs):
            result, missing_info = base_results[idx]
            result['_meta']['ai_amount_tax_called'] = any(f in missing_info for f in ['amount', 'tax'])
            result['_meta']['vendor_ai_called'] = 'vendor' in missing_info
            if ai_result:
                _apply_ai_result(result, ai_result, missing_info)

    return [r for r, _ in base_results]


def generic_parser(email_subject: str, email_text: str, email_id: str, email_date: str, vendor_name: str) -> dict:
    result, missing_info = _build_base_result(email_subject, email_text, email_id, email_date, vendor_name)

    if missing_info:
        result['_meta']['ai_amount_tax_called'] = any(f in missing_info for f in ['amount', 'tax'])
        result['_meta']['vendor_ai_called'] = 'vendor' in missing_info
        print(f" Regex failed for {vendor_name}:{','.join(missing_info)} missing")
        print("\n Using AI to extract missing fields\n")

        ai_result = ai_search(email_subject, email_text, missing_info)
        _apply_ai_result(result, ai_result, missing_info)
    else:
        print(f"Regex successful for {vendor_name}")

    return result


def ai_search(email_subject: str, email_text: str, missing_fields: list) -> dict:
    ai_text = ""
    try:
        field_list = ', '.join(missing_fields)
        relevant_body = _extract_financial_lines(email_text)
        prompt = (
            f'Extract {field_list} from this receipt. '
            f'Return ONLY JSON: {{"vendor":"","amount":0.0,"tax":0.0}}\n'
            f'Rules: vendor=store name; amount=final total (no $); tax=levy/tax (no $); '
            f'"balance due now"=amount, "local levy"=tax, "merchandise sum"=subtotal.\n\n'
            f'{email_subject}\n{relevant_body}'
        )
        ai_text = generate_text(
            prompt,
            temperature=0.1,
            max_output_tokens=80,
        )

        match = re.search(r'\{.*\}', ai_text, re.DOTALL)
        if match:
            clean_json = match.group(0)
            ai_data = json.loads(clean_json)
        else:
            print(f"⚠️ AI returned text without a JSON block: {ai_text[:50]}...")
            return {"_ai_raw": ai_text}

        ai_info = {}
        ai_info['_ai_raw'] = ai_text
        if 'vendor' in missing_fields and ai_data.get('vendor'):
            vendor = str(ai_data.get('vendor')).strip()
            vendor = vendor.split('\n')[0].strip().strip('"\'. ,;:')
            if vendor:
                ai_info['vendor'] = vendor

        if 'amount' in missing_fields and ai_data.get('amount'):
            ai_info['amount'] = float(ai_data['amount'])

        if 'date' in missing_fields and ai_data.get('date'):
            try:
                ai_info['date'] = date_parser.parse(ai_data['date'])
            except Exception:
                pass

        if ai_data.get('tax'):
            ai_info['tax'] = float(ai_data['tax'])

        print(f" AI extracted: {', '.join(ai_info.keys())}")
        return ai_info

    except Exception as e:
        print(f"AI extraction failed: {e}")
        if ai_text:
            return {"_ai_raw": f"ERROR: {e} | RAW: {ai_text}"}
        return {"_ai_raw": f"ERROR: {e}"}

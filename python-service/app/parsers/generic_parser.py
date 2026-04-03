import re 
from datetime import datetime
from dateutil import parser as date_parser
import json
from typing import Optional
from ..ai_client import generate_text


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

def generic_parser(email_subject:str ,email_text:str,email_id:str,email_date:str,vendor_name:str)-> dict:
    result={
        'email_id': email_id,
        'vendor': vendor_name or "Unknown",
        'email body': email_text,
        'amount':0.0,
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
    
    regex_result=regex_parsing(email_text)
    result.update(regex_result)

    has_amount=regex_result.get('amount') is not None
    has_tax=regex_result.get('tax') is not None
    result['_meta']['amount_regex_found'] = bool(has_amount)
    result['_meta']['tax_regex_found'] = bool(has_tax)

    
    missing_info=[]
    if not vendor_name or str(vendor_name).strip().lower() == "unknown":
        missing_info.append('vendor')
    if not has_amount:
        missing_info.append('amount')
    if not has_tax:
        missing_info.append('tax')
    
    if missing_info:
        result['_meta']['ai_amount_tax_called'] = any(f in missing_info for f in ['amount', 'tax'])
        result['_meta']['vendor_ai_called'] = 'vendor' in missing_info
        print(f" Regex failed for {vendor_name}:{','.join(missing_info)} mssing")
        print("\n Using Ai to extract missing fields\n")

        ai_result=ai_search(email_subject,email_text,missing_info)
        raw = ai_result.get('_ai_raw') or ''
        result['_meta']['ai_amount_tax_raw'] = raw
        result['_meta']['vendor_ai_raw'] = raw

        if ai_result.get('vendor'):
            result['vendor'] = str(ai_result.get('vendor')).strip()
            result['_meta']['vendor_ai_success'] = True
        if ai_result.get('amount') and not has_amount:
            result['amount'] = ai_result['amount']
            result['_meta']['ai_amount_found'] = True
        
        if ai_result.get('tax') and not result.get('tax'):
            result['tax'] = ai_result['tax']
            result['_meta']['ai_tax_found'] = True
    else:
        print(f"Regex successful for {vendor_name}")
    
    return result

def regex_parsing(email_text:str)->dict:
    regex_info={}
    amount_value = _extract_amount_value(email_text)
    if amount_value is not None:
        regex_info['amount'] = amount_value

    #regex match for tax
    tax_value = _extract_tax_value(email_text)
    if tax_value is not None:
        regex_info["tax"] = tax_value
    return regex_info
def ai_search(email_subject:str,email_text:str,missing_fields:list)->dict:
    ai_text = ""
    try:
        field_list=','.join(missing_fields)
        prompt=f"""Extract ONLY these fields from this receipt: {field_list}
Return JSON with only the requested fields:
{{
  "vendor": "",
  "amount": 0.00,
  "tax": 0.00
}}

You are a data extraction tool.
OUTPUT: ONLY JSON 
dont explain or any other thing other than the JSON

RULES:
0. "vendor": store/company name only (short text, no explanation).
1. "amount": final amount charged / balance due (Decimal only).
2. "tax": tax/local levy value (Decimal only).
3. Labels may be noisy or renamed (e.g. "balance due now", "local levy", "merchandise sum").
4. Return only numeric values, no currency symbols.

JSON:

Receipt Content:
{email_subject}
{email_text[:1500]}

JSON:"""
        ai_text = generate_text(
            prompt,
            temperature=0.1,
            max_output_tokens=100,
        )
        
        # 1. Use Regex to find the first '{' and the last '}'
        # This ignores any "Sure, here is your JSON" preamble
        match = re.search(r'\{.*\}', ai_text, re.DOTALL)
        if match:
            clean_json = match.group(0)
            ai_data = json.loads(clean_json)
        else:
            # Fallback if the AI returned something completely non-JSON
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
            except:
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

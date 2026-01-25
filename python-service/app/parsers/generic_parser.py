import re 
from datetime import datetime
from dateutil import parser as date_parser
import ollama
import json

def generic_parser(email_text:str,email_id:str,vendor_name:str)-> dict:
    information={
        'email_id': email_id,
        'vendor': "generic",
        'email body': email_text
    }
    result={}
    regex_result=regex_parsing(email_text)
    result.update(regex_result)

    has_amount=regex_result.get('amount') is not None
    has_date=regex_result.get('date') is not None
    has_tax=regex_result.get('tax') is not None

    if not has_amount or not has_date or has_tax:
        missing_info=[]
        if not has_amount:
            missing_info.append('amount')
        if not has_date:
            missing_info.append('date')
        if not has_tax:
            missing_info.append('tax')
        print(f" Regex failed for {vendor_name}:{','.join(missing_info)} mssing")
        print("\n Using Ai to extract missing fields\n")

        ai_result=ai_search(email_text,missing_info)
        if ai_result.get('amount') and not has_amount:
            result['amount'] = ai_result['amount']
        
        if ai_result.get('date') and not has_date:
            result['date'] = ai_result['date']
        
        if ai_result.get('tax') and not result.get('tax'):
            result['tax'] = ai_result['tax']
    else:
        print(f"Regex extraction successful for {vendor_name}")
    
    return result

def regex_parsing(email_text:str)->dict:
    regex_info={}
    ##regex match for amount
    amount_patterns = [
    r'(?:total|amount|charge)[:\s]+\$?([\d,]+\.\d{2})',
    r'\$\s*([\d,]+\.\d{2})\s*(?:total|charged)',
    r'(?:grand|order)\s+total[:\s]+\$?([\d,]+\.\d{2})',
    ]
    for pattern in amount_patterns:
        match = re.search(pattern, email_text, re.IGNORECASE)
        if match:
            try:
                regex_info['amount'] = float(match.group(1).replace(',', ''))
            except:
                continue
            break

    #regex match for date
    date_patterns = [
        r'date[:\s]+([^\n]+)',
        r'(?:on|ordered)[:\s]+([^\n]+)',
        ]
    for pattern in date_patterns:
        date_match=re.search(pattern,email_text,re.IGNORECASE)
        if date_match:
            try:
                regex_info["date"]=date_parser.parse(date_match.group(1),fuzzy=True)
            except:
                continue

    #regex match for tax
    tax_match=re.search(r'tax[:\s]+\$?([\d,]+\.\d{2})',email_text,re.IGNORECASE)
    if tax_match:
        regex_info["tax"]=float(tax_match.group(1).replace(',',''))
    return regex_info
def ai_search(email_text:str,missing_fields:list)->dict:
    try:
        field_list=','.join(missing_fields)
        prompt=f"""Extract ONLY these fields from this reciept: {field_list}
Return JSON with only the requested fields:
{{
  "amount": 0.00,
  "date": "YYYY-MM-DD",
  "tax": 0.00
}}

Rules:
1. amount: decimal number only (no symbols)
2. date: format as YYYY-MM-DD
3. tax: decimal number only (0.00 if not found)
4. If a field is missing, use null.

Receipt Content:
{email_text[:1500]}

JSON:"""
        response=ollama.chat(
            model='llama3.2:3b',
            messages=[{'role':'user','content':prompt}],
            options={
                'num_predict':100,
                'temperature':0.1,
            }
        )
        ai_text = response['message']['content'].strip()
        
        # 1. Use Regex to find the first '{' and the last '}'
        # This ignores any "Sure, here is your JSON" preamble
        match = re.search(r'\{.*\}', ai_text, re.DOTALL)
        if match:
            clean_json = match.group(0)
            ai_data = json.loads(clean_json)
        else:
            # Fallback if the AI returned something completely non-JSON
            print(f"⚠️ AI returned text without a JSON block: {ai_text[:50]}...")
            return {}
        
        ai_info = {}
        
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
        return {}


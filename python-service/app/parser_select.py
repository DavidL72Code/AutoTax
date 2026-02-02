from parsers.paypal_parser import paypal_parser
from parsers.amazon_parser import amazon_parser
from parsers.generic_parser import generic_parser
from database import SessionLocal 
from models import Vendor
import ollama
import re
from vendor_normalize import normalize_vendor_name

def parser_select(email_data:dict)->dict:
    email_body=email_data.get('body','')
    email_from=email_data.get('from','').lower()
    email_subject=email_data.get('subject','').lower()
    email_id=email_data.get('id')
    email_date=email_data.get('date')

    vendor_name=vendor_search(email_from,email_subject,email_body)

    if not vendor_name:
        print(f"⚠️  Vendor unknown for {email_id}, using AI to identify...")
        vendor_name = identify_vendor_with_ai(email_body,email_subject)
        
        if vendor_name != "Unknown":
            print(f"AI identified vendor: {vendor_name}")
        else:
            print(f"AI could not identify vendor")
    normalized_vendor=normalize_vendor_name(
    vendor_name or "Unknown",
    email_data=email_data
    )
    if normalized_vendor == "PayPal":
        return paypal_parser(email_subject,email_body, email_id,email_date, normalized_vendor)
    elif normalized_vendor == "Amazon":
        return amazon_parser(email_subject,email_body, email_id,email_date,normalized_vendor)
    else:
        return generic_parser(email_subject,email_body, email_id,email_date, normalized_vendor)

def vendor_search(email_from: str, subject: str, body: str) -> str:
    email_from
    if 'paypal.com' in email_from:
        return 'PayPal'
    elif 'amazon.com' in email_from or "amazon.co" in email_from:
        return 'Amazon'
    elif 'uber.com' in email_from and 'eats' in subject:
        return 'UberEats'
    
    if 'paypal' in subject:
        return "Paypal"
    elif 'amazon' in subject:
        return "Amazon"
    
    return None


def identify_vendor_with_ai(email_body: str, email_subject:str) -> str:
    try:
        prompt = f"""What is the vendor/store/company name from this receipt or email?

Reply with ONLY the vendor name (maximum 4 words). Do not include any explanation.

Examples of good responses:
- "Starbucks"
- "Blue Mountain Cafe"
- "Target"
- "Joe's Pizza"

Email Subject:
{email_subject}
Email text:
{email_body[:1500]}

Vendor name:"""
        
        response = ollama.chat(
            model='llama3.2:3b',
            messages=[{'role': 'user', 'content': prompt}],
            options={
                'num_predict': 30,      
                'temperature': 0.1,     
            }
        )
        
        vendor_name = response['message']['content'].strip()
        
        vendor_name = re.sub(r'^(The |A |An )', '', vendor_name, flags=re.IGNORECASE)
        
        vendor_name = vendor_name.split('\n')[0].strip()
        
        vendor_name = vendor_name.replace('"', '').replace("'", '')
        
        vendor_name = vendor_name.rstrip('.,;:')
        
        if 2 < len(vendor_name) < 60:  
            word_count = len(vendor_name.split())
            if word_count <= 5:  
                return vendor_name
        print(f"⚠️  AI returned invalid vendor: '{vendor_name}'")
        
    except Exception as e:
        print(f"AI vendor identification failed: {e}")
    
    return "Unknown"
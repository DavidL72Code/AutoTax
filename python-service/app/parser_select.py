from parsers.paypal_parser import paypal_parser
from parsers.amazon_parser import amazon_parser
from database import SessionLocal 
from models import Vendor
import ollama
import re

def parser_select(email_data:dict)->dict:
    email_body=email_data.get('body','')
    email_from=email_data.get('from','').lower
    email_subject=email_data.get('subject','').lower
    email_id=email_data.get('id')

    vendor_name=vendor_search(email_from,email_subject,email_body)
    normalized_vendor=vendor_normalize(
    vendor_name or "Unknown",
    email_data=email_data
    )
    if normalized_vendor == "Unknown":
        print(f"⚠️  Vendor unknown for {email_id}, using AI to identify...")
        normalized_vendor = identify_vendor_with_ai(email_text)
        
        if normalized_vendor != "Unknown":
            print(f"AI identified vendor: {normalized_vendor}")
        else:
            print(f"AI could not identify vendor")
    if normalized_vendor == "PayPal":
        return paypal_parser(email_text, email_id)
    elif normalized_vendor == "Amazon":
        return amazon_parser(email_text, email_id)
    else:
        return generic_parser(email_text, email_id, normalized_vendor)

def vendor_search(email_from: str, subject: str, body: str) -> str:
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


def identify_vendor_with_ai(email_text: str) -> str:
    try:
        prompt = f"""What is the vendor/store/company name from this receipt or email?

Reply with ONLY the vendor name (maximum 4 words). Do not include any explanation.

Examples of good responses:
- "Starbucks"
- "Blue Mountain Cafe"
- "Target"
- "Joe's Pizza"

Email text:
{email_text[:1500]}

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
from parsers.paypal_parser import paypal_parser
from parsers.amazon_parser import amazon_parser
from database import SessionLocal 
from models import Vendor

def parser_select(email_data:dict)->dict
    email_body=email_data.get('body','')
    email_from=email_data.get('from','').lower
    email_subject=email_data.get('subject','').lower
    email_id=email_data.get('id')

    vendor_name=vendor_search(email_from,email_subject,email_body)
    if vendor_name:
        db=SessionLocal()
        vendor=db.quer(Vendor).filter(Vendor.normalized_name==vendor_name).first()
        db.close()

        if vendor:
            parser_type=vendor.parser_type
            if parser_type=="paypal":
                return paypal_parser(email_body,email_id)
            elif parser_type="amazon":
                return amazon_parser(email_body,email_id)
            elif parser_type='generic':
                return generic_parser(email_body,email_id,vendor_name)
    print(f"unknown vendor, using generic parser for email{email_id}")
    return generic_parser(email_text,email_id,vendor_name or "unkown")

def identify_vendor(email_from: str, subject: str, body: str) -> str:
    if 'paypal.com' in email_from:
        return 'PayPal'
    elif 'amazon.com' in email_from:
        return 'Amazon'
    elif 'uber.com' in email_from and 'eats' in subject:
        return 'UberEats'
    
    return None



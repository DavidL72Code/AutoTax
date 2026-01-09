import re 
from datetime import datetime
from dateutil import parser as date_parser

def amazon_parser(email_text:str,email_id:str)-> dict:
    information={
        'email_id': email_id,
        'vendor': "amazon",
        'email body': email_text
    }
    amount_match= re.search(r'(?:Total|Order Total).*?\$?([\d,]+\.\d{2})', email_text, re.IGNORECASE)
    if amount_match:
        information["amount"]=float(amount_match.group(1).replace(',',''))
    date_match=re.search(r'date[:\s]+([^\n]+)',email_text,re.IGNORECASE)
    if date_match:
        try:
            information["date"]=date_parser.parse(date_match.group(1),fuzzy=True)
        except:
            pass 
    tax_match=re.search(r'tax[:\s]+\$?([\d,]+\.\d{2})',email_text,re.IGNORECASE)
    if tax_match:
        information["tax"]=float(tax_match.group(1).replace(',',''))
    return information
import re 
from datetime import datetime
from dateutil import parser as date_parser
from .generic_parser import regex_parsing
from .generic_parser import ai_search

def paypal_parser(email_subject:str, email_text:str,email_id:str,email_date:str,vendor_name:str)-> dict:
    result={
        'email_id': email_id,
        'vendor': "paypal",
        'email_body': email_text,
        'amount':0.0,
        'date': email_date,
        'tax': 0.0
    }
    regex_result=regex_parsing(email_text)
    result.update(regex_result)

    has_amount=regex_result.get('amount') is not None
    has_tax=regex_result.get('tax') is not None

    if not has_amount or not has_tax:
        missing_info=[]
        if not has_amount:
            missing_info.append('amount')
        if not has_tax:
            missing_info.append('tax')
        print(f" Regex failed for {vendor_name}:{','.join(missing_info)} mssing")
        print("\n Using Ai to extract missing fields\n")

        ai_result=ai_search(email_subject,email_text,missing_info)
        if ai_result.get('amount') and not has_amount:
            result['amount'] = ai_result['amount']
        
        if ai_result.get('tax') and not result.get('tax'):
            result['tax'] = ai_result['tax']
    else:
        print(f"Regex extraction successful for {vendor_name}")
    
    return result

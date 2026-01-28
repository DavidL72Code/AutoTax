from database import SessionLocal
from models import Vendor
import re

def normalize_vendor_name(raw_vendor:str, email_data:dict=None)->str:
    try:
        if not raw_vendor:
            return "Unknown"

        db=SessionLocal()
        #exact
        vendor=db.query(Vendor).filter(Vendor.name==raw_vendor).first()
        if vendor:
            db.close()
            return vendor.normalized_name
    
        if email_data:
            vendor_from_content = search_email_for_vendor(email_data, db)
            if vendor_from_content:
                db.close()
                return vendor_from_content
    finally:
        db.close()

    return raw_vendor


def search_email_for_vendor(email_data:dict,db)->str:
    subject=email_data.get('subject','').lower()
    body=email_data.get('body','').lower()
    sender=email_data.get('from','').lower()

    email_info=f"{sender}{subject}{body}"
    vendors=db.query(Vendor).all()
    best_score=0
    for vendor in vendors:
        if vendor.normalize_name in email_info or vendor.name in email_info:
            return vendor.normalized_name
        score = 0
        vendor_words = vendor.normalized_name.lower().split()
            
        for word in vendor_words:
            if len(word) >= 3 and word in email_info:  
                score += 20
            elif word in sender or word in subject:
                score += 70
            else:
                score += 3
            
        if score > best_score:
            best_score = score
            best_match = vendor.normalized_name
        
    if best_score >= 10:
        return best_match
from .database import SessionLocal
from .models import Vendor
import re
from .firestore_store import firestore_enabled, get_all_vendors

def normalize_vendor_name(raw_vendor:str, email_data:dict=None)->str:
    if firestore_enabled():
        if not raw_vendor:
            return "Unknown"
        if email_data:
            vendor_from_content = search_email_for_vendor(email_data, None)
            if vendor_from_content:
                return vendor_from_content
        return raw_vendor

    db = None
    try:
        if not raw_vendor:
            return "Unknown"

        db=SessionLocal()
        #exact
        vendor=db.query(Vendor).filter(Vendor.name==raw_vendor).first()
        if vendor:
            return vendor.normalized_name
    
        if email_data:
            vendor_from_content = search_email_for_vendor(email_data, db)
            if vendor_from_content:
                return vendor_from_content
    finally:
        if db is not None:
            db.close()

    return raw_vendor


def search_email_for_vendor(email_data:dict,db)->str:
    subject=email_data.get('subject','').lower()
    body=email_data.get('body','').lower()
    sender=email_data.get('from','').lower()

    email_info=f"{sender}{subject}{body}"
    vendors = get_all_vendors() if firestore_enabled() else db.query(Vendor).all()
    if not vendors:
        return None

    best_score=0
    best_match=None
    for vendor in vendors:
        normalized_name = (vendor.normalized_name or "").lower()
        name = (vendor.name or "").lower()

        if normalized_name and normalized_name in email_info:
            return vendor.normalized_name
        if name and name in email_info:
            return vendor.normalized_name

        score = 0
        vendor_words = normalized_name.split()
            
        for word in vendor_words:
            if len(word) >= 3 and word in email_info:  
                score += 20
            elif word in sender or word in subject:
                score += 70
            
        if score > best_score:
            best_score = score
            best_match = vendor.normalized_name
        
    if best_match and best_score >= 40:
        return best_match
    return None

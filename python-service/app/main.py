from email_scraper import fetch_receipt_emails
from parser_select import parser_select
from data_helper import log_transaction
from database import SessionLocal

def main():
    emails=fetch_receipt_emails()
    db=SessionLocal()
    try:
        for email in emails:
            parsed_data = parser_select(email)
    
            
            if parsed_data and isinstance(parsed_data, dict):
                log_transaction(parsed_data)
        
        
                vendor = parsed_data.get('vendor', 'Unknown')
                amount = parsed_data.get('amount', 0.0)
                date= parsed_data.get('date', 'N/A')
        
           
                display_vendor = (vendor or "Unknown")[:20]
                print(f"{str(date):<12} | {display_vendor:<20} | ${amount:>8.2f}")
            else:
            
                subject = email.get('subject', 'No Subject')
                print(f"⚠️  [SKIP] Could not parse email: {subject[:30]}...")
    finally:
        db.close()
if __name__=="__main__":
    main()
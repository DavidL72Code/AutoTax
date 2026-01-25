from email_scraper import fetch_receipt_emails
from parser_select import parser_select
from data_helper import log_transaction
from database import SessionLocal

def main():
    emails=fetch_receipt_emails()
    db=SessionLocal()
    try:
        for email in emails:
            parsed_data = {} 
            vendor = "Unknown"
            amount = 0.0
            parsed_data=parser_select(email)
            if parsed_data:
                log_transaction(parsed_data)
                vendor = parsed_data.get('vendor', 'Unknown')
                amount = parsed_data.get('amount', 0.0)
                date = parsed_data.get('date', 'N/A')
                print(f"{str(date):<12} | {vendor[:20]:<20} | ${amount:>8.2f}")
            else:
                print(f"⚠️  [SKIP] Could not parse email: {email.get('subject')[:30]}...")
    finally:
        db.close()
if __name__=="__main__":
    main()
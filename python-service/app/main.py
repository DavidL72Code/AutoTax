from .email_scraper import fetch_receipt_emails
from .parser_select import parser_select
from .data_helper import log_transaction, get_existing_email_ids

def main(user_id: str | int | None = None, gmail_creds=None):
    # Only fetch/parse emails we don't already have (saves parsing and AI)
    existing_ids = get_existing_email_ids(user_id=user_id)
    emails = fetch_receipt_emails(existing_ids=existing_ids, creds=gmail_creds)
    for email in emails:
        parsed_data = parser_select(email)

        if parsed_data and isinstance(parsed_data, dict):
            print(
                "🧪 Parsed:",
                parsed_data.get('email_id'),
                parsed_data.get('vendor'),
                parsed_data.get('amount'),
                parsed_data.get('date'),
            )

        if parsed_data and isinstance(parsed_data, dict):
            amount = parsed_data.get('amount') or 0.0
            if amount == 0 or (isinstance(amount, (int, float)) and float(amount) == 0):
                subject = email.get('subject', 'No Subject')
                print(f"⚠️  [SKIP] No expenditure (total 0): {subject[:40]}...")
                continue
            log_transaction(parsed_data, user_id=user_id)
            vendor = parsed_data.get('vendor', 'Unknown')
            date = parsed_data.get('date', 'N/A')
            display_vendor = (vendor or "Unknown")[:20]
            print(f"{str(date):<12} | {display_vendor:<20} | ${float(amount):>8.2f}")
        else:
            subject = email.get('subject', 'No Subject')
            print(f"⚠️  [SKIP] Could not parse email: {subject[:30]}...")
if __name__=="__main__":
    main()

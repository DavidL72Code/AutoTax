from .email_scraper import fetch_receipt_emails
from .parser_select import parser_select
from .data_helper import log_transaction, get_existing_email_ids

def main(user_id: str | int | None = None, gmail_creds=None, date_from: str | None = None, date_to: str | None = None, run_id=None, is_cancelled=None, progress=None):
    def report(message: str):
        """Send a human-readable progress line to the scan log (and stdout)."""
        print(message)
        if progress:
            try:
                progress(message)
            except Exception:
                pass

    existing_ids = get_existing_email_ids(user_id=user_id)
    emails = fetch_receipt_emails(max_results=50, days_back=180, date_from=date_from, date_to=date_to, existing_ids=existing_ids, creds=gmail_creds)

    total = len(emails)
    report(f"Found {total} new email(s) to scan.")

    scanned = 0
    saved = 0
    skipped = 0
    for index, email in enumerate(emails, start=1):
        if is_cancelled and is_cancelled(run_id):
            report("Scan cancelled.")
            return {"scanned": scanned, "saved": saved, "skipped": skipped}

        scanned += 1
        subject = (email.get('subject') or 'No Subject')[:50]
        report(f"[{index}/{total}] Parsing: {subject}")

        parsed_data = parser_select(email)
        if not parsed_data or not isinstance(parsed_data, dict):
            skipped += 1
            report(f"[{index}/{total}] Skipped — could not parse receipt.")
            continue

        amount = parsed_data.get('amount') or 0.0
        try:
            amount_val = float(amount)
        except (TypeError, ValueError):
            amount_val = 0.0

        if amount_val == 0:
            skipped += 1
            report(f"[{index}/{total}] Skipped — no charge amount found.")
            continue

        log_transaction(parsed_data, user_id=user_id)
        saved += 1
        vendor = (parsed_data.get('vendor') or 'Unknown')[:24]
        date = parsed_data.get('date', 'N/A')
        report(f"[{index}/{total}] Saved: {vendor} — ${amount_val:.2f} ({date})")

    report(f"Scan complete — {saved} saved, {skipped} skipped of {total}.")
    return {"scanned": scanned, "saved": saved, "skipped": skipped}

if __name__=="__main__":
    main()

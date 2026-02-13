import os 
import base64
import re
from google.auth.transport.requests import Request 
from google.oauth2.credentials import Credentials 
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from bs4 import BeautifulSoup
from email.utils import parsedate_to_datetime

SCOPES=['https://www.googleapis.com/auth/gmail.readonly']

def get_gmail_service():
    creds=None
    if os.path.exists('token.json'):
        creds=Credentials.from_authorized_user_file('token.json',SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            print("First time setup-open browswer for autherntication...")
            flow=InstalledAppFlow.from_client_secrets_file(
                'credentials.json',SCOPES)
            creds=flow.run_local_server(port=0)
        
        with open('token.json','w') as token:
            token.write(creds.to_json())
        print("Authentication saved")
    return build('gmail','v1',credentials=creds)

def fetch_receipt_emails(max_results=15, days_back=60, existing_ids=None):
    """
    Fetch receipt-like emails from Gmail.
    existing_ids: optional set of Gmail message ids already in DB; we skip fetching/parsing those to save time and AI.
    """
    try:
        print("Connecting to Gmail...")
        service = get_gmail_service()

        query_parts = [
            '(subject:"confirmation" OR subject:"receipt" OR OR subject:"payment" OR subject:"order summary") -subject:"shipping" -subject:"delivered" -subject:"sale" -subject:"deals"',
            f' newer_than:{days_back}d',
        ]
        query = ''.join(query_parts)
        print(f"Searching{query}")

        results = service.users().messages().list(
            userId='me',
            q=query,
            maxResults=max_results
        ).execute()

        messages = results.get('messages', [])

        if not messages:
            print("No receipt emails found")
            return []

        # Skip messages we already have in DB (no fetch, no parsing, no AI)
        if existing_ids:
            before = len(messages)
            messages = [m for m in messages if m['id'] not in existing_ids]
            skipped = before - len(messages)
            if skipped:
                print(f"📬 Skipping {skipped} already in database (no parse/AI)")
            if not messages:
                print("✅ All listed emails already processed")
                return []

        print(f"📬 Found {len(messages)} new receipt emails to process")
        print(f"⏳ Fetching email details...")

        emails = []
        for i, message in enumerate(messages):
            try:
                msg = service.users().messages().get(
                    userId='me',
                    id=message['id'],
                    format='full'
                ).execute()
                email_data = parse_gmail_message(msg)
                emails.append(email_data)
                if (i + 1) % 10 == 0:
                    print(f"  📊 Processed {i + 1}/{len(messages)}...")
            except Exception as e:
                print(f"⚠️  Error processing message {message['id']}: {e}")
                continue

        print(f"✅ Successfully fetched {len(emails)} emails")
        return emails
        
    except Exception as e:
        print(f"❌ Error fetching emails: {e}")
        print("💡 Tip: Make sure credentials.json exists and you've authenticated")
        return []


def parse_gmail_message(msg):
    """
    Parse Gmail API message into simple dict
    """
    headers = msg['payload']['headers']
    
    email_data = {
        'id': msg['id'],
        'from': get_header(headers, 'From'),
        'subject': get_header(headers, 'Subject'),
        'date': (parsedate_to_datetime(get_header(headers, 'Date'))).strftime('%Y-%m-%d'),
        'body': ''
    }
    
    # Extract email body
    email_data['body'] = get_email_body(msg['payload'])
    
    return email_data


def get_header(headers, name):
    """Get header value by name"""
    for header in headers:
        if header['name'].lower() == name.lower():
            return header['value']
    return ''


def get_email_body(payload):
    html_parts = []
    
    # --- 1. HANDLE DIRECT BODY (Single-part emails) ---
    if 'body' in payload and 'data' in payload['body']:
        direct_data = base64.urlsafe_b64decode(payload['body']['data']).decode('utf-8', errors='ignore')
        mimetype = payload.get('mimeType')
        
        if mimetype == 'text/plain':
            return direct_data
        elif mimetype == 'text/html':
            html_parts.append(direct_data)

    # --- 2. HANDLE MULTIPART (Nested emails) ---
    if 'parts' in payload:
        for part in payload['parts']:
            mime = part.get('mimeType')
            
            if mime == 'text/plain' and 'data' in part['body']:
                return base64.urlsafe_b64decode(part['body']['data']).decode('utf-8', errors='ignore')
            
            elif mime == 'text/html' and 'data' in part['body']:
                html_parts.append(
                    base64.urlsafe_b64decode(part['body']['data']).decode('utf-8', errors='ignore')
                )
            
            elif 'parts' in part:
                nested = get_email_body(part)
                if nested: return nested

    # --- 3. CLEANING PHASE ---
    if html_parts:
        soup = BeautifulSoup(" ".join(html_parts), 'html.parser')
        for hidden in soup(["script", "style", "meta", "noscript"]):
            hidden.decompose()
        return " ".join(soup.get_text(separator=' ').split())

    return ""


# Test the scraper
if __name__ == "__main__":
    print("=" * 60)
    print("🧪 Testing Gmail Email Scraper")
    print("=" * 60)
    
    # Fetch recent emails
    emails = fetch_receipt_emails(max_results=10, days_back=30)
    
    print(f"\n📊 Results:")
    print(f"   Total emails fetched: {len(emails)}")
    
    if emails:
        print(f"\n📧 Sample email:")
        sample = emails[0]
        print(f"   ID: {sample['id']}")
        print(f"   From: {sample['from']}")
        print(f"   Subject: {sample['subject']}")
        print(f"   Date: {sample['date']}")
        print(f"   Body preview: {sample['body'][:150]}...")
    
    print("\n✅ Test complete!")

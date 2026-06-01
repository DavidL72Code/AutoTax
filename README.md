# Receipt Automation

Automatically scrapes Gmail for receipt emails, parses vendor/amount/tax using regex and AI, and stores transactions in a dashboard you can view and export.

---

## Purpose

Most people lose track of spending because receipts are scattered across their inbox. This project connects to your Gmail account via OAuth, finds receipt emails automatically, extracts the financial data from each one, and gives you a live dashboard of your spending — broken down by vendor, category, and date.

It also includes a public demo mode so anyone can try the parser without signing in, using AI-generated receipt emails that simulate real-world noise and formatting variation.

---

## Features

### Gmail Integration
- OAuth 2.0 connection to Gmail via Google API
- Automatic email scraping filtered to receipt/invoice senders
- Refresh token stored encrypted (Fernet) per user
- Background sync so the API never times out on large inboxes

### Receipt Parsing Pipeline
- **Regex parsing** — fast, zero-cost extraction using pattern matching for common labels (`Total:`, `Sales Tax:`, `Amount Charged:`, etc.)
- **Individual AI fallback** — if regex misses a field, a single Gemini call extracts the missing vendor/amount/tax for that email
- **Batch AI parsing** — all emails that failed regex are bundled into one prompt and parsed in a single Gemini call, cutting API calls from N to 1 and reducing wall-clock time by ~8×
- **Smart body extraction** — before sending to the LLM, only lines containing dollar amounts or financial keywords are extracted from the email body, reducing tokens sent by ~70%
- **Specialized parsers** — dedicated logic for PayPal and Amazon email formats
- **Vendor normalization** — cleans and standardizes vendor names across formats

### Auth & Users
- Email/password registration and login
- Google Sign-In via Firebase Auth
- Session tokens with 30-day TTL

### Dashboard
- Total spent, receipt count, unique vendors, average transaction
- Top vendors by spending
- CSV export
- Vendor spend pie chart (server-rendered)
- Inline transaction editing and deletion

### Demo Mode
- Shared demo user with AI-generated receipt emails
- Live parse progress log streamed to the browser
- No login required

---

## Tech Stack

| Layer | Technology |
|---|---|
| Backend | Python, FastAPI |
| AI / LLM | Google Gemini (`gemini-3.1-flash-lite`) via `google-generativeai` |
| Database | Firebase Firestore (primary), SQLite/PostgreSQL (legacy fallback) |
| Auth | Firebase Authentication, custom token auth |
| Email API | Gmail API via `google-auth-oauthlib` |
| Encryption | Fernet symmetric encryption for stored OAuth tokens |
| Frontend | Vanilla JS, HTML/CSS (no framework) |
| Deployment | Render (backend), static file serving |
| Migrations | Alembic (SQLAlchemy) |
| Containerization | Docker, Docker Compose |

---

## Parsing Architecture

```
Gmail email
    │
    ▼
Vendor detection  ──► PayPal parser
(domain + regex)  ──► Amazon parser
                  ──► Generic parser
                            │
                       Regex pass
                            │
                    ┌───────┴────────┐
                 Found           Missing
                    │           fields?
                 Done               │
                            Batch AI call
                          (all failures in
                           one prompt)
                                   │
                              Merge & save
```

For a batch of N emails that all fail regex, the system makes **1 LLM call** instead of N, with only the financially relevant lines from each email body included in the prompt.

---

## Parser Benchmark

Evaluated on 10 AI-generated receipt emails with known ground truth (vendor, total, tax). Emails mix clean organized formats (first 5) with messy real-world formats containing decoy dollar values, indirect labels, and noise.

### Before optimization (full body, verbose prompts, `150×N` max tokens)

| Method | Vendor | Amount | Tax | All Correct | AI Calls | Time |
|---|---|---|---|---|---|---|
| regex_only | 0% | 40% | 100% | 0% | 0 | 0.01s |
| individual_ai | 100% | 100% | 100% | 100% | 10 | 172.8s |
| batch_ai | 100% | 100% | 100% | 100% | 10* | 22.4s |

### After optimization (financial-line extraction, compact prompts, `70×N` max tokens)

| Method | Vendor | Amount | Tax | All Correct | AI Calls | Time |
|---|---|---|---|---|---|---|
| regex_only | 0% | 10% | 100% | 0% | 0 | 0.01s |
| individual_ai | 100% | 100% | 100% | 100% | 10 | 168.3s |
| batch_ai | 100% | 100% | 100% | 100% | 10* | **13.5s** |

\* AI calls = emails that needed AI help; actual API requests = 1 for batch_ai.

**Key results:**
- `batch_ai` is **8× faster** than `individual_ai` and **40% faster** after optimization
- Accuracy is identical between `individual_ai` and `batch_ai`
- `regex_only` catches tax reliably but fails on vendor and misses amounts with indirect labels
- Token reduction from body extraction: ~1500 chars/email → ~400 chars/email (~70% reduction)

Run the benchmark yourself:
```bash
cd python-service
python3 eval.py --json --detail   # full comparison with per-email breakdown
python3 eval.py --skip-ai         # regex only, instant, no API calls
python3 eval.py --count 20        # larger test set
```

---

## Setup

### Prerequisites
- Python 3.10+
- A Google Cloud project with Gmail API and Firebase enabled
- A Gemini API key

### Environment Variables

Copy `.env.example` to `.env` and fill in:

```
GOOGLE_API_KEY=          # Gemini API key
GEMINI_MODEL=            # e.g. gemini-3.1-flash-lite
FIREBASE_PROJECT_ID=     # Firebase project ID
FIREBASE_SERVICE_ACCOUNT_PATH=  # or FIREBASE_SERVICE_ACCOUNT_JSON
FIREBASE_WEB_API_KEY=
FIREBASE_WEB_AUTH_DOMAIN=
FIREBASE_WEB_APP_ID=
GOOGLE_OAUTH_CLIENT_ID=
GOOGLE_OAUTH_CLIENT_SECRET=
GOOGLE_OAUTH_REDIRECT_URI=
FERNET_KEY=              # generate with: python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

### Run locally

```bash
cd python-service
pip install -r requirements.txt
uvicorn app.api:app --reload --port 8000
```

Open `index.html` directly in a browser or serve it from any static host.

### Docker

```bash
docker-compose up --build
```

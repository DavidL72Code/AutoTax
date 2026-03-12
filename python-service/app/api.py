import os
import threading
import json
import hashlib
import uuid
import random
import re
from pathlib import Path

from fastapi import FastAPI, HTTPException, Body, Request
from fastapi.middleware.cors import CORSMiddleware
from .data_helper import get_all_transactions, delete_zero_amount_transactions
from .database import SessionLocal
from .models import Transaction
from datetime import datetime, timedelta
import uvicorn
from dateutil import parser as date_parser
from io import StringIO, BytesIO
import base64
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from .ai_client import generate_text

app = FastAPI()
DEMO_PARSE_RUNS = {}
DEMO_PARSE_LOCK = threading.Lock()

# Allow your website to call the API
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, specify your domain
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
def root():
    return {"message": "Receipt Automation API", "status": "running"}

def _nonzero_transactions(transactions):
    """Filter out transactions with amount 0 or None (no expenditure)."""
    out = []
    for t in transactions:
        if t.amount is None:
            continue
        try:
            amt = float(t.amount)
            if amt == 0 or abs(amt) < 0.0001:
                continue
        except (TypeError, ValueError):
            continue
        out.append(t)
    return out

@app.get("/api/transactions")
def get_transactions():
    """Get all transactions from database (excludes zero-amount)."""
    try:
        transactions = get_all_transactions()
        transactions = _nonzero_transactions(transactions)
        return [
            {
                "id": t.id,
                "date": t.date.strftime('%Y-%m-%d') if isinstance(t.date, datetime) else str(t.date),
                "vendor": t.vendor or "Unknown",
                "amount": float(t.amount) if t.amount else 0.0,
                "tax": float(t.tax) if t.tax else 0.0,
                "email_id": t.email_id,
                "category": t.category,
                "payment_method": t.payment_method
            }
            for t in transactions
        ]
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching transactions: {str(e)}")

@app.get("/api/stats")
def get_stats():
    """Get dashboard statistics (excludes zero-amount transactions)."""
    try:
        transactions = _nonzero_transactions(get_all_transactions())
        total_spent = sum(t.amount for t in transactions if t.amount)
        total_receipts = len(transactions)
        unique_vendors = len(set(t.vendor for t in transactions if t.vendor))
        avg_transaction = total_spent / total_receipts if total_receipts > 0 else 0
        
        return {
            "total_spent": round(total_spent, 2),
            "total_receipts": total_receipts,
            "unique_vendors": unique_vendors,
            "avg_transaction": round(avg_transaction, 2)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching stats: {str(e)}")

@app.get("/api/top-vendors")
def get_top_vendors():
    """Get top vendors by spending (excludes zero-amount transactions)."""
    try:
        transactions = _nonzero_transactions(get_all_transactions())
        # Group by vendor
        vendor_totals = {}
        vendor_counts = {}
        
        for t in transactions:
            vendor = t.vendor or "Unknown"
            amount = t.amount or 0
            
            if vendor not in vendor_totals:
                vendor_totals[vendor] = 0
                vendor_counts[vendor] = 0
            
            vendor_totals[vendor] += amount
            vendor_counts[vendor] += 1
        
        # Sort by total spending
        top_vendors = sorted(vendor_totals.items(), key=lambda x: x[1], reverse=True)[:4]
        
        return [
            {
                "vendor": vendor,
                "total": round(amount, 2),
                "count": vendor_counts[vendor]
            }
            for vendor, amount in top_vendors
        ]
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching top vendors: {str(e)}")

@app.post("/api/cleanup-zero")
def cleanup_zero_transactions():
    """Delete all transactions with amount 0 or null from the database. Returns count removed."""
    try:
        deleted = delete_zero_amount_transactions()
        return {"status": "success", "deleted": deleted, "message": f"Removed {deleted} zero-amount transaction(s)."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Cleanup failed: {str(e)}")

def _run_sync():
    """Run email sync in background (avoids request timeouts). Auto-removes $0 transactions after sync."""
    try:
        from .main import main
        print("🔄 Starting email sync...")
        main()
        deleted = delete_zero_amount_transactions()
        if deleted:
            print(f"🧹 Removed {deleted} zero-amount transaction(s) after sync.")
        _print_db_snapshot()
        print("✅ Email sync completed")
    except Exception as e:
        print(f"❌ Sync failed: {e}")

def _require_api_key(request: Request):
    """Require X-API-Key when SYNC_API_KEY is set."""
    expected = os.getenv("SYNC_API_KEY")
    if not expected:
        return
    provided = request.headers.get("X-API-Key", "")
    if provided != expected:
        raise HTTPException(status_code=401, detail="Unauthorized")

def _demo_emails_path() -> Path:
    path = Path(__file__).resolve().parent / "reports" / "demo_emails.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path

def _now_iso() -> str:
    return datetime.utcnow().isoformat() + "Z"

def _init_demo_run(run_id: str, force_reprocess: bool = False):
    with DEMO_PARSE_LOCK:
        DEMO_PARSE_RUNS[run_id] = {
            "run_id": run_id,
            "status": "queued",
            "total": 0,
            "processed": 0,
            "success": 0,
            "skipped": 0,
            "failed": 0,
            "force_reprocess": force_reprocess,
            "started_at": _now_iso(),
            "finished_at": None,
            "logs": [],
        }

def _append_demo_log(run_id: str, line: str):
    with DEMO_PARSE_LOCK:
        run = DEMO_PARSE_RUNS.get(run_id)
        if not run:
            return
        run["logs"].append(f"[{datetime.utcnow().strftime('%H:%M:%S')}] {line}")
        if len(run["logs"]) > 500:
            run["logs"] = run["logs"][-500:]

def _update_demo_run(run_id: str, **kwargs):
    with DEMO_PARSE_LOCK:
        run = DEMO_PARSE_RUNS.get(run_id)
        if not run:
            return
        run.update(kwargs)

def _get_demo_run(run_id: str):
    with DEMO_PARSE_LOCK:
        run = DEMO_PARSE_RUNS.get(run_id)
        return dict(run) if run else None

def _demo_email_id(email: dict) -> str:
    """Stable id for demo emails based on content so duplicates are skipped."""
    raw = "|".join(
        [
            str(email.get("from", "")),
            str(email.get("subject", "")),
            str(email.get("date", "")),
            str(email.get("body", "")),
        ]
    )
    return hashlib.sha256(raw.encode("utf-8", errors="ignore")).hexdigest()


def _prepare_demo_emails(emails):
    demo_rows = []
    for e in emails:
        email = {
            "id": e.get("id") or _demo_email_id(e),
            "from": e.get("from", "demo@example.com"),
            "subject": e.get("subject", "Demo receipt"),
            "date": e.get("date", datetime.utcnow().strftime("%Y-%m-%d")),
            "body": e.get("body", "Total: $10.00"),
        }
        demo_rows.append(email)
    return demo_rows

def _run_demo_parse(run_id: str, force_reprocess: bool = False):
    from .parser_select import parser_select
    from .data_helper import get_existing_email_ids, log_transaction

    try:
        _update_demo_run(run_id, status="running")
        path = _demo_emails_path()
        if not path.exists():
            _append_demo_log(run_id, "No demo_emails.json found. Generate demo emails first.")
            _update_demo_run(run_id, status="failed", finished_at=_now_iso())
            return

        emails = json.loads(path.read_text())
        if not isinstance(emails, list) or not emails:
            _append_demo_log(run_id, "Demo email list is empty. Generate demo emails first.")
            _update_demo_run(run_id, status="failed", finished_at=_now_iso())
            return

        existing_ids = get_existing_email_ids()
        _update_demo_run(run_id, total=len(emails), processed=0, success=0, skipped=0, failed=0)
        _append_demo_log(run_id, f"Loaded {len(emails)} demo emails.")

        success = 0
        skipped = 0
        failed = 0
        for idx, email in enumerate(emails, start=1):
            email_id = email.get("id")
            if not force_reprocess and email_id in existing_ids:
                skipped += 1
                _append_demo_log(run_id, f"[SKIP] Already processed: {email_id}")
                _update_demo_run(run_id, processed=idx, success=success, skipped=skipped, failed=failed)
                continue
            subject = (email.get("subject") or "Demo receipt")[:80]
            _append_demo_log(run_id, f"Parsing {idx}/{len(emails)}: {subject}")
            try:
                parsed = parser_select(email)
                if parsed and isinstance(parsed, dict):
                    tx = log_transaction(parsed)
                    vendor = parsed.get("vendor", "Unknown")
                    amount = float(parsed.get("amount") or 0.0)
                    meta = parsed.get("_meta") or {}
                    vendor_ai_called = bool(meta.get("vendor_ai_called", False))
                    vendor_ai_success = bool(meta.get("vendor_ai_success", False))
                    amount_ai_called = bool(meta.get("ai_amount_tax_called", False))
                    amount_ai_success = bool(meta.get("ai_amount_found", False))
                    tax_ai_called = bool(meta.get("ai_amount_tax_called", False))
                    tax_ai_success = bool(meta.get("ai_tax_found", False))
                    vendor_ai_raw = str(meta.get("vendor_ai_raw", ""))
                    amount_tax_ai_raw = str(meta.get("ai_amount_tax_raw", ""))
                    _append_demo_log(
                        run_id,
                        "AI indicators -> "
                        f"vendor_ai_called={vendor_ai_called}, "
                        f"vendor_ai_success={vendor_ai_success}, "
                        f"amount_ai_called={amount_ai_called}, "
                        f"amount_ai_success={amount_ai_success}, "
                        f"tax_ai_called={tax_ai_called}, "
                        f"tax_ai_success={tax_ai_success}"
                    )
                    if vendor_ai_called:
                        _append_demo_log(run_id, f"AI vendor raw -> {vendor_ai_raw or '(empty)'}")
                    if amount_ai_called:
                        _append_demo_log(run_id, f"AI amount/tax raw -> {amount_tax_ai_raw or '(empty)'}")
                    if tx is not None:
                        success += 1
                        if email_id:
                            existing_ids.add(email_id)
                        _append_demo_log(run_id, f"Saved: vendor={vendor}, amount=${amount:.2f}")
                    else:
                        failed += 1
                        _append_demo_log(run_id, f"Skipped/not saved: vendor={vendor}, amount=${amount:.2f}")
                else:
                    failed += 1
                    _append_demo_log(run_id, "Parse returned no transaction.")
            except Exception as row_error:
                failed += 1
                _append_demo_log(run_id, f"Error: {row_error}")
            finally:
                _update_demo_run(run_id, processed=idx, success=success, skipped=skipped, failed=failed)

        _update_demo_run(run_id, status="completed", finished_at=_now_iso())
        _append_demo_log(run_id, f"Run complete. success={success}, failed={failed}")
    except Exception as e:
        _append_demo_log(run_id, f"Run crashed: {e}")
        _update_demo_run(run_id, status="failed", finished_at=_now_iso())

def _generate_demo_emails(count: int = 6):
    """Generate demo receipt emails via Gemini with tax/subtotal/total details."""
    run_nonce = uuid.uuid4().hex[:8]
    prompt = f"""Generate {count} fake receipt emails in JSON array format.
Return ONLY a JSON array with exactly {count} objects and NO extra text.

Each object must include:
- subject
- from
- date (YYYY-MM-DD)
- vendor
- subtotal (number)
- tax (number)
- total (number)
- body

Rules:
1. Choose variety of vendor names. Do not use a fixed repeated list.
2. Ensure Tax==subtotal*.0625
3. Ensure total == subtotal + tax.
4. Make the body messy and realistic: include extra sections like promo text, shipping/tracking, support footer, rewards, partial refunds, and authorization lines.
5. Include at least 5-10 additional dollar values in each body (item prices, discounts, shipping, credits, prior balance, pending charge), so parser must distinguish the true subtotal/tax/total.
6. Do NOT format body as a short clean 5-line summary.
7. For the true amounts section, avoid exact labels like "Tax:" and "Total:"; use less direct wording like "local levy", "merchandise sum", and "balance due now".
8. Keep vendor name present in body, but not always in the sender domain.
9. Create a fresh set of vendors and receipts for this run token: {run_nonce}
"""

    def _safe_float(value, default=0.0):
        try:
            return round(float(value), 2)
        except Exception:
            return round(float(default), 2)

    def _build_messy_body(vendor: str, date: str, subtotal: float, tax: float, total: float, extra: str = "") -> str:
        items = []
        item_count = random.randint(3, 6)
        running = 0.0
        for i in range(item_count):
            price = round(random.uniform(2.5, 45.0), 2)
            qty = random.randint(1, 3)
            line_total = round(price * qty, 2)
            running += line_total
            items.append(f"Item {i+1} x{qty} ............. ${line_total:.2f}")

        shipping = round(random.uniform(0, 12.99), 2)
        discount = round(random.uniform(0, 10.0), 2)
        credit = round(random.uniform(0, 7.5), 2)
        pending = round(random.uniform(1.0, 30.0), 2)
        auth_hold = round(random.uniform(total, total + 25), 2)
        prior_balance = round(random.uniform(0, 80), 2)
        rewards = random.randint(50, 4000)
        noise_note = extra.strip()
        if noise_note:
            noise_note = f"\nCustomer Note Snippet: {noise_note[:220]}"

        return (
            f"Subject Thread: Re: order update / invoice copy / receipt confirmation\n"
            f"Merchant Notice: This receipt may include pending holds and promotional adjustments.\n"
            f"Order Ref: {uuid.uuid4().hex[:10].upper()}  |  Tracking: 1Z{uuid.uuid4().hex[:14].upper()}\n"
            f"----- PAYMENT RECONCILIATION BLOCK -----\n"
            f"Document Date -> {date}\n"
            f"Merchant Legal Name -> {vendor}\n"
            f"Merchandise Sum (USD) -> ${subtotal:.2f}\n"
            f"Local Levy @ 6.25 pct -> ${tax:.2f}\n"
            f"Balance Due Now (final) -> ${total:.2f}\n"
            f"--------------------------------\n"
            f"Auth Hold (temporary): ${auth_hold:.2f}\n"
            f"Pending Charge (not final): ${pending:.2f}\n"
            f"Previous Balance: ${prior_balance:.2f}\n"
            f"Rewards Applied Equivalent: ${credit:.2f} ({rewards} pts)\n"
            f"Promo Banner: Save 15% on next order over $50.00\n"
            f"Line Items:\n- " + "\n- ".join(items) + "\n"
            f"Shipping Est.: ${shipping:.2f}\n"
            f"Coupon / Promo Deduction: -${discount:.2f}\n"
            f"Support Plan Offer: $4.99/mo (not included)\n"
            f"If questions, contact support within 30 days. This message may contain automated text.{noise_note}\n"
        )

    def _build_organized_body(vendor: str, date: str, subtotal: float, tax: float, total: float) -> str:
        templates = [
            (
                f"Receipt Confirmation\n"
                f"Date: {date}\n"
                f"Vendor: {vendor}\n"
                f"Order Summary\n"
                f"Subtotal: ${subtotal:.2f}\n"
                f"Tax: ${tax:.2f}\n"
                f"Total: ${total:.2f}\n"
                f"Thank you for your purchase.\n"
            ),
            (
                f"Payment Receipt\n"
                f"Merchant: {vendor}\n"
                f"Transaction Date: {date}\n"
                f"Summary\n"
                f"Amount Before Tax: ${subtotal:.2f}\n"
                f"Sales Tax: ${tax:.2f}\n"
                f"Amount Charged: ${total:.2f}\n"
                f"We appreciate your business.\n"
            ),
            (
                f"Invoice Paid\n"
                f"From: {vendor}\n"
                f"Email Date: {date}\n"
                f"Charges\n"
                f"Merchandise Total: ${subtotal:.2f}\n"
                f"Tax Amount: ${tax:.2f}\n"
                f"Grand Total: ${total:.2f}\n"
                f"Keep this email for your records.\n"
            ),
            (
                f"Order Receipt\n"
                f"Store: {vendor}\n"
                f"Date: {date}\n"
                f"Breakdown\n"
                f"Subtotal Amount: ${subtotal:.2f}\n"
                f"Tax Collected: ${tax:.2f}\n"
                f"Total Paid: ${total:.2f}\n"
                f"Status: Completed\n"
            ),
            (
                f"Purchase Confirmation\n"
                f"Vendor: {vendor}\n"
                f"Processed On: {date}\n"
                f"Receipt Details\n"
                f"Items Subtotal: ${subtotal:.2f}\n"
                f"Tax: ${tax:.2f}\n"
                f"Final Charge: ${total:.2f}\n"
                f"Thanks for shopping with us.\n"
            ),
        ]
        return random.choice(templates)

    def _normalize_demo_rows(rows):
        out = []
        for item in rows:
            if not isinstance(item, dict):
                continue
            vendor = (item.get("vendor") or "").strip() or f"Vendor {uuid.uuid4().hex[:6]}"
            subtotal = _safe_float(item.get("subtotal"), random.uniform(6, 120))
            tax = round(subtotal * 0.0625, 2)
            total = round(subtotal + tax, 2)

            date = item.get("date")
            if not date:
                days_ago = random.randint(0, 30)
                date = (datetime.utcnow() - timedelta(days=days_ago)).strftime("%Y-%m-%d")

            sender = (item.get("from") or "").strip()
            if not sender:
                sender = f"notification-{uuid.uuid4().hex[:6]}@billing-updates.net"

            subject = (item.get("subject") or "").strip() or f"Your receipt from {vendor}"
            source_body = (item.get("body") or "").strip()
            clean_target = min(5, count)
            use_messy = len(out) >= clean_target
            body = _build_messy_body(vendor, date, subtotal, tax, total, source_body) if use_messy else _build_organized_body(vendor, date, subtotal, tax, total)
            out.append({
                "subject": subject,
                "from": sender,
                "date": date,
                "vendor": vendor,
                "subtotal": subtotal,
                "tax": tax,
                "total": total,
                "body": body,
            })
            if len(out) >= count:
                break
        return out

    last_error = None
    for _ in range(2):
        try:
            text = generate_text(
                prompt,
                temperature=0.8,
                max_output_tokens=2400,
            )
            match = re.search(r'\[.*\]', text, re.DOTALL)
            if not match:
                last_error = "No JSON array found in model output"
                continue
            data = json.loads(match.group(0))
            if isinstance(data, list) and data:
                normalized = _normalize_demo_rows(data)
                if normalized:
                    return normalized
            last_error = "Model returned empty/invalid list"
        except Exception as e:
            last_error = str(e)
            continue

    print(f"⚠️ Demo generation failed, using realistic fallback: {last_error}")

    # Real-world fallback vendor pool (used only when AI generation fails).
    fallback_vendors = [
        "Target", "Walmart", "Costco", "Best Buy", "Home Depot", "Lowe's",
        "Kroger", "Safeway", "Whole Foods Market", "Trader Joe's", "CVS Pharmacy",
        "Walgreens", "Starbucks", "Dunkin'", "Chipotle", "McDonald's", "Subway",
        "Panera Bread", "Domino's", "Pizza Hut", "Uber", "Lyft", "Airbnb",
        "Delta Air Lines", "United Airlines", "American Airlines", "Marriott",
        "Hilton", "Amazon", "Etsy", "eBay", "Apple", "Microsoft", "Google Store",
        "AT&T", "Verizon", "T-Mobile", "Netflix", "Spotify", "Adobe",
    ]

    def _sender_from_vendor(vendor_name: str) -> str:
        return f"notification-{uuid.uuid4().hex[:6]}@billing-updates.net"

    out = []
    sampled_vendors = random.sample(fallback_vendors, k=min(count, len(fallback_vendors)))
    while len(sampled_vendors) < count:
        sampled_vendors.append(random.choice(fallback_vendors))
    clean_target = min(5, count)
    for i in range(count):
        vendor = sampled_vendors[i]
        subtotal = round(random.uniform(8, 160), 2)
        tax = round(subtotal * 0.0625, 2)
        total = round(subtotal + tax, 2)
        days_ago = random.randint(0, 30)
        date = (datetime.utcnow() - timedelta(days=days_ago)).strftime("%Y-%m-%d")
        out.append({
            "subject": f"Your receipt from {vendor}",
            "from": _sender_from_vendor(vendor),
            "date": date,
            "vendor": vendor,
            "subtotal": subtotal,
            "tax": tax,
            "total": total,
            "body": _build_messy_body(vendor, date, subtotal, tax, total) if i >= clean_target else _build_organized_body(vendor, date, subtotal, tax, total),
        })
    return out

def _print_db_snapshot(limit: int = 50):
    """Print a snapshot of the latest transactions (date, vendor, amount)."""
    db = SessionLocal()
    try:
        rows = (
            db.query(Transaction)
            .order_by(Transaction.id.desc())
            .limit(limit)
            .all()
        )
        print("🧾 DB Snapshot (latest transactions):")
        if not rows:
            print("  (no rows found)")
            return
        for t in reversed(rows):
            date = t.date.strftime('%Y-%m-%d') if hasattr(t.date, "strftime") else str(t.date)
            vendor = (t.vendor or "Unknown").strip()
            amount = t.amount if t.amount is not None else 0
            print(f"  {date} | {vendor} | ${float(amount):.2f}")
    finally:
        db.close()

@app.post("/api/sync")
def sync_emails(request: Request):
    """Start email scraper in background; returns immediately so the request doesn't timeout."""
    try:
        _require_api_key(request)
        thread = threading.Thread(target=_run_sync, daemon=True)
        thread.start()
        return {"status": "success", "message": "Sync started. Fetching and parsing emails in the background—refresh in a minute to see new receipts."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Sync failed to start: {str(e)}")

@app.post("/api/demo-sync")
def demo_sync():
    """Generate demo emails with AI, parse them, and store transactions."""
    try:
        from .parser_select import parser_select
        from .data_helper import get_existing_email_ids, log_transaction
        emails = _generate_demo_emails(10)
        demo_rows = _prepare_demo_emails(emails)
        existing_ids = get_existing_email_ids()
        for email in demo_rows:
            email_id = email.get("id")
            if email_id in existing_ids:
                continue
            try:
                parsed = parser_select(email)
                if parsed and isinstance(parsed, dict):
                    saved = log_transaction(parsed)
                    if saved is not None:
                        existing_ids.add(email_id)
            except Exception as row_error:
                print(f"⚠️ Demo parse failed for {email_id}: {row_error}")
                continue

        _demo_emails_path().write_text(json.dumps(demo_rows, indent=2))
        return {"status": "success", "count": len(demo_rows)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Demo sync failed: {e}")

@app.post("/api/demo-generate")
def demo_generate():
    """Generate demo emails only (no parsing)."""
    try:
        emails = _generate_demo_emails(10)
        demo_rows = _prepare_demo_emails(emails)
        _demo_emails_path().write_text(json.dumps(demo_rows, indent=2))
        return {"status": "success", "count": len(demo_rows)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Demo generation failed: {e}")

@app.post("/api/demo-parse")
def demo_parse(force_reprocess: bool = False):
    """Parse existing demo emails in background and expose progress logs."""
    try:
        run_id = uuid.uuid4().hex
        _init_demo_run(run_id, force_reprocess=force_reprocess)
        thread = threading.Thread(target=_run_demo_parse, args=(run_id, force_reprocess), daemon=True)
        thread.start()
        return {"status": "started", "run_id": run_id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Demo parse failed to start: {e}")

@app.get("/api/demo-parse-status")
def demo_parse_status(run_id: str):
    run = _get_demo_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    return run

@app.get("/api/demo-emails")
def demo_emails():
    """Return last generated demo emails."""
    path = _demo_emails_path()
    if not path.exists():
        return []
    try:
        return json.loads(path.read_text())
    except Exception:
        return []

@app.delete("/api/transactions/clear")
def clear_transactions(request: Request):
    """Delete all transactions (protected by API key)."""
    _require_api_key(request)
    db = SessionLocal()
    try:
        deleted = db.query(Transaction).delete()
        db.commit()
        return {"status": "success", "deleted": deleted}
    finally:
        db.close()

@app.post("/api/vendor-pie")
async def vendor_pie(request: Request):
    """Generate a vendor spend pie chart from CSV body."""
    try:
        raw = await request.body()
        csv_text = raw.decode("utf-8", errors="ignore")
        if not csv_text.strip():
            raise HTTPException(status_code=400, detail="CSV body is empty")

        df = pd.read_csv(StringIO(csv_text))
        if df.empty:
            raise HTTPException(status_code=400, detail="CSV contains no rows")

        cols = {c.lower().strip(): c for c in df.columns}
        vendor_col = cols.get("vendor")
        amount_col = cols.get("amount")
        if not vendor_col or not amount_col:
            raise HTTPException(status_code=400, detail="CSV must include Vendor and Amount columns")

        amounts = (
            df[amount_col]
            .astype(str)
            .str.replace("$", "", regex=False)
            .str.replace(",", "", regex=False)
        )
        df["_amount"] = pd.to_numeric(amounts, errors="coerce")
        df = df.dropna(subset=["_amount"])
        df = df[df["_amount"] > 0]
        if df.empty:
            raise HTTPException(status_code=400, detail="No positive amounts to chart")

        grouped = df.groupby(vendor_col)["_amount"].sum().sort_values(ascending=False)
        totals = grouped.to_dict()
        total_sum = sum(totals.values())
        breakdown = [
            {"vendor": k, "total": float(v), "percent": float(v / total_sum * 100)}
            for k, v in totals.items()
        ]

        # Keep colors deterministic so legend matches chart
        palette = [
            "#ef4444", "#f97316", "#f59e0b", "#84cc16", "#10b981",
            "#14b8a6", "#06b6d4", "#0ea5e9", "#6366f1", "#8b5cf6",
            "#d946ef", "#ec4899",
        ]
        labels = list(totals.keys())
        values = list(totals.values())
        colors = [palette[i % len(palette)] for i in range(len(labels))]

        fig, ax = plt.subplots(figsize=(5, 5), dpi=150)
        ax.pie(
            values,
            labels=labels,
            colors=colors,
            autopct="%1.1f%%",
            startangle=90,
            textprops={"fontsize": 8},
        )
        ax.axis("equal")
        buf = BytesIO()
        fig.savefig(buf, format="png", bbox_inches="tight")
        plt.close(fig)
        buf.seek(0)
        image_b64 = base64.b64encode(buf.read()).decode("ascii")

        return {"image_base64": image_b64, "breakdown": breakdown, "colors": colors}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Chart generation failed: {e}")

@app.put("/api/transactions/{transaction_id}")
def update_transaction(transaction_id: int, payload: dict = Body(...)):
    """Update a transaction's vendor, amount, tax, or date."""
    db = SessionLocal()
    try:
        tx = db.query(Transaction).filter(Transaction.id == transaction_id).first()
        if not tx:
            raise HTTPException(status_code=404, detail="Transaction not found")

        if "vendor" in payload:
            vendor = (payload.get("vendor") or "").strip()
            if vendor:
                tx.vendor = vendor
        if "amount" in payload:
            try:
                tx.amount = float(str(payload["amount"]).replace("$", "").replace(",", "").strip())
            except Exception:
                raise HTTPException(status_code=400, detail="Invalid amount")
        if "tax" in payload:
            try:
                tx.tax = float(str(payload["tax"]).replace("$", "").replace(",", "").strip())
            except Exception:
                raise HTTPException(status_code=400, detail="Invalid tax")
        if "date" in payload:
            try:
                tx.date = date_parser.parse(str(payload["date"]))
            except Exception:
                raise HTTPException(status_code=400, detail="Invalid date")

        db.commit()
        db.refresh(tx)
        return {"status": "success", "id": tx.id}
    finally:
        db.close()

@app.delete("/api/transactions/{transaction_id}")
def delete_transaction(transaction_id: int):
    """Delete a transaction by ID."""
    db = SessionLocal()
    try:
        tx = db.query(Transaction).filter(Transaction.id == transaction_id).first()
        if not tx:
            raise HTTPException(status_code=404, detail="Transaction not found")
        db.delete(tx)
        db.commit()
        return {"status": "success", "id": transaction_id}
    finally:
        db.close()

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)

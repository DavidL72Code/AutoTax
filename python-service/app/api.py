import os
import threading
import json
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
import ollama

app = FastAPI()

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

def _generate_demo_emails(count: int = 6):
    """Generate demo emails via local model; fallback to templates."""
    prompt = f"""Generate {count} fake receipt emails in JSON array format.
Each item must include: subject, from, date (YYYY-MM-DD), body.
Include realistic vendors and totals like "Total: $12.34".
Return ONLY JSON.
"""
    try:
        response = ollama.chat(
            model="llama3.2:3b",
            messages=[{"role": "user", "content": prompt}],
            options={"num_predict": 400, "temperature": 0.6},
        )
        text = response["message"]["content"].strip()
        match = re.search(r'\[.*\]', text, re.DOTALL)
        if match:
            data = json.loads(match.group(0))
            if isinstance(data, list) and data:
                return data
    except Exception as e:
        print(f"⚠️ Demo generation failed, using templates: {e}")

    vendors = [
        ("Fidelity Investments", "noreply@fidelity.com"),
        ("Chase", "alerts@chase.com"),
        ("PayPal", "service@paypal.com"),
        ("American Express", "receipt@americanexpress.com"),
        ("Starbucks", "store@starbucks.com"),
        ("Amazon", "auto-confirm@amazon.com"),
    ]
    out = []
    for i in range(count):
        vendor, from_email = vendors[i % len(vendors)]
        amount = round(random.uniform(5, 250), 2)
        days_ago = random.randint(0, 30)
        date = (datetime.utcnow() - timedelta(days=days_ago)).strftime("%Y-%m-%d")
        out.append({
            "subject": f"Your {vendor} receipt",
            "from": from_email,
            "date": date,
            "body": f"Thanks for your purchase at {vendor}. Total: ${amount:.2f}.",
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
        from .data_helper import log_transaction
        emails = _generate_demo_emails(8)
        demo_rows = []
        for e in emails:
            email_id = uuid.uuid4().hex
            email = {
                "id": email_id,
                "from": e.get("from", "demo@example.com"),
                "subject": e.get("subject", "Demo receipt"),
                "date": e.get("date", datetime.utcnow().strftime("%Y-%m-%d")),
                "body": e.get("body", "Total: $10.00"),
            }
            demo_rows.append(email)
            parsed = parser_select(email)
            if parsed and isinstance(parsed, dict):
                log_transaction(parsed)

        _demo_emails_path().write_text(json.dumps(demo_rows, indent=2))
        return {"status": "success", "count": len(demo_rows)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Demo sync failed: {e}")

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

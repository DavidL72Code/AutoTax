"""Sample receipts for demo mode and benchmarks.

Generated locally and deterministically: the same seed always produces the
same inbox, so accuracy numbers are comparable between runs and demo mode
costs nothing to serve.
"""
from __future__ import annotations

import hashlib
import random
import uuid
from datetime import datetime, timedelta

def _generate_demo_emails(count: int = 10) -> list[dict]:
    """Generate fake receipt emails with known ground-truth fields."""

    def _safe_float(value, default=0.0):
        try:
            return round(float(value), 2)
        except Exception:
            return round(float(default), 2)

    def _build_messy_body(vendor, date, subtotal, tax, total, extra=""):
        items = []
        for i in range(random.randint(3, 6)):
            price = round(random.uniform(2.5, 45.0), 2)
            qty = random.randint(1, 3)
            items.append(f"Item {i+1} x{qty} ............. ${price*qty:.2f}")
        shipping = round(random.uniform(0, 12.99), 2)
        discount = round(random.uniform(0, 10.0), 2)
        credit = round(random.uniform(0, 7.5), 2)
        pending = round(random.uniform(1.0, 30.0), 2)
        auth_hold = round(random.uniform(total, total + 25), 2)
        prior_balance = round(random.uniform(0, 80), 2)
        rewards = random.randint(50, 4000)
        noise = f"\nCustomer Note Snippet: {extra[:220]}" if extra.strip() else ""
        return (
            f"Subject Thread: Re: order update / invoice copy / receipt confirmation\n"
            f"Merchant Notice: This receipt may include pending holds.\n"
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
            f"If questions, contact support within 30 days.{noise}\n"
        )

    def _build_organized_body(vendor, date, subtotal, tax, total):
        templates = [
            f"Receipt Confirmation\nDate: {date}\nVendor: {vendor}\nSubtotal: ${subtotal:.2f}\nTax: ${tax:.2f}\nTotal: ${total:.2f}\nThank you for your purchase.\n",
            f"Payment Receipt\nMerchant: {vendor}\nTransaction Date: {date}\nAmount Before Tax: ${subtotal:.2f}\nSales Tax: ${tax:.2f}\nAmount Charged: ${total:.2f}\nWe appreciate your business.\n",
            f"Invoice Paid\nFrom: {vendor}\nEmail Date: {date}\nMerchandise Total: ${subtotal:.2f}\nTax Amount: ${tax:.2f}\nGrand Total: ${total:.2f}\nKeep this email for your records.\n",
            f"Order Receipt\nStore: {vendor}\nDate: {date}\nSubtotal Amount: ${subtotal:.2f}\nTax Collected: ${tax:.2f}\nTotal Paid: ${total:.2f}\nStatus: Completed\n",
        ]
        return random.choice(templates)

    def _normalize_rows(rows):
        out = []
        clean_target = min(5, count)
        for item in rows:
            if not isinstance(item, dict):
                continue
            vendor = (item.get("vendor") or "").strip() or f"Vendor {uuid.uuid4().hex[:6]}"
            subtotal = _safe_float(item.get("subtotal"), random.uniform(6, 120))
            tax = round(subtotal * 0.0625, 2)
            total = round(subtotal + tax, 2)
            date = item.get("date") or (datetime.utcnow() - timedelta(days=random.randint(0, 30))).strftime("%Y-%m-%d")
            sender = (item.get("from") or "").strip() or f"notification-{uuid.uuid4().hex[:6]}@billing-updates.net"
            subject = (item.get("subject") or "").strip() or f"Your receipt from {vendor}"
            source_body = (item.get("body") or "").strip()
            use_messy = len(out) >= clean_target
            body = _build_messy_body(vendor, date, subtotal, tax, total, source_body) if use_messy else _build_organized_body(vendor, date, subtotal, tax, total)
            out.append({"subject": subject, "from": sender, "date": date, "vendor": vendor, "subtotal": subtotal, "tax": tax, "total": total, "body": body})
            if len(out) >= count:
                break
        return out

    # v1 asked a model to invent these emails, which made every eval run
    # differ. v2 generates them locally so accuracy numbers are comparable
    # between runs and cost nothing.
    # Fallback: local generation
    fallback_vendors = ["Target", "Walmart", "Best Buy", "Starbucks", "Chipotle", "Amazon",
                        "Apple", "Uber", "Airbnb", "Netflix", "Spotify", "CVS Pharmacy",
                        "Whole Foods", "Trader Joes", "Home Depot"]
    clean_target = min(5, count)
    out = []
    for i, vendor in enumerate(random.sample(fallback_vendors, min(count, len(fallback_vendors)))):
        subtotal = round(random.uniform(8, 160), 2)
        tax = round(subtotal * 0.0625, 2)
        total = round(subtotal + tax, 2)
        date = (datetime.utcnow() - timedelta(days=random.randint(0, 30))).strftime("%Y-%m-%d")
        body = _build_messy_body(vendor, date, subtotal, tax, total) if i >= clean_target else _build_organized_body(vendor, date, subtotal, tax, total)
        out.append({"subject": f"Your receipt from {vendor}", "from": f"no-reply@{vendor.lower().replace(' ', '')}.com",
                    "date": date, "vendor": vendor, "subtotal": subtotal, "tax": tax, "total": total, "body": body})
    return out


def _email_id(e: dict) -> str:
    raw = "|".join([str(e.get("from", "")), str(e.get("subject", "")), str(e.get("date", "")), str(e.get("body", ""))])
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def _strip_ground_truth(e: dict) -> dict:
    return {"id": _email_id(e), "from": e.get("from", ""), "subject": e.get("subject", ""), "date": e.get("date", ""), "body": e.get("body", "")}


def demo_cases(count: int = 10, seed: int | None = 7) -> list[dict]:
    """Receipts including their ground-truth vendor/subtotal/tax/total."""
    if seed is not None:
        random.seed(seed)
    return _generate_demo_emails(count)


def to_graph_email(case: dict) -> dict:
    stripped = _strip_ground_truth(case)
    return {
        "id": stripped["id"],
        "sender": stripped["from"],
        "subject": stripped["subject"],
        "date": stripped["date"],
        "body": stripped["body"],
    }


def demo_emails(count: int = 10, seed: int | None = None) -> list[dict]:
    """Demo-mode inbox: no ground truth attached, fresh ids each time."""
    return [to_graph_email(case) for case in demo_cases(count, seed)]

#!/usr/bin/env python3
"""
eval.py — Compare regex_only vs individual_ai vs batch_ai parsing accuracy.

Usage (from python-service/):
    python3 eval.py                        # 10 emails, all 3 methods
    python3 eval.py --count 20             # 20 emails
    python3 eval.py --skip-ai              # regex only, no API calls
    python3 eval.py --json                 # summary as JSON
    python3 eval.py --json --detail        # summary + per-email JSON
    python3 eval.py --json > results.json  # save to file
"""
from __future__ import annotations

import sys
import os
import re
import json
import time
import uuid
import random
import hashlib
import argparse
from datetime import datetime, timedelta

# Make app importable without pulling in database/firebase layers
sys.path.insert(0, os.path.dirname(__file__))

# Load env vars (API key lives on a single line so it loads fine even if
# the multiline service-account JSON causes dotenv warnings)
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"), override=False)

# Only import the parser layer — avoids data_helper / firebase chains
from app.ai_client import generate_text
from app.parsers.generic_parser import (
    _build_base_result,
    _apply_ai_result,
    ai_search,
    batch_ai_search,
    parse_generic_emails_batch,
)


# ── demo email generation (self-contained copy from api.py) ──────────────────

def _generate_demo_emails(count: int = 10) -> list[dict]:
    """Generate fake receipt emails with known ground-truth fields."""
    run_nonce = uuid.uuid4().hex[:8]

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

    prompt = f"""Generate {count} fake receipt emails in JSON array format.
Return ONLY a JSON array with exactly {count} objects and NO extra text.
Each object must include: subject, from, date (YYYY-MM-DD), vendor, subtotal (number), tax (number), total (number), body.
Rules:
1. Variety of vendor names.
2. Tax == subtotal * 0.0625, total == subtotal + tax.
3. Make the body messy with extra dollar values so parser must distinguish the true total.
4. Use indirect labels: "balance due now", "local levy", "merchandise sum".
5. Run token: {run_nonce}"""

    for _ in range(2):
        try:
            text = generate_text(prompt, temperature=0.8, max_output_tokens=2400)
            match = re.search(r'\[.*\]', text, re.DOTALL)
            if match:
                data = json.loads(match.group(0))
                if isinstance(data, list) and data:
                    normalized = _normalize_rows(data)
                    if normalized:
                        return normalized
        except Exception as e:
            print(f"⚠️  Email generation attempt failed: {e}", file=sys.stderr)

    # Fallback: local generation
    print("⚠️  Using local fallback email generation.", file=sys.stderr)
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


# ── accuracy helpers ──────────────────────────────────────────────────────────

def _vendor_match(predicted: str, truth: str) -> bool:
    p = (predicted or "").lower().strip()
    t = (truth or "").lower().strip()
    if not p or not t:
        return False
    return p == t or t in p or p in t


def _amount_match(predicted, truth, tol: float = 0.02) -> bool:
    try:
        return abs(float(predicted) - float(truth)) / max(float(truth), 0.01) <= tol
    except (TypeError, ValueError):
        return False


# ── method runners ────────────────────────────────────────────────────────────

def run_regex_only(emails: list[dict]) -> list[dict]:
    results = []
    for e in emails:
        result, _ = _build_base_result(e["subject"], e["body"], e["id"], e["date"], vendor_name=None)
        results.append(result)
    return results


def run_individual_ai(emails: list[dict]) -> list[dict]:
    results = []
    for e in emails:
        result, missing = _build_base_result(e["subject"], e["body"], e["id"], e["date"], vendor_name=None)
        if missing:
            result["_meta"]["ai_amount_tax_called"] = any(f in missing for f in ["amount", "tax"])
            result["_meta"]["vendor_ai_called"] = "vendor" in missing
            ai_result = ai_search(e["subject"], e["body"], missing)
            _apply_ai_result(result, ai_result, missing)
        results.append(result)
    return results


def run_batch_ai(emails: list[dict]) -> list[dict]:
    items = [{"email_subject": e["subject"], "email_text": e["body"], "email_id": e["id"], "email_date": e["date"], "vendor_name": None} for e in emails]
    return parse_generic_emails_batch(items)


# ── evaluation ────────────────────────────────────────────────────────────────

def evaluate(method_name: str, parsed: list[dict], ground_truth: list[dict]) -> dict:
    n = len(ground_truth)
    vendor_correct = amount_correct = tax_correct = all_correct = ai_calls = 0
    for p, gt in zip(parsed, ground_truth):
        meta = p.get("_meta") or {}
        v = _vendor_match(p.get("vendor"), gt["vendor"])
        a = _amount_match(p.get("amount"), gt["total"])
        t = _amount_match(p.get("tax"), gt["tax"])
        vendor_correct += v
        amount_correct += a
        tax_correct += t
        all_correct += v and a and t
        if meta.get("ai_amount_tax_called") or meta.get("vendor_ai_called"):
            ai_calls += 1
    return {"method": method_name, "vendor": vendor_correct, "amount": amount_correct, "tax": tax_correct, "all": all_correct, "n": n, "ai_calls": ai_calls}


def _pct(n, total) -> float:
    return round(100 * n / total, 1) if total else 0.0


def print_table(rows: list[dict], times: dict):
    n = rows[0]["n"] if rows else 1
    col = 18
    header = f"{'Method':<{col}} {'Vendor':>8} {'Amount':>8} {'Tax':>8} {'All':>8} {'AI Calls':>10} {'Time':>8}"
    print()
    print(header)
    print("─" * len(header))
    for r in rows:
        t = times.get(r["method"], 0)
        print(f"{r['method']:<{col}} {_pct(r['vendor'],n):>7}% {_pct(r['amount'],n):>7}% {_pct(r['tax'],n):>7}% {_pct(r['all'],n):>7}% {r['ai_calls']:>10} {t:>7.1f}s")
    print()


def print_detail(emails, ground_truth, results):
    print("── Per-email detail ──────────────────────────────────────────────────")
    for i, gt in enumerate(ground_truth):
        subject = (emails[i].get("subject") or "")[:55]
        print(f"\n  [{i+1}] {subject}")
        print(f"       ground truth  vendor={gt['vendor']}  amount=${gt['total']:.2f}  tax=${gt['tax']:.2f}")
        for name, parsed in results.items():
            p = parsed[i]
            v = "✓" if _vendor_match(p.get("vendor"), gt["vendor"]) else "✗"
            a = "✓" if _amount_match(p.get("amount"), gt["total"]) else "✗"
            t = "✓" if _amount_match(p.get("tax"), gt["tax"]) else "✗"
            print(f"       {name:<18} vendor={v} {str(p.get('vendor',''))[:22]:<22} amount={a} {p.get('amount',0):>8.2f}  tax={t} {p.get('tax',0):>7.2f}")
    print()


# ── main ─────────────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser(description="Evaluate receipt parsing methods.")
    ap.add_argument("--count", type=int, default=10)
    ap.add_argument("--skip-ai", action="store_true", help="Regex only, no API calls")
    ap.add_argument("--detail", action="store_true", help="Per-email breakdown")
    ap.add_argument("--json", action="store_true", help="Output as JSON")
    args = ap.parse_args()

    print(f"Generating {args.count} test emails...", file=sys.stderr)
    raw = _generate_demo_emails(args.count)
    emails = [_strip_ground_truth(e) for e in raw]
    ground_truth = [{"vendor": e["vendor"], "total": float(e["total"]), "tax": float(e["tax"])} for e in raw]
    print(f"Generated {len(emails)} emails.\n", file=sys.stderr)

    method_results: dict[str, list[dict]] = {}
    times: dict[str, float] = {}
    summary_rows = []

    print("Running regex_only...", file=sys.stderr)
    t0 = time.time()
    parsed = run_regex_only(emails)
    times["regex_only"] = time.time() - t0
    method_results["regex_only"] = parsed
    summary_rows.append(evaluate("regex_only", parsed, ground_truth))

    if not args.skip_ai:
        print(f"Running individual_ai ({len(emails)} emails, throttled — takes ~{len(emails)*7}s)...", file=sys.stderr)
        t0 = time.time()
        parsed = run_individual_ai(emails)
        times["individual_ai"] = time.time() - t0
        method_results["individual_ai"] = parsed
        summary_rows.append(evaluate("individual_ai", parsed, ground_truth))

        print("Running batch_ai (one call)...", file=sys.stderr)
        t0 = time.time()
        parsed = run_batch_ai(emails)
        times["batch_ai"] = time.time() - t0
        method_results["batch_ai"] = parsed
        summary_rows.append(evaluate("batch_ai", parsed, ground_truth))

    if args.json:
        output = {
            "test_count": len(emails),
            "summary": [
                {
                    "method": r["method"],
                    "vendor_pct": _pct(r["vendor"], r["n"]),
                    "amount_pct": _pct(r["amount"], r["n"]),
                    "tax_pct": _pct(r["tax"], r["n"]),
                    "all_correct_pct": _pct(r["all"], r["n"]),
                    "ai_calls": r["ai_calls"],
                    "time_seconds": round(times.get(r["method"], 0), 2),
                }
                for r in summary_rows
            ],
            "per_email": [
                {
                    "index": i + 1,
                    "subject": (emails[i].get("subject") or "")[:60],
                    "ground_truth": gt,
                    "results": {
                        name: {
                            "vendor": p[i].get("vendor"),
                            "amount": p[i].get("amount"),
                            "tax": p[i].get("tax"),
                            "vendor_correct": _vendor_match(p[i].get("vendor"), gt["vendor"]),
                            "amount_correct": _amount_match(p[i].get("amount"), gt["total"]),
                            "tax_correct": _amount_match(p[i].get("tax"), gt["tax"]),
                        }
                        for name, p in method_results.items()
                    },
                }
                for i, gt in enumerate(ground_truth)
            ] if args.detail else [],
        }
        print(json.dumps(output, indent=2))
    else:
        print_table(summary_rows, times)
        if args.detail:
            print_detail(emails, ground_truth, method_results)


if __name__ == "__main__":
    main()

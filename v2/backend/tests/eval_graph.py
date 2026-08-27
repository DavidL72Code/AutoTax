#!/usr/bin/env python3
"""Accuracy and cost benchmark for the receipt graph.

    ./.venv/bin/python tests/eval_graph.py            # full graph, model enabled
    ./.venv/bin/python tests/eval_graph.py --no-llm   # rules only, free, instant
    ./.venv/bin/python tests/eval_graph.py -n 20      # bigger sample
    ./.venv/bin/python tests/eval_graph.py --json     # machine-readable

"API calls" is the number of HTTP requests actually sent to Gemini, which is
what the batching in app/llm.py is there to hold down — it is normally far
lower than the number of emails that needed a model.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import sys
import time

import _harness  # noqa: F401  - sets sys.path and exposes the memory store
import fixtures
from _harness import use_memory_store


def vendor_match(predicted, truth) -> bool:
    # Punctuation and spacing differences ("Trader Joe's" vs "Trader Joes")
    # are not extraction errors, so they are normalised away before comparing.
    norm = lambda s: re.sub(r"[^a-z0-9]", "", (s or "").lower())
    p, t = norm(predicted), norm(truth)
    if not p or not t:
        return False
    return p == t or p in t or t in p


def amount_match(predicted, truth, tol: float = 0.02) -> bool:
    try:
        return abs(float(predicted) - float(truth)) / max(float(truth), 0.01) <= tol
    except (TypeError, ValueError):
        return False


def score(records: list[dict], truth: list[dict]) -> dict:
    hits = {"vendor": 0, "amount": 0, "tax": 0, "all": 0}
    for record, expected in zip(records, truth):
        checks = {
            "vendor": vendor_match(record.get("vendor"), expected["vendor"]),
            "amount": amount_match(record.get("amount"), expected["amount"]),
            "tax": amount_match(record.get("tax"), expected["tax"]) or (
                record.get("tax") in (0, 0.0) and expected["tax"] == 0
            ),
        }
        for field, ok in checks.items():
            hits[field] += int(ok)
        hits["all"] += int(all(checks.values()))
    n = max(len(truth), 1)
    return {field: round(100 * count / n) for field, count in hits.items()}


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("-n", "--count", type=int, default=10)
    parser.add_argument("--no-llm", action="store_true", help="disable model calls entirely")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--detail", action="store_true")
    args = parser.parse_args()

    if args.no_llm:
        os.environ["GOOGLE_API_KEY"] = ""

    from app import llm
    from app.graph.runner import run_many

    if args.no_llm:
        llm.settings.google_api_key = ""

    use_memory_store()
    emails, truth = fixtures.make_cases(args.count)

    llm.reset_calls()
    started = time.perf_counter()
    records = await run_many(emails)
    elapsed = time.perf_counter() - started

    accuracy = score(records, truth)
    needed_model = sum(1 for r in records if r.get("llm_calls", 0) > 0)
    summary = {
        "mode": "rules_only" if args.no_llm else "graph",
        "emails": len(emails),
        **accuracy,
        "emails_needing_model": needed_model,
        "gemini_requests": llm.calls_made(),
        "seconds": round(elapsed, 2),
        "auto_saved": sum(1 for r in records if r.get("status") == "parsed"),
        "flagged_for_review": sum(1 for r in records if r.get("status") == "needs_review"),
    }

    if args.json:
        print(json.dumps({"summary": summary, "records": records if args.detail else []}, indent=2, default=str))
        return 0

    print(f"\n  {summary['mode']} · {summary['emails']} emails · {summary['seconds']}s")
    print(f"  vendor {accuracy['vendor']}%   amount {accuracy['amount']}%   tax {accuracy['tax']}%   all three {accuracy['all']}%")
    print(f"  {needed_model} emails needed the model → {summary['gemini_requests']} Gemini requests")
    print(f"  {summary['auto_saved']} auto-saved · {summary['flagged_for_review']} flagged for review\n")

    if args.detail:
        for record, expected in zip(records, truth):
            ok = "✓" if all(
                [vendor_match(record.get("vendor"), expected["vendor"]),
                 amount_match(record.get("amount"), expected["amount"]),
                 amount_match(record.get("tax"), expected["tax"])]
            ) else "✗"
            print(f"  {ok} {str(record.get('vendor')):18} {str(record.get('amount')):>9} "
                  f"(truth {expected['vendor']} {expected['amount']}) conf={record.get('confidence')}")
            for s in record.get("steps", []):
                print(f"      {s['node']:9} {s['detail']} ({s['ms']}ms)")
    return 0


if __name__ == "__main__":
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    raise SystemExit(asyncio.run(main()))

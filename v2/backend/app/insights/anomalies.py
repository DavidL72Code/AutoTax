"""Things in the ledger worth a second look.

Each finding names the receipts it is about and says what to do, because an
alert you cannot act on is noise. Severity is deliberately coarse: `action`
means money is probably wrong, `watch` means it changed.
"""
from __future__ import annotations

import statistics
from collections import defaultdict
from datetime import date
from typing import Any, Optional

DUPLICATE_WINDOW_DAYS = 3
OUTLIER_MULTIPLE = 3.0
TAX_EXPECTED_SHARE = 0.7
MIN_TAXABLE_AMOUNT = 10.0


def _parse(value: Any) -> Optional[date]:
    try:
        return date.fromisoformat(str(value)[:10])
    except (TypeError, ValueError):
        return None


def _finding(
    kind: str,
    severity: str,
    title: str,
    detail: str,
    amount: float,
    ids: list[str],
    vendor: Optional[str] = None,
    *,
    params: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """`ids` names the exact rows a finding is about. A subscription finding is
    derived from a rollup rather than from rows, so it carries `vendor` instead
    — either way the UI can take you to the receipts behind the claim."""
    return {
        "kind": kind,
        "severity": severity,
        "title": title,
        "detail": detail,
        "amount": round(amount, 2),
        "transaction_ids": ids,
        "vendor": vendor,
        # `title`/`detail` are the English sentences; `kind` plus `params` is the
        # same finding with the grammar left to whoever renders it.
        "params": params or {},
    }


def _duplicates(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Same merchant, same amount, days apart — a double charge or a double sync."""
    by_key: dict[tuple[str, float], list[dict]] = defaultdict(list)
    for row in rows:
        vendor, amount, when = row.get("vendor"), row.get("amount"), _parse(row.get("date"))
        if vendor and amount and when:
            by_key[(vendor, round(float(amount), 2))].append({**row, "_date": when})

    findings = []
    for (vendor, amount), group in by_key.items():
        if len(group) < 2:
            continue
        group.sort(key=lambda r: r["_date"])
        for earlier, later in zip(group, group[1:]):
            if (later["_date"] - earlier["_date"]).days > DUPLICATE_WINDOW_DAYS:
                continue
            if earlier.get("email_id") and earlier.get("email_id") == later.get("email_id"):
                continue
            findings.append(_finding(
                "duplicate", "action",
                f"Possible duplicate charge at {vendor}",
                f"${amount:.2f} charged twice within "
                f"{(later['_date'] - earlier['_date']).days} day(s). Check for a double billing "
                f"or two confirmation emails for one order.",
                amount,
                [str(earlier.get("id")), str(later.get("id"))],
                params={"vendor": vendor, "amount": amount,
                        "days": (later["_date"] - earlier["_date"]).days},
            ))
    return findings


def _outliers(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """A charge far outside what this merchant normally costs."""
    by_vendor: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        if row.get("vendor") and row.get("amount"):
            by_vendor[row["vendor"]].append(row)

    findings = []
    for vendor, group in by_vendor.items():
        if len(group) < 5:
            continue
        amounts = [float(r["amount"]) for r in group]
        middle = statistics.median(amounts)
        deviation = statistics.median([abs(a - middle) for a in amounts]) or (middle * 0.1)
        for row in group:
            amount = float(row["amount"])
            if amount > middle + OUTLIER_MULTIPLE * deviation and amount > middle * 2:
                findings.append(_finding(
                    "outlier", "watch",
                    f"Unusually large charge at {vendor}",
                    f"${amount:.2f} against a typical ${middle:.2f} across {len(group)} receipts.",
                    amount, [str(row.get("id"))],
                    params={"vendor": vendor, "amount": amount,
                            "typical": round(middle, 2), "receipts": len(group)},
                ))
    return findings


def _missing_tax(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """A merchant that normally charges tax, on a receipt with none.

    Usually a parsing miss rather than a merchant error, which is exactly why
    it is worth surfacing: it understates recoverable tax.
    """
    by_vendor: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        if row.get("vendor") and row.get("amount"):
            by_vendor[row["vendor"]].append(row)

    findings = []
    for vendor, group in by_vendor.items():
        if len(group) < 4:
            continue
        with_tax = [r for r in group if r.get("tax")]
        if len(with_tax) / len(group) < TAX_EXPECTED_SHARE:
            continue
        for row in group:
            if not row.get("tax") and float(row.get("amount") or 0) >= MIN_TAXABLE_AMOUNT:
                findings.append(_finding(
                    "missing_tax", "watch",
                    f"No tax recorded for {vendor}",
                    f"{vendor} charged tax on {len(with_tax)} of {len(group)} receipts, but this "
                    f"${float(row['amount']):.2f} charge has none.",
                    float(row["amount"]), [str(row.get("id"))],
                    params={"vendor": vendor, "amount": float(row["amount"]),
                            "with_tax": len(with_tax), "receipts": len(group)},
                ))
    return findings


def _subscription_changes(subscriptions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    findings = []
    for sub in subscriptions:
        if sub["price_change_pct"] > 0:
            baseline = sub.get("baseline_amount", sub["typical_amount"])
            annual_delta = (sub["latest_amount"] - baseline) * sub.get("periods_per_year", 12)
            findings.append(_finding(
                "price_increase", "action" if sub["price_change_pct"] >= 15 else "watch",
                f"{sub['vendor']} went up {sub['price_change_pct']:.0f}%",
                f"Now ${sub['latest_amount']:.2f} {sub['cadence']}, was ${baseline:.2f}. That is "
                f"${annual_delta:.2f} more per year.",
                sub["latest_amount"], [], sub["vendor"],
                params={"vendor": sub["vendor"], "pct": round(sub["price_change_pct"]),
                        "latest": sub["latest_amount"], "baseline": baseline,
                        "cadence": sub["cadence"], "annual_delta": annual_delta},
            ))
        if sub["days_overdue"] > sub["interval_days"]:
            findings.append(_finding(
                "lapsed", "watch",
                f"No charge from {sub['vendor']} since {sub['last_charged']}",
                f"A {sub['cadence']} charge is {sub['days_overdue']} days late. Either it was "
                f"cancelled, or the receipt never arrived.",
                sub["typical_amount"], [], sub["vendor"],
                params={"vendor": sub["vendor"], "last_charged": sub["last_charged"],
                        "cadence": sub["cadence"], "days_overdue": sub["days_overdue"]},
            ))
    return findings


def _unresolved(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    flagged = [r for r in rows if r.get("status") == "needs_review"]
    if not flagged:
        return []
    return [_finding(
        "needs_review", "action",
        f"{len(flagged)} receipt(s) still need a human",
        "These are excluded from nothing. They are in your totals with the values the pipeline "
        "could prove, which may be incomplete.",
        sum(float(r.get("amount") or 0) for r in flagged),
        [str(r.get("id")) for r in flagged],
        params={"count": len(flagged)},
    )]


def detect(rows: list[dict[str, Any]], subscriptions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    findings = [
        *_duplicates(rows),
        *_subscription_changes(subscriptions),
        *_outliers(rows),
        *_missing_tax(rows),
        *_unresolved(rows),
    ]
    order = {"action": 0, "watch": 1}
    return sorted(findings, key=lambda f: (order.get(f["severity"], 2), -f["amount"]))

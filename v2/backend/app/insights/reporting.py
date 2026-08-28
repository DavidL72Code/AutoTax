"""Statements and rollups — the outputs someone actually files or acts on."""
from __future__ import annotations

from calendar import monthrange
from collections import defaultdict
from datetime import date
from typing import Any, Optional

from .accounts import account_for


def _parse(value: Any) -> Optional[date]:
    try:
        return date.fromisoformat(str(value)[:10])
    except (TypeError, ValueError):
        return None


def _amount(row: dict[str, Any]) -> float:
    try:
        return float(row.get("amount") or 0)
    except (TypeError, ValueError):
        return 0.0


def _tax(row: dict[str, Any]) -> float:
    try:
        return float(row.get("tax") or 0)
    except (TypeError, ValueError):
        return 0.0


def _month_key(value: date) -> str:
    return f"{value.year:04d}-{value.month:02d}"


def _previous_month(month: str) -> str:
    year, mon = int(month[:4]), int(month[5:7])
    return f"{year - 1:04d}-12" if mon == 1 else f"{year:04d}-{mon - 1:02d}"


def monthly_statement(rows: list[dict[str, Any]], month: str, today: Optional[date] = None) -> dict[str, Any]:
    """One month, with the comparison that makes the number mean something."""
    today = today or date.today()
    dated = [(row, _parse(row.get("date"))) for row in rows]
    current = [r for r, d in dated if d and _month_key(d) == month]
    previous_key = _previous_month(month)
    previous = [r for r, d in dated if d and _month_key(d) == previous_key]

    total = sum(_amount(r) for r in current)
    prior_total = sum(_amount(r) for r in previous)

    by_category: dict[str, float] = defaultdict(float)
    prior_by_category: dict[str, float] = defaultdict(float)
    for row in current:
        by_category[row.get("category") or "Other"] += _amount(row)
    for row in previous:
        prior_by_category[row.get("category") or "Other"] += _amount(row)

    categories = [
        {
            "name": name,
            "amount": round(amount, 2),
            "prior": round(prior_by_category.get(name, 0.0), 2),
            "delta": round(amount - prior_by_category.get(name, 0.0), 2),
            "share": round(100 * amount / total, 1) if total else 0.0,
        }
        for name, amount in sorted(by_category.items(), key=lambda kv: kv[1], reverse=True)
    ]

    daily: dict[str, float] = defaultdict(float)
    for row, when in dated:
        if when and _month_key(when) == month:
            daily[when.isoformat()] += _amount(row)

    year, mon = int(month[:4]), int(month[5:7])
    days_in_month = monthrange(year, mon)[1]
    is_current = _month_key(today) == month
    elapsed = today.day if is_current else days_in_month

    return {
        "month": month,
        "total": round(total, 2),
        "prior_total": round(prior_total, 2),
        "delta": round(total - prior_total, 2),
        "delta_pct": round(100 * (total - prior_total) / prior_total, 1) if prior_total else None,
        "receipts": len(current),
        "tax_paid": round(sum(_tax(r) for r in current), 2),
        "largest": max(
            (
                {"vendor": r.get("vendor"), "amount": round(_amount(r), 2), "date": r.get("date")}
                for r in current
            ),
            key=lambda item: item["amount"],
            default=None,
        ),
        "categories": categories,
        "movers": sorted(categories, key=lambda c: abs(c["delta"]), reverse=True)[:3],
        "daily": [{"date": day, "amount": round(value, 2)} for day, value in sorted(daily.items())],
        "per_day": round(total / elapsed, 2) if elapsed else 0.0,
        # Only projected while the month is still running; a finished month
        # is a fact, not a forecast.
        "projected": round(total / elapsed * days_in_month, 2) if is_current and elapsed else None,
    }


def tax_summary(rows: list[dict[str, Any]], year: Optional[int] = None) -> dict[str, Any]:
    """Sales tax paid and a default business apportionment.

    The apportionment is a mapping you edit, not a determination — see
    `accounts.py`.
    """
    scoped = []
    for row in rows:
        when = _parse(row.get("date"))
        if when and (year is None or when.year == year):
            scoped.append((row, when))

    by_month: dict[str, float] = defaultdict(float)
    by_category: dict[str, dict[str, float]] = defaultdict(lambda: {"gross": 0.0, "tax": 0.0, "business": 0.0})
    total_tax = 0.0
    total_gross = 0.0
    business_total = 0.0

    for row, when in scoped:
        gross, tax = _amount(row), _tax(row)
        category = row.get("category") or "Other"
        account = account_for(category)
        business = (gross - tax) * account.business_share

        by_month[_month_key(when)] += tax
        bucket = by_category[category]
        bucket["gross"] += gross
        bucket["tax"] += tax
        bucket["business"] += business
        total_tax += tax
        total_gross += gross
        business_total += business

    return {
        "year": year,
        "receipts": len(scoped),
        "gross": round(total_gross, 2),
        "sales_tax_paid": round(total_tax, 2),
        "effective_tax_rate": round(100 * total_tax / (total_gross - total_tax), 2) if total_gross > total_tax else 0.0,
        "business_apportioned": round(business_total, 2),
        "by_month": [{"month": m, "tax": round(v, 2)} for m, v in sorted(by_month.items())],
        "by_category": [
            {
                "category": name,
                "account": account_for(name).code,
                "account_name": account_for(name).name,
                "business_share": account_for(name).business_share,
                "gross": round(values["gross"], 2),
                "tax": round(values["tax"], 2),
                "business_apportioned": round(values["business"], 2),
            }
            for name, values in sorted(by_category.items(), key=lambda kv: kv[1]["gross"], reverse=True)
        ],
        "disclaimer": "Default apportionment from the editable category mapping. Not tax advice.",
    }


def vendor_concentration(rows: list[dict[str, Any]], top: int = 5) -> dict[str, Any]:
    """How much of the spend sits with a handful of vendors — the number
    procurement asks for, and the one that tells a household where the money
    really goes."""
    by_vendor: dict[str, float] = defaultdict(float)
    for row in rows:
        by_vendor[row.get("vendor") or "Unknown"] += _amount(row)
    total = sum(by_vendor.values())
    ranked = sorted(by_vendor.items(), key=lambda kv: kv[1], reverse=True)
    head = ranked[:top]
    return {
        "total": round(total, 2),
        "vendors": len(ranked),
        "top_share_pct": round(100 * sum(v for _, v in head) / total, 1) if total else 0.0,
        "top": [{"vendor": name, "amount": round(value, 2),
                 "share_pct": round(100 * value / total, 1) if total else 0.0}
                for name, value in head],
    }

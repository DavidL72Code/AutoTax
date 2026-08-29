"""Recurring-charge detection.

A subscription is not a category, it is a *pattern*: the same merchant, at a
steady interval, for a steady amount. Detecting it from the ledger rather than
asking the user to tag things is what turns a pile of receipts into something
that can answer "what am I actually committed to each year?", and, on the
business side, "which vendors are we paying on an evergreen contract?"
"""
from __future__ import annotations

import statistics
from collections import defaultdict
from datetime import date, timedelta
from typing import Any, Optional

# (label, low, high) in days. Windows are generous because billing dates drift
# with month length, weekends and card retries.
CADENCES = (
    ("weekly", 6, 8),
    ("biweekly", 12, 16),
    ("monthly", 26, 35),
    ("bimonthly", 55, 68),
    ("quarterly", 84, 96),
    ("semiannual", 175, 190),
    ("annual", 350, 380),
)
PERIODS_PER_YEAR = {
    "weekly": 52, "biweekly": 26, "monthly": 12, "bimonthly": 6,
    "quarterly": 4, "semiannual": 2, "annual": 1,
}
PRICE_CHANGE_THRESHOLD = 0.05


def _parse(value: Any) -> Optional[date]:
    try:
        return date.fromisoformat(str(value)[:10])
    except (TypeError, ValueError):
        return None


def _cadence_for(days: float) -> Optional[str]:
    for label, low, high in CADENCES:
        if low <= days <= high:
            return label
    return None


def _stable(values: list[float], tolerance: float) -> bool:
    """True when the spread of `values` is small relative to their middle."""
    if len(values) < 2:
        return True
    middle = statistics.median(values)
    if middle == 0:
        return False
    spread = max(abs(v - middle) for v in values)
    return spread / middle <= tolerance


def detect(rows: list[dict[str, Any]], today: Optional[date] = None) -> list[dict[str, Any]]:
    today = today or date.today()
    by_vendor: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        vendor = (row.get("vendor") or "").strip()
        amount = row.get("amount")
        charged = _parse(row.get("date"))
        if vendor and charged and amount:
            by_vendor[vendor].append({"date": charged, "amount": float(amount), "id": row.get("id")})

    found = []
    for vendor, charges in by_vendor.items():
        if len(charges) < 2:
            continue
        charges.sort(key=lambda c: c["date"])
        gaps = [
            (b["date"] - a["date"]).days
            for a, b in zip(charges, charges[1:])
            if (b["date"] - a["date"]).days > 0
        ]
        if not gaps:
            continue

        median_gap = statistics.median(gaps)
        cadence = _cadence_for(median_gap)
        # Two charges is enough only if the interval lands squarely on a known
        # cadence; three or more can carry a little jitter.
        if not cadence or not _stable([float(g) for g in gaps], 0.3 if len(gaps) > 1 else 0.12):
            continue

        amounts = [c["amount"] for c in charges]
        if not _stable(amounts, 0.25):
            continue

        typical = round(statistics.median(amounts), 2)
        latest = charges[-1]
        baseline = round(statistics.median(amounts[:-1]), 2) if len(amounts) > 2 else amounts[0]
        change = (latest["amount"] - baseline) / baseline if baseline else 0.0
        next_expected = latest["date"] + timedelta(days=round(median_gap))
        periods = PERIODS_PER_YEAR.get(cadence, 365 / max(median_gap, 1))

        found.append({
            "vendor": vendor,
            "cadence": cadence,
            "interval_days": round(median_gap),
            "charges": len(charges),
            "typical_amount": typical,
            "baseline_amount": round(baseline, 2),
            "latest_amount": round(latest["amount"], 2),
            "periods_per_year": round(periods, 2),
            "annualised": round(typical * periods, 2),
            "first_charged": charges[0]["date"].isoformat(),
            "last_charged": latest["date"].isoformat(),
            "next_expected": next_expected.isoformat(),
            "days_overdue": max((today - next_expected).days, 0),
            "price_change_pct": round(change * 100, 1) if abs(change) >= PRICE_CHANGE_THRESHOLD else 0.0,
            "category": latest.get("category") or next((c.get("category") for c in charges if c.get("category")), None),
        })

    return sorted(found, key=lambda item: item["annualised"], reverse=True)


def summary(subscriptions: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "count": len(subscriptions),
        "annual_commitment": round(sum(s["annualised"] for s in subscriptions), 2),
        "monthly_equivalent": round(sum(s["annualised"] for s in subscriptions) / 12, 2),
        "price_increases": [s for s in subscriptions if s["price_change_pct"] > 0],
        "lapsed": [s for s in subscriptions if s["days_overdue"] > s["interval_days"]],
    }

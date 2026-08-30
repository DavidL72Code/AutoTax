"""Default category → chart-of-accounts mapping.

These are starting values, not tax advice. Edit `CATEGORY_ACCOUNTS` (or
override per deployment) so exports land in the accounts your bookkeeper
actually uses; the `business_share` column is a default apportionment, and the
correct figure for any given expense is a question for your accountant.
"""
from __future__ import annotations

from typing import NamedTuple


class Account(NamedTuple):
    code: str
    name: str
    business_share: float


CATEGORY_ACCOUNTS: dict[str, Account] = {
    "Dining": Account("6110", "Meals & Entertainment", 0.5),
    "Entertainment": Account("6700", "Entertainment", 0.0),
    "Groceries": Account("6100", "Provisions", 0.0),
    "Health": Account("6600", "Health & Medical", 0.0),
    "Other": Account("6900", "Unclassified", 0.0),
    "Services": Account("6800", "Professional Services", 1.0),
    "Shopping": Account("6300", "Supplies & Equipment", 1.0),
    "Subscriptions": Account("6400", "Software & Subscriptions", 1.0),
    "Transport": Account("6200", "Travel. Local", 1.0),
    "Travel": Account("6210", "Travel", 1.0),
    "Utilities": Account("6500", "Utilities", 1.0),
}

UNCLASSIFIED = CATEGORY_ACCOUNTS["Other"]

# Where the money came out of, for a double-entry export.
PAYMENT_ACCOUNTS = {
    "visa": ("2100", "Credit Card Payable"),
    "mastercard": ("2100", "Credit Card Payable"),
    "american express": ("2110", "Amex Payable"),
    "discover": ("2100", "Credit Card Payable"),
    "paypal": ("1050", "PayPal Balance"),
    "venmo": ("1055", "Venmo Balance"),
    "cash app": ("1055", "Cash App Balance"),
    "apple pay": ("2100", "Credit Card Payable"),
    "google pay": ("2100", "Credit Card Payable"),
}
DEFAULT_PAYMENT_ACCOUNT = ("2000", "Accounts Payable")


def account_for(category: str | None) -> Account:
    return CATEGORY_ACCOUNTS.get((category or "").strip(), UNCLASSIFIED)


def payment_account_for(method: str | None) -> tuple[str, str]:
    text = (method or "").lower()
    for key, account in PAYMENT_ACCOUNTS.items():
        if key in text:
            return account
    return DEFAULT_PAYMENT_ACCOUNT

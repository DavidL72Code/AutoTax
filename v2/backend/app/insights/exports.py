"""File outputs.

Three shapes for three readers: a plain ledger for a person, a double-entry
journal for accounting software, and an expense claim for whoever signs off.
All three carry the source Gmail message id, so any row can be traced back to
the email it came from.
"""
from __future__ import annotations

import csv
import io
from typing import Any, Iterable

from .accounts import account_for, payment_account_for


def _amount(row: dict[str, Any], key: str = "amount") -> float:
    try:
        return round(float(row.get(key) or 0), 2)
    except (TypeError, ValueError):
        return 0.0


_FORMULA_TRIGGERS = ("=", "+", "-", "@", "\t", "\r")


def _safe_cell(value: Any) -> Any:
    """Neutralise spreadsheet formulas.

    Vendor names come out of email, which anyone can send. Excel and Sheets
    treat a leading =, +, - or @ as a formula, so a merchant called
    `=cmd|' /C calc'!A1` would execute on open. Numbers stay numbers; text that
    starts with a trigger gets a leading apostrophe, which spreadsheets strip
    on display.
    """
    if isinstance(value, (int, float)) or value is None:
        return value
    text = str(value)
    return f"'{text}" if text[:1] in _FORMULA_TRIGGERS else text


def _write(header: list[str], rows: Iterable[list[Any]]) -> str:
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(header)
    writer.writerows([_safe_cell(cell) for cell in row] for row in rows)
    return buffer.getvalue()


def ledger_csv(records: list[dict[str, Any]]) -> str:
    return _write(
        ["date", "vendor", "category", "amount", "tax", "net", "payment_method",
         "order_number", "status", "confidence", "source_email_id"],
        (
            [
                row.get("date"), row.get("vendor"), row.get("category"),
                _amount(row), _amount(row, "tax"),
                round(_amount(row) - _amount(row, "tax"), 2),
                row.get("payment_method"), row.get("order_number"),
                row.get("status"), row.get("confidence"), row.get("email_id"),
            ]
            for row in records
        ),
    )


def journal_csv(records: list[dict[str, Any]]) -> str:
    """Two lines per receipt: expense debited, payment source credited.

    Tax is split onto its own debit line where present, because recoverable
    tax has to be separable to be recoverable.
    """
    lines: list[list[Any]] = []
    for row in records:
        gross, tax = _amount(row), _amount(row, "tax")
        net = round(gross - tax, 2)
        account = account_for(row.get("category"))
        pay_code, pay_name = payment_account_for(row.get("payment_method"))
        memo = f"{row.get('vendor') or 'Unknown'} {row.get('order_number') or ''}".strip()
        source = row.get("email_id") or ""

        lines.append([row.get("date"), memo, account.code, account.name, net, "", row.get("currency", "USD"), source])
        if tax:
            lines.append([row.get("date"), f"{memo}, tax", "1300", "Tax Receivable", tax, "", row.get("currency", "USD"), source])
        lines.append([row.get("date"), memo, pay_code, pay_name, "", gross, row.get("currency", "USD"), source])

    return _write(
        ["date", "memo", "account_code", "account_name", "debit", "credit", "currency", "source_email_id"],
        lines,
    )


def expense_report_csv(records: list[dict[str, Any]]) -> str:
    rows = []
    for row in records:
        gross, tax = _amount(row), _amount(row, "tax")
        account = account_for(row.get("category"))
        claimable = round((gross - tax) * account.business_share, 2)
        rows.append([
            row.get("date"), row.get("vendor"), row.get("category"),
            account.code, account.name, gross, tax, round(gross - tax, 2),
            account.business_share, claimable, row.get("payment_method"), row.get("email_id"),
        ])
    return _write(
        ["date", "vendor", "category", "account_code", "account_name", "gross", "tax",
         "net", "business_share", "claimable", "paid_with", "source_email_id"],
        rows,
    )


FORMATS = {"ledger": ledger_csv, "journal": journal_csv, "expenses": expense_report_csv}

from .database import SessionLocal
from .models import Transaction
from datetime import datetime
from dateutil import parser as date_parser
from .firestore_store import (
    clear_transactions as clear_firestore_transactions,
    deduplicate_order_transactions as deduplicate_firestore_transactions,
    delete_transaction as delete_firestore_transaction,
    delete_zero_amount_transactions as delete_zero_firestore_transactions,
    firestore_enabled,
    get_all_transactions as get_all_firestore_transactions,
    get_existing_email_ids as get_existing_firestore_email_ids,
    get_transaction_by_id as get_firestore_transaction_by_id,
    save_transaction_record,
    update_transaction as update_firestore_transaction,
)

def _normalize_amount(value):
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        cleaned = value.replace('$', '').replace(',', '').strip()
        if not cleaned:
            return None
        try:
            return float(cleaned)
        except ValueError:
            return None
    return None

def _normalize_date(value):
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        try:
            return date_parser.parse(value)
        except Exception:
            return None
    return None
def log_transaction(parsed_data:dict, user_id: str | int | None = None):
    """Save transaction to DB. Skips if amount is 0 (no expenditure)."""
    if not parsed_data:
        return None

    email_id = parsed_data.get('email_id')
    user_id = user_id if user_id is not None else parsed_data.get('user_id')
    if not email_id:
        print("⚠️  Missing email_id; skipping save")
        return None
    if user_id is None:
        print("⚠️  Missing user_id; skipping save")
        return None

    amount = _normalize_amount(parsed_data.get('amount'))
    if amount is None or amount == 0:
        print(f"Skipping zero-total receipt: {parsed_data.get('email_id', '?')}")
        return None
    
    tax = _normalize_amount(parsed_data.get('tax'))
    date_val = _normalize_date(parsed_data.get('date')) or datetime.utcnow()
    if firestore_enabled():
        parsed_copy = dict(parsed_data)
        parsed_copy["amount"] = amount
        parsed_copy["tax"] = tax
        parsed_copy["date"] = date_val
        saved = save_transaction_record(parsed_copy, user_id=user_id)
        if saved is not None:
            print(f"Saved: {saved.vendor} ${saved.amount}")
        return saved

    db=SessionLocal()
    try:
        # Deduplicate by email_id first
        existing=db.query(Transaction).filter(
            Transaction.email_id==parsed_data.get('email_id'),
            Transaction.user_id==user_id
        ).first()
        if existing:
            print(f"Transaction already exists (email_id): {parsed_data.get('email_id')}")
            return existing

        # Deduplicate by order number — different emails about the same order.
        # Do NOT filter by vendor: slight name differences between emails would
        # let duplicates slip through (e.g. "Amazon" vs "Amazon.com").
        order_number = parsed_data.get('order_number')
        if order_number:
            existing_order = db.query(Transaction).filter(
                Transaction.order_number == order_number,
                Transaction.user_id == user_id,
            ).first()
            if existing_order:
                print(f"Duplicate order number {order_number} — skipping")
                return existing_order

        transaction=Transaction(
            user_id=user_id,
            email_id=parsed_data.get('email_id'),
            vendor=(parsed_data.get('vendor') or "Unknown"),
            amount=amount,
            tax=tax,
            date=date_val,
            category=parsed_data.get('category'),
            payment_method=parsed_data.get('payment_method'),
            items=parsed_data.get('items'),
            email_body=parsed_data.get('email_body') or parsed_data.get('email body'),
            order_number=order_number,
            )

        db.add(transaction)
        db.commit()
        db.refresh(transaction)
        print(f"Saved: {transaction.vendor} ${transaction.amount}")
        return transaction

    except Exception as e:
        print(f"❌ Failed to save transaction: {e}")
        db.rollback()
        return None
    finally:
        db.close()

def get_all_transactions(user_id: str | int | None = None):
    """Get all transactions from database"""
    if firestore_enabled():
        return get_all_firestore_transactions(user_id=user_id)
    db = SessionLocal()
    try:
        query = db.query(Transaction)
        if user_id is not None:
            query = query.filter(Transaction.user_id == user_id)
        transactions = query.all()
        return transactions
    finally:
        db.close()


def get_existing_email_ids(user_id: str | int | None = None):
    """Return set of Gmail message ids we already have as transactions. Use before fetch/parse to skip duplicates."""
    if firestore_enabled():
        return get_existing_firestore_email_ids(user_id=user_id)
    db = SessionLocal()
    try:
        query = db.query(Transaction.email_id)
        if user_id is not None:
            query = query.filter(Transaction.user_id == user_id)
        rows = query.all()
        return set(r[0] for r in rows if r[0])
    finally:
        db.close()


def delete_zero_amount_transactions(user_id: str | int | None = None):
    """Remove all transactions with amount 0 or None from the database. Returns count deleted."""
    if firestore_enabled():
        return delete_zero_firestore_transactions(user_id=user_id)
    db = SessionLocal()
    try:
        query = db.query(Transaction).filter(
            (Transaction.amount.is_(None)) | (Transaction.amount == 0)
        )
        if user_id is not None:
            query = query.filter(Transaction.user_id == user_id)
        to_delete = query.all()
        count = len(to_delete)
        for t in to_delete:
            db.delete(t)
        db.commit()
        return count
    except Exception as e:
        db.rollback()
        raise e
    finally:
        db.close()


def get_transaction_by_id(transaction_id: str | int):
    """Get a specific transaction by ID"""
    if firestore_enabled():
        return get_firestore_transaction_by_id(str(transaction_id))
    db = SessionLocal()
    try:
        transaction = db.query(Transaction).filter(
            Transaction.id == transaction_id
        ).first()
        return transaction
    finally:
        db.close()


def deduplicate_transactions_for_user(user_id: str | int | None) -> int:
    if firestore_enabled():
        return deduplicate_firestore_transactions(user_id=user_id)
    return 0  # SQLite path uses DB-level constraints; no cleanup needed


def clear_transactions_for_user(user_id: str | int | None):
    if firestore_enabled():
        return clear_firestore_transactions(user_id=user_id)
    db = SessionLocal()
    try:
        return db.query(Transaction).filter(Transaction.user_id == user_id).delete()
    finally:
        db.commit()
        db.close()


def update_transaction_for_user(transaction_id: str | int, payload: dict, user_id: str | int | None):
    if firestore_enabled():
        return update_firestore_transaction(str(transaction_id), user_id=user_id, payload=payload)
    db = SessionLocal()
    try:
        transaction = db.query(Transaction).filter(
            Transaction.id == transaction_id,
            Transaction.user_id == user_id,
        ).first()
        if not transaction:
            return None
        if "vendor" in payload:
            vendor = (payload.get("vendor") or "").strip()
            if vendor:
                transaction.vendor = vendor
        if "amount" in payload:
            transaction.amount = float(str(payload["amount"]).replace("$", "").replace(",", "").strip())
        if "tax" in payload:
            raw_tax = str(payload["tax"]).replace("$", "").replace(",", "").strip()
            transaction.tax = float(raw_tax) if raw_tax else None
        if "date" in payload and payload.get("date"):
            transaction.date = date_parser.parse(str(payload["date"]))
        if "category" in payload:
            raw_cat = (payload.get("category") or "").strip()
            transaction.category = raw_cat or None
        db.commit()
        db.refresh(transaction)
        return transaction
    finally:
        db.close()


def delete_transaction_for_user(transaction_id: str | int, user_id: str | int | None):
    if firestore_enabled():
        return delete_firestore_transaction(str(transaction_id), user_id=user_id)
    db = SessionLocal()
    try:
        transaction = db.query(Transaction).filter(
            Transaction.id == transaction_id,
            Transaction.user_id == user_id,
        ).first()
        if not transaction:
            return False
        db.delete(transaction)
        db.commit()
        return True
    finally:
        db.close()

from database import SessionLocal
from models import Transaction
from datetime import datetime
from dateutil import parser as date_parser

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
def log_transaction(parsed_data:dict):
    """Save transaction to DB. Skips if amount is 0 (no expenditure)."""
    if not parsed_data:
        return None

    email_id = parsed_data.get('email_id')
    if not email_id:
        print("⚠️  Missing email_id; skipping save")
        return None

    amount = _normalize_amount(parsed_data.get('amount'))
    if amount is None or amount == 0:
        print(f"Skipping zero-total receipt: {parsed_data.get('email_id', '?')}")
        return None
    
    tax = _normalize_amount(parsed_data.get('tax'))
    date_val = _normalize_date(parsed_data.get('date')) or datetime.utcnow()
    db=SessionLocal()
    try:
        existing=db.query(Transaction).filter(Transaction.email_id==parsed_data.get('email_id')).first()
        if existing:
            print(f"Transaction already exists:{parsed_data.get('email_id')}")
            return existing
    
        transaction=Transaction(
            email_id=parsed_data.get('email_id'),
            vendor=(parsed_data.get('vendor') or "Unknown"),
            amount=amount,
            tax=tax,
            date=date_val,
            email_body=parsed_data.get('email_body') or parsed_data.get('email body')
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

def get_all_transactions():
    """Get all transactions from database"""
    db = SessionLocal()
    try:
        transactions = db.query(Transaction).all()
        return transactions
    finally:
        db.close()


def get_existing_email_ids():
    """Return set of Gmail message ids we already have as transactions. Use before fetch/parse to skip duplicates."""
    db = SessionLocal()
    try:
        rows = db.query(Transaction.email_id).all()
        return set(r[0] for r in rows if r[0])
    finally:
        db.close()


def delete_zero_amount_transactions():
    """Remove all transactions with amount 0 or None from the database. Returns count deleted."""
    db = SessionLocal()
    try:
        to_delete = db.query(Transaction).filter(
            (Transaction.amount.is_(None)) | (Transaction.amount == 0)
        ).all()
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


def get_transaction_by_id(transaction_id: int):
    """Get a specific transaction by ID"""
    db = SessionLocal()
    try:
        transaction = db.query(Transaction).filter(
            Transaction.id == transaction_id
        ).first()
        return transaction
    finally:
        db.close()

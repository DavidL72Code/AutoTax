from database import SessionLocal
from models import Transaction

try:
    existing=db.query(Transaction).filter(Transaction.email_id==parsed_data['email_id']).first()
    if existing:
        print(f"Transaction already exists:{parsed_data['email_id']}")
        return existing
    
    transaction=Transaction(
        email_id=parsed_data.get('email_id'),
        vendor=parsed_data.get('vendor'),
        amount=parsed_data.get('amount'),
        tax=parsed_data.get('tax'),
        date=parsed_data.get('date'),
        email_body=parsed_data.get('email_body')
    )

    db.add(transaction)
    db.commit()
    db.refresh(transaction)
    print(f"Saved: {transaction.vendor} ${transaction.amount}")
        return transaction

except Exception as e:
    db.rollback()
    return None
finally:
    db.close()
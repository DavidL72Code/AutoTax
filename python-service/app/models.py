from sqlalchemy import Column, Integer, String, Float, DateTime,Text
from sqlalchemy.ext.declarative import declarative_base
from datetime import datetime


Base=declarative_base()
class Transaction(Base):
    __tablename__="transactions"
    id=Column(Integer,primary_key=True,index=True)
    email_id=Column(String(255),unique=True,nullable=False,index=True)
    vendor=Column(String(255),nullable=False,index=True)
    amount=Column(Float,nullable=False)
    tax=Column(Float,nullable=True)
    date=Column(DateTime,nullable=False,index=True)
    category=Column(String(100),nullable=True,index=True)
    payment_method=Column(String(100),nullable=True)
    items=Column(Text,nullable=True)#using text cause json string can stroe entire item list name,price
    email_body=Column(Text,nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

def __repr__(self):
    return f"<Transaction {self.vendor} ${self.amount}>"

class Vendor(Base):
    __tablename__ = "vendors"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), unique=True, nullable=False)
    normalized_name = Column(String(255))
    parser_type = Column(String(50))  # 'amazon', 'paypal', 'generic', 'ai'
    created_at = Column(DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f"<Vendor {self.name}>"  
# database.py
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from .config import settings
from .models import Base, Vendor, User, AuthToken, Transaction, GoogleCredential

# Create engine
engine = create_engine(settings.database_url)

def _ensure_transactions_schema():
    """Add user_id column and composite uniqueness for transactions when missing (SQLite)."""
    if engine.dialect.name != "sqlite":
        Base.metadata.create_all(bind=engine)
        return

    with engine.begin() as conn:
        cols = [row[1] for row in conn.execute(text("PRAGMA table_info(transactions)")).fetchall()] if conn.execute(text("SELECT name FROM sqlite_master WHERE type='table' AND name='transactions'")).fetchone() else []
        if not cols:
            Base.metadata.create_all(bind=engine)
            return

        needs_user_id = "user_id" not in cols
        if not needs_user_id:
            return

        # Rebuild transactions table with user_id column and composite unique index.
        conn.execute(text("""
            CREATE TABLE transactions_new (
                id INTEGER PRIMARY KEY,
                user_id INTEGER,
                email_id VARCHAR(255) NOT NULL,
                vendor VARCHAR(255) NOT NULL,
                amount FLOAT NOT NULL,
                tax FLOAT,
                date DATETIME NOT NULL,
                category VARCHAR(100),
                payment_method VARCHAR(100),
                items TEXT,
                email_body TEXT,
                created_at DATETIME,
                updated_at DATETIME
            )
        """))
        conn.execute(text("""
            INSERT INTO transactions_new (
                id, email_id, vendor, amount, tax, date, category, payment_method,
                items, email_body, created_at, updated_at, user_id
            )
            SELECT
                id, email_id, vendor, amount, tax, date, category, payment_method,
                items, email_body, created_at, updated_at, NULL
            FROM transactions
        """))
        conn.execute(text("DROP TABLE transactions"))
        conn.execute(text("ALTER TABLE transactions_new RENAME TO transactions"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_transactions_email_id ON transactions (email_id)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_transactions_vendor ON transactions (vendor)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_transactions_date ON transactions (date)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_transactions_user_id ON transactions (user_id)"))
        conn.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS uq_user_email ON transactions (user_id, email_id)"))

_ensure_transactions_schema()
Base.metadata.create_all(bind=engine)
# Create session factory
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Function to get DB session
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

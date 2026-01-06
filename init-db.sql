-- Create extensions if needed
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Create transactions table
CREATE TABLE IF NOT EXISTS transactions (
    id SERIAL PRIMARY KEY,
    email_id VARCHAR(255) UNIQUE NOT NULL,
    vendor VARCHAR(255) NOT NULL,
    amount DECIMAL(10, 2) NOT NULL,
    tax DECIMAL(10, 2),
    date TIMESTAMP NOT NULL,
    category VARCHAR(100),
    payment_method VARCHAR(100),
    items TEXT,
    raw_email TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Create vendors table (optional)
CREATE TABLE IF NOT EXISTS vendors (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255) UNIQUE NOT NULL,
    normalized_name VARCHAR(255),
    parser_type VARCHAR(50),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Create indexes for performance
CREATE INDEX IF NOT EXISTS idx_transactions_email_id ON transactions(email_id);
CREATE INDEX IF NOT EXISTS idx_transactions_vendor ON transactions(vendor);
CREATE INDEX IF NOT EXISTS idx_transactions_date ON transactions(date);
CREATE INDEX IF NOT EXISTS idx_transactions_category ON transactions(category);

-- Insert sample vendors (optional)
INSERT INTO vendors (name, normalized_name, parser_type) VALUES
    ('Amazon', 'Amazon', 'amazon'),
    ('PayPal', 'PayPal', 'paypal'),
    ('Uber', 'Uber', 'generic'),
    ('Starbucks', 'Starbucks', 'generic')
ON CONFLICT (name) DO NOTHING;

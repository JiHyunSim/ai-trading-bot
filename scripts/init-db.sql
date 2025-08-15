-- Database initialization script for AI Trading Bot
-- Creates tables for storing candlestick data with monthly partitioning

-- Create schema if not exists
CREATE SCHEMA IF NOT EXISTS trading;

-- Set search path
SET search_path TO trading, public;

-- Create candlestick data table
CREATE TABLE IF NOT EXISTS candlesticks (
    id BIGSERIAL NOT NULL,
    symbol VARCHAR(20) NOT NULL,
    timeframe VARCHAR(10) NOT NULL,
    timestamp_ms BIGINT NOT NULL,
    open_price DECIMAL(20, 8) NOT NULL,
    high_price DECIMAL(20, 8) NOT NULL,
    low_price DECIMAL(20, 8) NOT NULL,
    close_price DECIMAL(20, 8) NOT NULL,
    volume DECIMAL(20, 8) NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    PRIMARY KEY (id, timestamp_ms)
) PARTITION BY RANGE (timestamp_ms);

-- Create indexes on main table
CREATE INDEX IF NOT EXISTS idx_candlesticks_symbol_timeframe 
    ON candlesticks (symbol, timeframe);
CREATE INDEX IF NOT EXISTS idx_candlesticks_timestamp 
    ON candlesticks (timestamp_ms);

-- Create function to create monthly partitions
CREATE OR REPLACE FUNCTION create_monthly_partition(
    base_table_name TEXT,
    year_month TEXT
) RETURNS VOID AS $$
DECLARE
    partition_name TEXT;
    start_date BIGINT;
    end_date BIGINT;
BEGIN
    partition_name := base_table_name || '_' || year_month;
    
    -- Convert YYYY_MM to millisecond timestamps
    start_date := EXTRACT(EPOCH FROM (year_month || '_01')::DATE) * 1000;
    end_date := EXTRACT(EPOCH FROM ((year_month || '_01')::DATE + INTERVAL '1 month')) * 1000;
    
    -- Create partition if it doesn't exist
    EXECUTE format('
        CREATE TABLE IF NOT EXISTS %I 
        PARTITION OF %I 
        FOR VALUES FROM (%L) TO (%L)',
        partition_name, base_table_name, start_date, end_date
    );
    
    -- Create indexes on partition
    EXECUTE format('
        CREATE INDEX IF NOT EXISTS %I ON %I (symbol, timeframe)',
        'idx_' || partition_name || '_symbol_timeframe', partition_name
    );
    
    EXECUTE format('
        CREATE INDEX IF NOT EXISTS %I ON %I (timestamp_ms)',
        'idx_' || partition_name || '_timestamp', partition_name
    );
    
    RAISE NOTICE 'Created partition % for range [%, %)', partition_name, start_date, end_date;
END;
$$ LANGUAGE plpgsql;

-- Create partitions for current and next 2 months
SELECT create_monthly_partition('candlesticks', TO_CHAR(NOW(), 'YYYY_MM'));
SELECT create_monthly_partition('candlesticks', TO_CHAR(NOW() + INTERVAL '1 month', 'YYYY_MM'));
SELECT create_monthly_partition('candlesticks', TO_CHAR(NOW() + INTERVAL '2 month', 'YYYY_MM'));

-- Create batch processing status table
CREATE TABLE IF NOT EXISTS batch_status (
    id BIGSERIAL PRIMARY KEY,
    batch_id VARCHAR(50) UNIQUE NOT NULL,
    symbol VARCHAR(20) NOT NULL,
    timeframe VARCHAR(10) NOT NULL,
    records_count INTEGER DEFAULT 0,
    status VARCHAR(20) DEFAULT 'pending',
    error_message TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    processed_at TIMESTAMPTZ
);

-- Create index for batch status
CREATE INDEX IF NOT EXISTS idx_batch_status_symbol_timeframe 
    ON batch_status (symbol, timeframe);
CREATE INDEX IF NOT EXISTS idx_batch_status_created_at 
    ON batch_status (created_at);

-- Create dead letter queue table
CREATE TABLE IF NOT EXISTS dead_letter_queue (
    id BIGSERIAL PRIMARY KEY,
    original_data JSONB NOT NULL,
    error_message TEXT NOT NULL,
    error_count INTEGER DEFAULT 1,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    last_retry_at TIMESTAMPTZ DEFAULT NOW()
);

-- Create index for DLQ
CREATE INDEX IF NOT EXISTS idx_dlq_created_at ON dead_letter_queue (created_at);

-- Grant permissions
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA trading TO trading_bot;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA trading TO trading_bot;

-- Create read-only user for monitoring
DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = 'trading_bot_readonly') THEN
        CREATE ROLE trading_bot_readonly LOGIN PASSWORD 'readonly_password';
    END IF;
END
$$;

GRANT CONNECT ON DATABASE trading_bot TO trading_bot_readonly;
GRANT USAGE ON SCHEMA trading TO trading_bot_readonly;
GRANT SELECT ON ALL TABLES IN SCHEMA trading TO trading_bot_readonly;

-- Display created objects
\dt trading.*;
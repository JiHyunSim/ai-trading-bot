# PostgreSQL 데이터베이스 스키마 및 설정 가이드

## 📋 개요

이 문서는 OKX 실시간 캔들 데이터 수집 시스템의 PostgreSQL 데이터베이스 스키마, 최적화 설정, 운영 방법을 상세히 설명합니다. Claude Code를 통해 단계별로 구현할 수 있도록 완전한 SQL 스크립트와 관리 방법을 제공합니다.

## 🏗️ 데이터베이스 아키텍처

### 설계 원칙
- **확장성**: 월별 파티션으로 수평 확장
- **성능**: 인덱스 최적화 및 쿼리 성능 향상
- **무결성**: 제약조건으로 데이터 품질 보장
- **관리성**: 자동화된 파티션 관리
- **백업**: 점진적 백업 및 아카이빙

### 테이블 구조 개요
```
symbols (심볼 정보)
├── id (PK)
├── symbol (UNIQUE)
└── metadata

timeframes (시간프레임)
├── id (PK) 
├── name (UNIQUE)
└── seconds

candlestick_data (캔들 데이터 - 파티션)
├── id (PK)
├── symbol_id (FK → symbols)
├── timeframe_id (FK → timeframes)  
├── timestamp (파티션 키)
└── OHLCV 데이터

system_metrics (시스템 메트릭)
data_quality_log (품질 로그)
daily_statistics (일간 통계)
```

## 📊 전체 스키마 정의

### 1. 데이터베이스 및 확장 기능 설정

```sql
-- 데이터베이스 생성
CREATE DATABASE okx_trading_data
    WITH 
    ENCODING = 'UTF8'
    LC_COLLATE = 'en_US.UTF-8'
    LC_CTYPE = 'en_US.UTF-8'
    TEMPLATE = template0;

-- 데이터베이스 연결
\c okx_trading_data;

-- 필수 확장 기능 활성화
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";           -- UUID 생성
CREATE EXTENSION IF NOT EXISTS "pg_stat_statements";  -- 쿼리 통계
CREATE EXTENSION IF NOT EXISTS "pg_trgm";            -- 텍스트 검색
CREATE EXTENSION IF NOT EXISTS "btree_gist";         -- GiST 인덱스
CREATE EXTENSION IF NOT EXISTS "pg_cron";            -- 크론 작업

-- 스키마 생성
CREATE SCHEMA IF NOT EXISTS trading;
CREATE SCHEMA IF NOT EXISTS monitoring;
CREATE SCHEMA IF NOT EXISTS archive;

-- 기본 스키마 설정
SET search_path TO trading, public;
```

### 2. 기본 참조 테이블

```sql
-- 거래소 정보 테이블
CREATE TABLE exchanges (
    id SERIAL PRIMARY KEY,
    name VARCHAR(50) UNIQUE NOT NULL,
    display_name VARCHAR(100) NOT NULL,
    api_endpoint VARCHAR(255),
    websocket_endpoint VARCHAR(255),
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- 심볼 정보 테이블
CREATE TABLE symbols (
    id SERIAL PRIMARY KEY,
    exchange_id INTEGER NOT NULL REFERENCES exchanges(id),
    symbol VARCHAR(20) NOT NULL,
    base_currency VARCHAR(10) NOT NULL,
    quote_currency VARCHAR(10) NOT NULL,
    instrument_type VARCHAR(20) NOT NULL CHECK (instrument_type IN ('SPOT', 'FUTURES', 'SWAP', 'OPTION')),
    status VARCHAR(10) DEFAULT 'ACTIVE' CHECK (status IN ('ACTIVE', 'INACTIVE', 'DELISTED')),
    
    -- 거래 정보
    tick_size DECIMAL(20,10),
    lot_size DECIMAL(20,10),
    min_size DECIMAL(20,10),
    max_size DECIMAL(20,10),
    contract_value DECIMAL(20,10),
    
    -- 메타데이터
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    
    -- 유니크 제약조건
    UNIQUE(exchange_id, symbol)
);

-- 시간프레임 정의 테이블
CREATE TABLE timeframes (
    id SERIAL PRIMARY KEY,
    name VARCHAR(10) UNIQUE NOT NULL,
    display_name VARCHAR(20) NOT NULL,
    seconds INTEGER NOT NULL,
    sort_order INTEGER DEFAULT 0,
    is_active BOOLEAN DEFAULT true,
    description TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);
```

### 3. 캔들스틱 데이터 메인 테이블 (파티션)

```sql
-- 캔들스틱 데이터 메인 테이블
CREATE TABLE candlestick_data (
    id UUID DEFAULT gen_random_uuid(),
    symbol_id INTEGER NOT NULL REFERENCES symbols(id),
    timeframe_id INTEGER NOT NULL REFERENCES timeframes(id),
    
    -- 시간 정보
    timestamp TIMESTAMP WITH TIME ZONE NOT NULL,
    
    -- OHLCV 데이터
    open_price DECIMAL(20,8) NOT NULL,
    high_price DECIMAL(20,8) NOT NULL,
    low_price DECIMAL(20,8) NOT NULL,
    close_price DECIMAL(20,8) NOT NULL,
    volume DECIMAL(20,8) NOT NULL DEFAULT 0,
    volume_currency DECIMAL(20,8) DEFAULT 0,
    
    -- 메타데이터
    confirm BOOLEAN DEFAULT false,          -- 캔들 확정 여부
    trade_count INTEGER DEFAULT 0,          -- 거래 횟수
    vwap DECIMAL(20,8),                    -- 거래량 가중 평균가
    raw_data JSONB,                        -- 원본 데이터
    
    -- 시스템 정보
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    processed_at TIMESTAMP WITH TIME ZONE,
    
    PRIMARY KEY (id, timestamp)
    
) PARTITION BY RANGE (timestamp);

-- 데이터 품질 제약조건
ALTER TABLE candlestick_data ADD CONSTRAINT chk_ohlc_valid 
    CHECK (
        high_price >= low_price AND 
        high_price >= open_price AND 
        high_price >= close_price AND
        low_price <= open_price AND 
        low_price <= close_price
    );

ALTER TABLE candlestick_data ADD CONSTRAINT chk_positive_values 
    CHECK (
        open_price > 0 AND 
        high_price > 0 AND 
        low_price > 0 AND 
        close_price > 0 AND 
        volume >= 0 AND
        COALESCE(volume_currency, 0) >= 0
    );

ALTER TABLE candlestick_data ADD CONSTRAINT chk_timestamp_reasonable 
    CHECK (
        timestamp >= '2020-01-01'::timestamp AND 
        timestamp <= CURRENT_TIMESTAMP + INTERVAL '1 day'
    );
```

### 4. 인덱스 생성

```sql
-- 기본 테이블 인덱스
CREATE INDEX idx_symbols_exchange_symbol ON symbols(exchange_id, symbol);
CREATE INDEX idx_symbols_status ON symbols(status) WHERE status = 'ACTIVE';
CREATE INDEX idx_symbols_instrument_type ON symbols(instrument_type);
CREATE INDEX idx_symbols_metadata_gin ON symbols USING gin (metadata);

CREATE INDEX idx_timeframes_seconds ON timeframes(seconds);
CREATE INDEX idx_timeframes_active ON timeframes(is_active) WHERE is_active = true;

-- 캔들스틱 데이터 인덱스 (파티션별로 자동 생성됨)
CREATE UNIQUE INDEX idx_candlestick_unique 
    ON candlestick_data (symbol_id, timeframe_id, timestamp);

CREATE INDEX idx_candlestick_symbol_timeframe 
    ON candlestick_data (symbol_id, timeframe_id);

CREATE INDEX idx_candlestick_timestamp_desc 
    ON candlestick_data (timestamp DESC);

CREATE INDEX idx_candlestick_confirm 
    ON candlestick_data (confirm, timestamp DESC) WHERE confirm = true;

CREATE INDEX idx_candlestick_symbol_tf_confirm 
    ON candlestick_data (symbol_id, timeframe_id, confirm, timestamp DESC);

-- JSONB 인덱스
CREATE INDEX idx_candlestick_raw_data_gin 
    ON candlestick_data USING gin (raw_data);

-- 부분 인덱스 (최근 데이터)
CREATE INDEX idx_candlestick_recent 
    ON candlestick_data (symbol_id, timeframe_id, timestamp DESC) 
    WHERE timestamp >= CURRENT_TIMESTAMP - INTERVAL '7 days';
```

### 5. 통계 및 집계 테이블

```sql
-- 일간 통계 테이블
CREATE TABLE daily_statistics (
    id SERIAL PRIMARY KEY,
    symbol_id INTEGER NOT NULL REFERENCES symbols(id),
    timeframe_id INTEGER NOT NULL REFERENCES timeframes(id),
    date DATE NOT NULL,
    
    -- OHLCV 집계
    open_price DECIMAL(20,8),
    high_price DECIMAL(20,8),
    low_price DECIMAL(20,8),
    close_price DECIMAL(20,8),
    volume DECIMAL(20,8),
    volume_currency DECIMAL(20,8),
    
    -- 통계 정보
    trade_count INTEGER DEFAULT 0,
    vwap DECIMAL(20,8),
    price_change DECIMAL(20,8),
    price_change_percent DECIMAL(8,4),
    
    -- 메타데이터
    candle_count INTEGER DEFAULT 0,
    first_timestamp TIMESTAMP WITH TIME ZONE,
    last_timestamp TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    
    UNIQUE(symbol_id, timeframe_id, date)
);

-- 일간 통계 인덱스
CREATE INDEX idx_daily_stats_symbol_date ON daily_statistics(symbol_id, date DESC);
CREATE INDEX idx_daily_stats_timeframe_date ON daily_statistics(timeframe_id, date DESC);
```

### 6. 시스템 모니터링 테이블

```sql
-- 시스템 메트릭 테이블
CREATE TABLE monitoring.system_metrics (
    id SERIAL PRIMARY KEY,
    metric_name VARCHAR(100) NOT NULL,
    metric_type VARCHAR(20) DEFAULT 'gauge' CHECK (metric_type IN ('counter', 'gauge', 'histogram')),
    metric_value DECIMAL(20,4),
    metric_data JSONB DEFAULT '{}',
    labels JSONB DEFAULT '{}',
    timestamp TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    
    -- 파티션 키로도 사용 가능
    INDEX (timestamp)
) PARTITION BY RANGE (timestamp);

-- 시스템 메트릭 인덱스
CREATE INDEX idx_system_metrics_name_timestamp 
    ON monitoring.system_metrics (metric_name, timestamp DESC);
    
CREATE INDEX idx_system_metrics_labels_gin 
    ON monitoring.system_metrics USING gin (labels);

-- 데이터 품질 로그 테이블
CREATE TABLE monitoring.data_quality_log (
    id SERIAL PRIMARY KEY,
    symbol_id INTEGER REFERENCES symbols(id),
    timeframe_id INTEGER REFERENCES timeframes(id),
    
    -- 이슈 정보
    issue_type VARCHAR(50) NOT NULL,
    issue_description TEXT,
    issue_data JSONB DEFAULT '{}',
    severity VARCHAR(10) DEFAULT 'LOW' CHECK (severity IN ('LOW', 'MEDIUM', 'HIGH', 'CRITICAL')),
    
    -- 해결 정보
    resolved BOOLEAN DEFAULT false,
    resolution_notes TEXT,
    resolved_by VARCHAR(100),
    
    -- 시간 정보
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    resolved_at TIMESTAMP WITH TIME ZONE,
    
    CHECK (resolved = false OR resolved_at IS NOT NULL)
);

-- 품질 로그 인덱스
CREATE INDEX idx_quality_log_symbol_timestamp 
    ON monitoring.data_quality_log(symbol_id, created_at DESC);
CREATE INDEX idx_quality_log_unresolved 
    ON monitoring.data_quality_log(resolved, severity, created_at DESC) 
    WHERE resolved = false;
```

## 🗓️ 파티션 관리 시스템

### 파티션 자동 생성 함수

```sql
-- 월별 파티션 생성 함수
CREATE OR REPLACE FUNCTION create_monthly_partition(
    table_name text, 
    start_date date,
    schema_name text DEFAULT 'trading'
)
RETURNS text AS $$
DECLARE
    partition_name text;
    full_table_name text;
    full_partition_name text;
    end_date date;
BEGIN
    -- 파티션 이름 생성
    partition_name := table_name || '_' || to_char(start_date, 'YYYY_MM');
    full_table_name := schema_name || '.' || table_name;
    full_partition_name := schema_name || '.' || partition_name;
    end_date := start_date + interval '1 month';
    
    -- 파티션 테이블 생성
    EXECUTE format('
        CREATE TABLE IF NOT EXISTS %I PARTITION OF %s
        FOR VALUES FROM (%L) TO (%L)',
        full_partition_name, full_table_name, start_date, end_date);
    
    -- 파티션별 인덱스 생성 (candlestick_data용)
    IF table_name = 'candlestick_data' THEN
        -- 유니크 인덱스
        EXECUTE format('
            CREATE UNIQUE INDEX IF NOT EXISTS %I 
            ON %I (symbol_id, timeframe_id, timestamp)',
            partition_name || '_unique_idx', full_partition_name);
            
        -- 성능 인덱스
        EXECUTE format('
            CREATE INDEX IF NOT EXISTS %I 
            ON %I (symbol_id, timeframe_id, timestamp DESC)',
            partition_name || '_query_idx', full_partition_name);
            
        EXECUTE format('
            CREATE INDEX IF NOT EXISTS %I 
            ON %I (timestamp DESC)',
            partition_name || '_timestamp_idx', full_partition_name);
    END IF;
    
    -- 시스템 메트릭용 인덱스
    IF table_name = 'system_metrics' THEN
        EXECUTE format('
            CREATE INDEX IF NOT EXISTS %I 
            ON %I (metric_name, timestamp DESC)',
            partition_name || '_metric_idx', full_partition_name);
    END IF;
    
    RAISE NOTICE 'Created partition: %', full_partition_name;
    RETURN full_partition_name;
END;
$$ LANGUAGE plpgsql;

-- 파티션 유지보수 함수
CREATE OR REPLACE FUNCTION maintain_partitions()
RETURNS void AS $$
DECLARE
    current_month date;
    i integer;
BEGIN
    current_month := date_trunc('month', CURRENT_DATE);
    
    -- 캔들스틱 데이터 파티션 (과거 3개월 ~ 미래 6개월)
    FOR i IN -3..6 LOOP
        PERFORM create_monthly_partition(
            'candlestick_data', 
            current_month + (i || ' months')::interval
        );
    END LOOP;
    
    -- 시스템 메트릭 파티션 (과거 1개월 ~ 미래 2개월)
    FOR i IN -1..2 LOOP
        PERFORM create_monthly_partition(
            'system_metrics', 
            current_month + (i || ' months')::interval,
            'monitoring'
        );
    END LOOP;
    
    RAISE NOTICE 'Partition maintenance completed at %', CURRENT_TIMESTAMP;
END;
$$ LANGUAGE plpgsql;

-- 오래된 파티션 삭제 함수
CREATE OR REPLACE FUNCTION drop_old_partitions(
    table_name text, 
    months_to_keep integer DEFAULT 12,
    schema_name text DEFAULT 'trading'
)
RETURNS integer AS $$
DECLARE
    partition_record record;
    cutoff_date date;
    dropped_count integer := 0;
    full_table_name text;
BEGIN
    cutoff_date := date_trunc('month', CURRENT_DATE - (months_to_keep || ' months')::interval);
    full_table_name := schema_name || '.' || table_name;
    
    -- 삭제 대상 파티션 찾기
    FOR partition_record IN
        SELECT schemaname, tablename 
        FROM pg_tables 
        WHERE schemaname = schema_name
        AND tablename LIKE table_name || '_%'
        AND tablename ~ '[0-9]{4}_[0-9]{2}$'
        AND to_date(
            substring(tablename from '([0-9]{4}_[0-9]{2})$'), 
            'YYYY_MM'
        ) < cutoff_date
    LOOP
        -- 파티션 삭제
        EXECUTE format('DROP TABLE IF EXISTS %I.%I CASCADE', 
            partition_record.schemaname, partition_record.tablename);
        
        dropped_count := dropped_count + 1;
        RAISE NOTICE 'Dropped partition: %.%', 
            partition_record.schemaname, partition_record.tablename;
    END LOOP;
    
    RAISE NOTICE 'Dropped % old partitions for %.%', dropped_count, schema_name, table_name;
    RETURN dropped_count;
END;
$$ LANGUAGE plpgsql;
```

### 자동 파티션 관리 설정

```sql
-- 초기 파티션 생성
SELECT maintain_partitions();

-- 크론 작업으로 자동 파티션 관리 (매월 1일 실행)
SELECT cron.schedule(
    'partition-maintenance',
    '0 0 1 * *',
    'SELECT maintain_partitions();'
);

-- 크론 작업으로 오래된 파티션 정리 (매월 15일 실행)
SELECT cron.schedule(
    'partition-cleanup',
    '0 2 15 * *',
    'SELECT drop_old_partitions(''candlestick_data'', 12);
     SELECT drop_old_partitions(''system_metrics'', 6, ''monitoring'');'
);
```

## 🚀 성능 최적화 설정

### PostgreSQL 설정 최적화

```sql
-- 메모리 관련 설정
ALTER SYSTEM SET shared_buffers = '1GB';              -- 물리 RAM의 25%
ALTER SYSTEM SET effective_cache_size = '3GB';        -- 물리 RAM의 75%
ALTER SYSTEM SET maintenance_work_mem = '256MB';      -- 인덱스 구축용
ALTER SYSTEM SET work_mem = '64MB';                   -- 정렬/해시 작업용

-- 연결 관련 설정
ALTER SYSTEM SET max_connections = 200;
ALTER SYSTEM SET max_prepared_transactions = 100;

-- WAL 관련 설정 (배치 INSERT 최적화)
ALTER SYSTEM SET wal_buffers = '16MB';
ALTER SYSTEM SET checkpoint_completion_target = 0.9;
ALTER SYSTEM SET checkpoint_timeout = '15min';
ALTER SYSTEM SET max_wal_size = '4GB';
ALTER SYSTEM SET min_wal_size = '1GB';

-- 백그라운드 작업 설정
ALTER SYSTEM SET autovacuum_max_workers = 6;
ALTER SYSTEM SET autovacuum_work_mem = '256MB';
ALTER SYSTEM SET bgwriter_delay = '200ms';
ALTER SYSTEM SET bgwriter_lru_maxpages = 100;

-- 배치 처리 최적화
ALTER SYSTEM SET commit_delay = 1000;                 -- 1ms 지연
ALTER SYSTEM SET commit_siblings = 10;                -- 동시 트랜잭션 임계값

-- 통계 수집 최적화
ALTER SYSTEM SET default_statistics_target = 100;
ALTER SYSTEM SET track_activities = on;
ALTER SYSTEM SET track_counts = on;
ALTER SYSTEM SET track_io_timing = on;
ALTER SYSTEM SET track_functions = 'pl';

-- 병렬 처리 설정
ALTER SYSTEM SET max_parallel_workers = 8;
ALTER SYSTEM SET max_parallel_workers_per_gather = 4;
ALTER SYSTEM SET parallel_tuple_cost = 0.1;

-- 로그 설정
ALTER SYSTEM SET log_min_duration_statement = '1000ms';  -- 느린 쿼리 로깅
ALTER SYSTEM SET log_line_prefix = '%t [%p]: [%l-1] user=%u,db=%d,app=%a,client=%h ';
ALTER SYSTEM SET log_checkpoints = on;
ALTER SYSTEM SET log_connections = on;
ALTER SYSTEM SET log_disconnections = on;

-- 설정 적용
SELECT pg_reload_conf();
```

### 테이블별 최적화

```sql
-- 캔들스틱 데이터 테이블 최적화
ALTER TABLE candlestick_data SET (
    fillfactor = 90,                    -- 페이지 채움률
    toast_tuple_target = 128,           -- TOAST 압축 설정
    autovacuum_vacuum_scale_factor = 0.1,
    autovacuum_analyze_scale_factor = 0.05
);

-- 심볼 테이블 최적화 (읽기 전용에 가까움)
ALTER TABLE symbols SET (
    fillfactor = 100,
    autovacuum_vacuum_scale_factor = 0.2,
    autovacuum_analyze_scale_factor = 0.1
);

-- 시스템 메트릭 테이블 최적화
ALTER TABLE monitoring.system_metrics SET (
    fillfactor = 90,
    autovacuum_vacuum_scale_factor = 0.05,
    autovacuum_analyze_scale_factor = 0.02
);
```

## 🎯 초기 데이터 및 설정

### 기본 데이터 삽입

```sql
-- 거래소 정보
INSERT INTO exchanges (name, display_name, api_endpoint, websocket_endpoint) VALUES
('okx', 'OKX', 'https://www.okx.com/api/v5', 'wss://ws.okx.com:8443/ws/v5/public');

-- 주요 심볼 데이터
INSERT INTO symbols (exchange_id, symbol, base_currency, quote_currency, instrument_type) 
SELECT 1, * FROM VALUES
    ('BTC-USDT', 'BTC', 'USDT', 'SPOT'),
    ('ETH-USDT', 'ETH', 'USDT', 'SPOT'),
    ('BNB-USDT', 'BNB', 'USDT', 'SPOT'),
    ('ADA-USDT', 'ADA', 'USDT', 'SPOT'),
    ('XRP-USDT', 'XRP', 'USDT', 'SPOT'),
    ('SOL-USDT', 'SOL', 'USDT', 'SPOT'),
    ('DOT-USDT', 'DOT', 'USDT', 'SPOT'),
    ('MATIC-USDT', 'MATIC', 'USDT', 'SPOT'),
    ('LINK-USDT', 'LINK', 'USDT', 'SPOT'),
    ('UNI-USDT', 'UNI', 'USDT', 'SPOT')
AS t(symbol, base_currency, quote_currency, instrument_type);

-- 시간프레임 데이터
INSERT INTO timeframes (name, display_name, seconds, sort_order, description) VALUES
('1m', '1 Minute', 60, 1, '1분 캔들'),
('3m', '3 Minutes', 180, 2, '3분 캔들'),
('5m', '5 Minutes', 300, 3, '5분 캔들'),
('15m', '15 Minutes', 900, 4, '15분 캔들'),
('30m', '30 Minutes', 1800, 5, '30분 캔들'),
('1H', '1 Hour', 3600, 6, '1시간 캔들'),
('2H', '2 Hours', 7200, 7, '2시간 캔들'),
('4H', '4 Hours', 14400, 8, '4시간 캔들'),
('6H', '6 Hours', 21600, 9, '6시간 캔들'),
('12H', '12 Hours', 43200, 10, '12시간 캔들'),
('1D', '1 Day', 86400, 11, '1일 캔들'),
('1W', '1 Week', 604800, 12, '1주 캔들'),
('1M', '1 Month', 2592000, 13, '1월 캔들');
```

### 유용한 뷰 생성

```sql
-- 최신 캔들 데이터 뷰
CREATE VIEW v_latest_candles AS
SELECT 
    s.symbol,
    tf.name as timeframe,
    tf.display_name as timeframe_display,
    cd.timestamp,
    cd.open_price,
    cd.high_price,
    cd.low_price,
    cd.close_price,
    cd.volume,
    cd.volume_currency,
    cd.confirm,
    cd.created_at
FROM candlestick_data cd
JOIN symbols s ON cd.symbol_id = s.id
JOIN timeframes tf ON cd.timeframe_id = tf.id
WHERE cd.timestamp >= CURRENT_TIMESTAMP - INTERVAL '1 hour'
ORDER BY s.symbol, tf.sort_order, cd.timestamp DESC;

-- 심볼별 최신 가격 뷰
CREATE VIEW v_symbol_latest_prices AS
WITH latest_1m AS (
    SELECT DISTINCT ON (symbol_id)
        symbol_id,
        timestamp,
        close_price,
        volume
    FROM candlestick_data
    WHERE timeframe_id = (SELECT id FROM timeframes WHERE name = '1m')
    ORDER BY symbol_id, timestamp DESC
)
SELECT 
    s.symbol,
    s.base_currency,
    s.quote_currency,
    l.close_price as latest_price,
    l.volume as latest_volume,
    l.timestamp as updated_at
FROM latest_1m l
JOIN symbols s ON l.symbol_id = s.id
WHERE s.status = 'ACTIVE';

-- 일간 통계 뷰
CREATE VIEW v_daily_symbol_stats AS
SELECT 
    s.symbol,
    ds.date,
    ds.open_price,
    ds.high_price,
    ds.low_price,
    ds.close_price,
    ds.volume,
    ds.price_change,
    ds.price_change_percent,
    ds.candle_count
FROM daily_statistics ds
JOIN symbols s ON ds.symbol_id = s.id
JOIN timeframes tf ON ds.timeframe_id = tf.id
WHERE tf.name = '1D'
AND s.status = 'ACTIVE'
ORDER BY s.symbol, ds.date DESC;
```

## 🔧 데이터베이스 관리 함수

### 데이터 품질 검증

```sql
-- 데이터 품질 검증 함수
CREATE OR REPLACE FUNCTION check_data_quality(
    check_symbol text DEFAULT NULL,
    check_hours integer DEFAULT 24
)
RETURNS TABLE (
    issue_type text,
    symbol text,
    timeframe text,
    issue_count bigint,
    sample_data jsonb
) AS $$
BEGIN
    -- 중복 데이터 검사
    RETURN QUERY
    SELECT 
        'duplicate_records' as issue_type,
        s.symbol,
        tf.name as timeframe,
        COUNT(*) as issue_count,
        jsonb_agg(
            jsonb_build_object(
                'timestamp', cd.timestamp,
                'count', count_per_timestamp
            )
        ) as sample_data
    FROM (
        SELECT 
            symbol_id, timeframe_id, timestamp,
            COUNT(*) as count_per_timestamp
        FROM candlestick_data
        WHERE timestamp >= CURRENT_TIMESTAMP - (check_hours || ' hours')::interval
        AND (check_symbol IS NULL OR EXISTS (
            SELECT 1 FROM symbols WHERE id = symbol_id AND symbol = check_symbol
        ))
        GROUP BY symbol_id, timeframe_id, timestamp
        HAVING COUNT(*) > 1
    ) duplicates
    JOIN candlestick_data cd ON (
        cd.symbol_id = duplicates.symbol_id 
        AND cd.timeframe_id = duplicates.timeframe_id 
        AND cd.timestamp = duplicates.timestamp
    )
    JOIN symbols s ON cd.symbol_id = s.id
    JOIN timeframes tf ON cd.timeframe_id = tf.id
    GROUP BY s.symbol, tf.name;
    
    -- 누락 데이터 검사 (1분 캔들 기준)
    RETURN QUERY
    WITH time_series AS (
        SELECT 
            s.id as symbol_id,
            tf.id as timeframe_id,
            generate_series(
                date_trunc('minute', CURRENT_TIMESTAMP - (check_hours || ' hours')::interval),
                date_trunc('minute', CURRENT_TIMESTAMP),
                (tf.seconds || ' seconds')::interval
            ) as expected_timestamp
        FROM symbols s, timeframes tf
        WHERE s.status = 'ACTIVE' 
        AND tf.is_active = true
        AND (check_symbol IS NULL OR s.symbol = check_symbol)
    )
    SELECT 
        'missing_records' as issue_type,
        s.symbol,
        tf.name as timeframe,
        COUNT(*) as issue_count,
        jsonb_agg(
            jsonb_build_object(
                'expected_timestamp', ts.expected_timestamp
            )
        ) as sample_data
    FROM time_series ts
    JOIN symbols s ON ts.symbol_id = s.id
    JOIN timeframes tf ON ts.timeframe_id = tf.id
    LEFT JOIN candlestick_data cd ON (
        cd.symbol_id = ts.symbol_id 
        AND cd.timeframe_id = ts.timeframe_id 
        AND cd.timestamp = ts.expected_timestamp
    )
    WHERE cd.id IS NULL
    GROUP BY s.symbol, tf.name
    HAVING COUNT(*) > 0;
    
    -- 가격 이상치 검사
    RETURN QUERY
    SELECT 
        'price_anomaly' as issue_type,
        s.symbol,
        tf.name as timeframe,
        COUNT(*) as issue_count,
        jsonb_agg(
            jsonb_build_object(
                'timestamp', cd.timestamp,
                'open_price', cd.open_price,
                'high_price', cd.high_price,
                'low_price', cd.low_price,
                'close_price', cd.close_price
            )
        ) as sample_data
    FROM candlestick_data cd
    JOIN symbols s ON cd.symbol_id = s.id
    JOIN timeframes tf ON cd.timeframe_id = tf.id
    WHERE cd.timestamp >= CURRENT_TIMESTAMP - (check_hours || ' hours')::interval
    AND (check_symbol IS NULL OR s.symbol = check_symbol)
    AND (
        cd.high_price < cd.low_price OR
        cd.high_price < cd.open_price OR
        cd.high_price < cd.close_price OR
        cd.low_price > cd.open_price OR
        cd.low_price > cd.close_price OR
        cd.open_price <= 0 OR
        cd.volume < 0
    )
    GROUP BY s.symbol, tf.name;
END;
$$ LANGUAGE plpgsql;
```

### 통계 및 집계 함수

```sql
-- 일간 통계 갱신 함수
CREATE OR REPLACE FUNCTION update_daily_statistics(target_date date DEFAULT CURRENT_DATE)
RETURNS integer AS $$
DECLARE
    updated_count integer := 0;
BEGIN
    WITH daily_aggregates AS (
        SELECT 
            cd.symbol_id,
            cd.timeframe_id,
            target_date as date,
            
            -- OHLCV 집계
            (array_agg(cd.open_price ORDER BY cd.timestamp))[1] as open_price,
            MAX(cd.high_price) as high_price,
            MIN(cd.low_price) as low_price,
            (array_agg(cd.close_price ORDER BY cd.timestamp DESC))[1] as close_price,
            SUM(cd.volume) as volume,
            SUM(cd.volume_currency) as volume_currency,
            
            -- 통계 정보
            SUM(cd.trade_count) as trade_count,
            SUM(cd.volume * cd.close_price) / NULLIF(SUM(cd.volume), 0) as vwap,
            COUNT(*) as candle_count,
            MIN(cd.timestamp) as first_timestamp,
            MAX(cd.timestamp) as last_timestamp
            
        FROM candlestick_data cd
        WHERE DATE(cd.timestamp) = target_date
        AND cd.confirm = true
        GROUP BY cd.symbol_id, cd.timeframe_id
    )
    INSERT INTO daily_statistics (
        symbol_id, timeframe_id, date,
        open_price, high_price, low_price, close_price,
        volume, volume_currency, trade_count, vwap,
        candle_count, first_timestamp, last_timestamp
    )
    SELECT * FROM daily_aggregates
    ON CONFLICT (symbol_id, timeframe_id, date)
    DO UPDATE SET
        open_price = EXCLUDED.open_price,
        high_price = EXCLUDED.high_price,
        low_price = EXCLUDED.low_price,
        close_price = EXCLUDED.close_price,
        volume = EXCLUDED.volume,
        volume_currency = EXCLUDED.volume_currency,
        trade_count = EXCLUDED.trade_count,
        vwap = EXCLUDED.vwap,
        candle_count = EXCLUDED.candle_count,
        first_timestamp = EXCLUDED.first_timestamp,
        last_timestamp = EXCLUDED.last_timestamp,
        updated_at = CURRENT_TIMESTAMP;
    
    GET DIAGNOSTICS updated_count = ROW_COUNT;
    RAISE NOTICE 'Updated % daily statistics for %', updated_count, target_date;
    RETURN updated_count;
END;
$$ LANGUAGE plpgsql;

-- 통계 갱신 크론 작업
SELECT cron.schedule(
    'daily-statistics-update',
    '5 0 * * *',
    'SELECT update_daily_statistics(CURRENT_DATE - 1);'  -- 전일 통계 갱신
);
```

## 📊 모니터링 및 유지보수

### 성능 모니터링 쿼리

```sql
-- 데이터베이스 크기 모니터링
CREATE VIEW v_database_size_info AS
SELECT 
    schemaname,
    tablename,
    pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename)) as size,
    pg_total_relation_size(schemaname||'.'||tablename) as size_bytes
FROM pg_tables 
WHERE schemaname IN ('trading', 'monitoring')
ORDER BY pg_total_relation_size(schemaname||'.'||tablename) DESC;

-- 파티션 정보 조회
CREATE VIEW v_partition_info AS
SELECT 
    schemaname as schema_name,
    tablename as partition_name,
    pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename)) as size,
    CASE 
        WHEN tablename ~ '_[0-9]{4}_[0-9]{2}$' 
        THEN to_date(substring(tablename from '([0-9]{4}_[0-9]{2})$'), 'YYYY_MM')
        ELSE NULL 
    END as partition_month
FROM pg_tables 
WHERE (tablename LIKE 'candlestick_data_%' OR tablename LIKE 'system_metrics_%')
AND schemaname IN ('trading', 'monitoring')
ORDER BY partition_month DESC NULLS LAST;

-- 인덱스 사용 통계
CREATE VIEW v_index_usage_stats AS
SELECT 
    schemaname as schema_name,
    tablename as table_name,
    indexname as index_name,
    idx_scan as times_used,
    pg_size_pretty(pg_relation_size(indexrelid)) as size,
    idx_tup_read as tuples_read,
    idx_tup_fetch as tuples_fetched
FROM pg_stat_user_indexes
WHERE schemaname IN ('trading', 'monitoring')
ORDER BY idx_scan DESC;
```

### 정리 작업 스크립트

```sql
-- 임시 데이터 정리 함수
CREATE OR REPLACE FUNCTION cleanup_temp_data()
RETURNS void AS $$
BEGIN
    -- 30일 이상 된 품질 로그 정리
    DELETE FROM monitoring.data_quality_log 
    WHERE created_at < CURRENT_TIMESTAMP - INTERVAL '30 days'
    AND resolved = true;
    
    -- 7일 이상 된 시스템 메트릭 정리 (상세 데이터)
    DELETE FROM monitoring.system_metrics
    WHERE timestamp < CURRENT_TIMESTAMP - INTERVAL '7 days'
    AND metric_type = 'histogram';
    
    -- VACUUM 및 ANALYZE
    VACUUM ANALYZE candlestick_data;
    VACUUM ANALYZE monitoring.system_metrics;
    VACUUM ANALYZE monitoring.data_quality_log;
    
    RAISE NOTICE 'Temporary data cleanup completed at %', CURRENT_TIMESTAMP;
END;
$$ LANGUAGE plpgsql;

-- 매일 새벽 2시에 정리 작업 실행
SELECT cron.schedule(
    'temp-data-cleanup',
    '0 2 * * *',
    'SELECT cleanup_temp_data();'
);
```

이 데이터베이스 스키마 가이드를 통해 Claude Code가 확장 가능하고 성능이 우수한 OKX 실시간 캔들 데이터 저장 시스템을 구축할 수 있습니다. 모든 스크립트는 단계별로 실행 가능하며, 자동화된 관리 기능을 포함하고 있습니다.
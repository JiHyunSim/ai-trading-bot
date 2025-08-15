# OKX 실시간 캔들 데이터 수집 시스템 구현 가이드

## 📋 프로젝트 개요

이 문서는 OKX API를 활용한 실시간 캔들스틱 데이터 수집 시스템의 완전한 구현 가이드입니다. Claude Code를 통해 단계별로 구현할 수 있도록 상세한 아키텍처, 코드 예시, 배포 방법을 제공합니다.

### 시스템 특징
- **실시간 데이터 수집**: OKX WebSocket API 기반
- **확장 가능한 아키텍처**: 마이크로서비스 패턴
- **고성능 데이터 저장**: PostgreSQL 파티션 테이블
- **장애 복구**: 자동 재연결 및 Dead Letter Queue
- **모니터링**: Prometheus + Grafana 기반

### 기술 스택
- **Backend**: Python 3.11+, FastAPI, AsyncIO
- **Database**: PostgreSQL 15+, Redis 7+
- **Message Queue**: Redis Pub/Sub
- **Containerization**: Docker, Kubernetes
- **Monitoring**: Prometheus, Grafana

## 🏗️ 시스템 아키텍처

### 전체 구조
```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│  Gateway API    │    │ Data Collectors │    │ Data Processor  │
│  (FastAPI)      │────│ (WebSocket)     │────│ (Batch Insert)  │
└─────────────────┘    └─────────────────┘    └─────────────────┘
         │                       │                       │
         │              ┌─────────────────┐               │
         └──────────────│     Redis       │───────────────┘
                        │  (Message Bus)  │
                        └─────────────────┘
                                 │
                        ┌─────────────────┐
                        │   PostgreSQL    │
                        │   (Partitioned) │
                        └─────────────────┘
```

### 핵심 컴포넌트
1. **Gateway Service**: REST API 및 구독 관리
2. **Data Collector**: WebSocket 클라이언트 및 실시간 수집
3. **Data Processor**: 배치 처리 및 데이터베이스 저장
4. **Message Queue**: Redis 기반 비동기 메시지 전달

## 🚀 빠른 시작 가이드

### 1. 프로젝트 구조 생성
```bash
mkdir okx-trading-system
cd okx-trading-system

# 디렉토리 구조 생성
mkdir -p {services/{gateway,collector,processor},sql/{init,migrations},k8s,monitoring,tests}
```

### 2. 핵심 의존성 설치
```bash
# requirements.txt 생성
cat > requirements.txt << 'EOF'
fastapi==0.104.1
uvicorn[standard]==0.24.0
websockets==12.0
asyncpg==0.29.0
redis[hiredis]==5.0.1
pydantic==2.5.0
pydantic-settings==2.1.0
python-multipart==0.0.6
pytest==7.4.3
pytest-asyncio==0.21.1
prometheus-client==0.19.0
aiohttp==3.9.1
python-dotenv==1.0.0
cryptography==41.0.8
EOF

pip install -r requirements.txt
```

### 3. 환경 설정
```bash
# .env 파일 생성
cat > .env << 'EOF'
# OKX API Configuration
OKX_API_KEY=your_api_key_here
OKX_SECRET_KEY=your_secret_key_here
OKX_PASSPHRASE=your_passphrase_here

# Database Configuration
DB_HOST=localhost
DB_PORT=5432
DB_NAME=okx_trading_data
DB_USER=postgres
DB_PASSWORD=your_password_here

# Redis Configuration
REDIS_HOST=localhost
REDIS_PORT=6379
REDIS_DB=0

# Service Configuration
BATCH_SIZE=100
BATCH_TIMEOUT=5
MAX_RECONNECT_DELAY=300

# Monitoring
PROMETHEUS_PORT=8080
GRAFANA_PORT=3000
EOF
```

## 📊 데이터베이스 설계

### PostgreSQL 스키마
데이터베이스 스키마는 확장성과 성능을 고려하여 설계되었습니다:

```sql
-- 심볼 정보 테이블
CREATE TABLE symbols (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(20) UNIQUE NOT NULL,
    base_currency VARCHAR(10) NOT NULL,
    quote_currency VARCHAR(10) NOT NULL,
    instrument_type VARCHAR(20) NOT NULL,
    status VARCHAR(10) DEFAULT 'ACTIVE',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- 시간프레임 정의 테이블
CREATE TABLE timeframes (
    id SERIAL PRIMARY KEY,
    name VARCHAR(10) UNIQUE NOT NULL,
    display_name VARCHAR(20) NOT NULL,
    seconds INTEGER NOT NULL,
    sort_order INTEGER DEFAULT 0,
    is_active BOOLEAN DEFAULT true
);

-- 캔들스틱 데이터 테이블 (월별 파티션)
CREATE TABLE candlestick_data (
    id UUID DEFAULT gen_random_uuid(),
    symbol_id INTEGER NOT NULL REFERENCES symbols(id),
    timeframe_id INTEGER NOT NULL REFERENCES timeframes(id),
    timestamp TIMESTAMP WITH TIME ZONE NOT NULL,
    open_price DECIMAL(20,8) NOT NULL,
    high_price DECIMAL(20,8) NOT NULL,
    low_price DECIMAL(20,8) NOT NULL,
    close_price DECIMAL(20,8) NOT NULL,
    volume DECIMAL(20,8) NOT NULL,
    volume_currency DECIMAL(20,8),
    confirm BOOLEAN DEFAULT false,
    raw_data JSONB,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id, timestamp)
) PARTITION BY RANGE (timestamp);

-- 유니크 제약조건 (중복 방지)
CREATE UNIQUE INDEX idx_candlestick_unique 
ON candlestick_data (symbol_id, timeframe_id, timestamp);
```

### 초기 데이터 삽입
```sql
-- 주요 심볼 데이터
INSERT INTO symbols (symbol, base_currency, quote_currency, instrument_type) VALUES
('BTC-USDT', 'BTC', 'USDT', 'SPOT'),
('ETH-USDT', 'ETH', 'USDT', 'SPOT'),
('BNB-USDT', 'BNB', 'USDT', 'SPOT');

-- 시간프레임 데이터
INSERT INTO timeframes (name, display_name, seconds, sort_order) VALUES
('1m', '1 Minute', 60, 1),
('5m', '5 Minutes', 300, 2),
('15m', '15 Minutes', 900, 3),
('1H', '1 Hour', 3600, 4),
('1D', '1 Day', 86400, 5);
```

## 🔧 핵심 서비스 구현

### Gateway Service (services/gateway/main.py)
```python
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import List, Optional
import redis.asyncio as redis
import json
from datetime import datetime

app = FastAPI(title="OKX Trading Gateway")

class SubscriptionRequest(BaseModel):
    symbols: List[str]
    timeframes: List[str]
    webhook_url: Optional[str] = None

@app.on_event("startup")
async def startup_event():
    app.redis = await redis.from_url("redis://localhost:6379")

@app.post("/api/v1/subscribe")
async def subscribe_to_symbols(request: SubscriptionRequest):
    """심볼 구독 요청 처리"""
    subscription_config = {
        "action": "subscribe",
        "symbols": request.symbols,
        "timeframes": request.timeframes,
        "webhook_url": request.webhook_url,
        "timestamp": datetime.utcnow().isoformat()
    }
    
    for symbol in request.symbols:
        # 구독 설정 저장
        await app.redis.set(
            f"subscription:{symbol}",
            json.dumps(subscription_config),
            ex=3600
        )
        
        # 컬렉터에 신호 전송
        await app.redis.publish(
            f"collector:{symbol}",
            json.dumps(subscription_config)
        )
    
    return {
        "status": "success",
        "message": f"Subscribed to {len(request.symbols)} symbols",
        "symbols": request.symbols
    }

@app.get("/api/v1/status/{symbol}")
async def get_symbol_status(symbol: str):
    """심볼별 수집 상태 조회"""
    status = await app.redis.get(f"status:{symbol}")
    if not status:
        raise HTTPException(status_code=404, detail="Symbol not found")
    
    return json.loads(status)

@app.get("/health")
async def health_check():
    return {"status": "healthy", "timestamp": datetime.utcnow()}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
```

### Data Collector Service (services/collector/main.py)
```python
import asyncio
import websockets
import json
import redis.asyncio as redis
from datetime import datetime
import logging
import hmac
import hashlib
import base64
import os

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class OKXDataCollector:
    def __init__(self, symbol: str):
        self.symbol = symbol
        self.ws_url = "wss://ws.okx.com:8443/ws/v5/public"
        self.redis_client = None
        self.is_running = False
        self.reconnect_delay = 5
        self.max_reconnect_delay = 300
        
    async def initialize(self):
        """서비스 초기화"""
        self.redis_client = await redis.from_url("redis://localhost:6379")
        
        # 구독 요청 리스너 시작
        asyncio.create_task(self.listen_for_subscriptions())
        
    async def listen_for_subscriptions(self):
        """Gateway로부터 구독 요청 수신"""
        pubsub = self.redis_client.pubsub()
        await pubsub.subscribe(f"collector:{self.symbol}")
        
        async for message in pubsub.listen():
            if message['type'] == 'message':
                config = json.loads(message['data'])
                if config['action'] == 'subscribe':
                    logger.info(f"Starting collection for {self.symbol}")
                    asyncio.create_task(self.start_collection(config))
    
    async def start_collection(self, config: dict):
        """WebSocket 연결 및 데이터 수집"""
        self.is_running = True
        timeframes = config.get('timeframes', ['1m'])
        
        while self.is_running:
            try:
                async with websockets.connect(self.ws_url) as websocket:
                    # 구독 메시지 전송
                    subscription_args = []
                    for timeframe in timeframes:
                        subscription_args.append({
                            "channel": f"candle{timeframe}",
                            "instId": self.symbol
                        })
                    
                    subscribe_msg = {
                        "op": "subscribe",
                        "args": subscription_args
                    }
                    
                    await websocket.send(json.dumps(subscribe_msg))
                    logger.info(f"Subscribed to {self.symbol} - {timeframes}")
                    
                    # 상태 업데이트
                    await self.update_status("connected")
                    
                    # 메시지 수신 루프
                    async for message in websocket:
                        await self.process_message(json.loads(message))
                        
            except Exception as e:
                logger.error(f"WebSocket error for {self.symbol}: {e}")
                await self.update_status("disconnected")
                await asyncio.sleep(self.reconnect_delay)
                self.reconnect_delay = min(self.reconnect_delay * 2, self.max_reconnect_delay)
    
    async def process_message(self, data: dict):
        """수신된 메시지 처리 및 Redis 큐 전송"""
        if 'data' not in data:
            return
            
        for candle_data in data['data']:
            processed_data = {
                "symbol": self.symbol,
                "timeframe": data['arg']['channel'].replace('candle', ''),
                "timestamp": int(candle_data[0]),
                "open": float(candle_data[1]),
                "high": float(candle_data[2]),
                "low": float(candle_data[3]),
                "close": float(candle_data[4]),
                "volume": float(candle_data[5]),
                "volume_currency": float(candle_data[6]),
                "confirm": candle_data[8] == "1",
                "received_at": datetime.utcnow().isoformat()
            }
            
            # Redis 큐에 전송
            await self.redis_client.lpush(
                "candle_data_queue",
                json.dumps(processed_data)
            )
            
            logger.info(f"Queued: {self.symbol} {processed_data['timeframe']} {processed_data['close']}")
    
    async def update_status(self, status: str):
        """서비스 상태 업데이트"""
        status_data = {
            "symbol": self.symbol,
            "status": status,
            "last_update": datetime.utcnow().isoformat()
        }
        
        await self.redis_client.set(
            f"status:{self.symbol}",
            json.dumps(status_data),
            ex=300
        )

async def main():
    symbol = os.getenv('SYMBOL', 'BTC-USDT')
    collector = OKXDataCollector(symbol)
    await collector.initialize()
    
    # 서비스 실행
    while True:
        await asyncio.sleep(1)

if __name__ == "__main__":
    asyncio.run(main())
```

### Data Processor Service (services/processor/main.py)
```python
import asyncio
import asyncpg
import redis.asyncio as redis
import json
from datetime import datetime
from typing import List, Dict
import logging
import os

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class DataProcessor:
    def __init__(self):
        self.redis_client = None
        self.db_pool = None
        self.batch_size = int(os.getenv('BATCH_SIZE', 100))
        self.batch_timeout = int(os.getenv('BATCH_TIMEOUT', 5))
        
    async def initialize(self):
        """서비스 초기화"""
        # Redis 연결
        self.redis_client = await redis.from_url("redis://localhost:6379")
        
        # PostgreSQL 연결 풀
        self.db_pool = await asyncpg.create_pool(
            host=os.getenv('DB_HOST', 'localhost'),
            port=int(os.getenv('DB_PORT', 5432)),
            database=os.getenv('DB_NAME', 'okx_trading_data'),
            user=os.getenv('DB_USER', 'postgres'),
            password=os.getenv('DB_PASSWORD'),
            min_size=5,
            max_size=20
        )
        
        logger.info("Data Processor initialized")
    
    async def start_processing(self):
        """데이터 처리 시작"""
        tasks = [
            self.batch_processor(),
            self.dead_letter_processor(),
            self.metrics_collector()
        ]
        
        await asyncio.gather(*tasks)
    
    async def batch_processor(self):
        """배치 처리 메인 루프"""
        while True:
            try:
                batch = []
                
                # 첫 번째 메시지 대기
                message = await self.redis_client.brpop("candle_data_queue", timeout=self.batch_timeout)
                if not message:
                    continue
                
                batch.append(json.loads(message[1]))
                
                # 배치 크기만큼 추가 메시지 수집
                for _ in range(self.batch_size - 1):
                    message = await self.redis_client.rpop("candle_data_queue")
                    if not message:
                        break
                    batch.append(json.loads(message))
                
                # 배치 처리
                await self.process_batch(batch)
                
            except Exception as e:
                logger.error(f"Batch processing error: {e}")
                await asyncio.sleep(1)
    
    async def process_batch(self, batch: List[Dict]):
        """배치 데이터 PostgreSQL 저장"""
        if not batch:
            return
            
        try:
            async with self.db_pool.acquire() as conn:
                async with conn.transaction():
                    insert_query = """
                        INSERT INTO candlestick_data 
                        (symbol_id, timeframe_id, timestamp, open_price, high_price, 
                         low_price, close_price, volume, volume_currency, confirm, raw_data)
                        VALUES (
                            (SELECT id FROM symbols WHERE symbol = $1),
                            (SELECT id FROM timeframes WHERE name = $2),
                            to_timestamp($3/1000), $4, $5, $6, $7, $8, $9, $10, $11
                        )
                        ON CONFLICT (symbol_id, timeframe_id, timestamp) 
                        DO UPDATE SET
                            open_price = EXCLUDED.open_price,
                            high_price = EXCLUDED.high_price,
                            low_price = EXCLUDED.low_price,
                            close_price = EXCLUDED.close_price,
                            volume = EXCLUDED.volume,
                            volume_currency = EXCLUDED.volume_currency,
                            confirm = EXCLUDED.confirm,
                            raw_data = EXCLUDED.raw_data
                    """
                    
                    batch_data = []
                    for item in batch:
                        batch_data.append((
                            item['symbol'],
                            item['timeframe'],
                            item['timestamp'],
                            item['open'],
                            item['high'],
                            item['low'],
                            item['close'],
                            item['volume'],
                            item['volume_currency'],
                            item['confirm'],
                            json.dumps(item)
                        ))
                    
                    await conn.executemany(insert_query, batch_data)
                    logger.info(f"Processed batch of {len(batch)} records")
                    
        except Exception as e:
            logger.error(f"Database error: {e}")
            await self.send_to_dlq(batch, str(e))
    
    async def send_to_dlq(self, batch: List[Dict], error: str):
        """Dead Letter Queue로 실패 데이터 전송"""
        for item in batch:
            dlq_item = {
                **item,
                "error": error,
                "failed_at": datetime.utcnow().isoformat(),
                "retry_count": item.get("retry_count", 0) + 1
            }
            
            await self.redis_client.lpush(
                "dead_letter_queue",
                json.dumps(dlq_item)
            )
    
    async def dead_letter_processor(self):
        """Dead Letter Queue 처리"""
        while True:
            try:
                message = await self.redis_client.brpop("dead_letter_queue", timeout=30)
                if not message:
                    continue
                
                item = json.loads(message[1])
                
                if item.get("retry_count", 0) < 3:
                    # 재시도
                    await asyncio.sleep(item["retry_count"] * 10)
                    await self.redis_client.lpush("candle_data_queue", json.dumps(item))
                    logger.info(f"Retrying item: {item['symbol']} {item['timeframe']}")
                else:
                    # 영구 실패
                    logger.error(f"Permanent failure: {item}")
                    
            except Exception as e:
                logger.error(f"DLQ processing error: {e}")
                await asyncio.sleep(5)
    
    async def metrics_collector(self):
        """메트릭 수집"""
        while True:
            try:
                queue_length = await self.redis_client.llen("candle_data_queue")
                dlq_length = await self.redis_client.llen("dead_letter_queue")
                
                metrics = {
                    "queue_length": queue_length,
                    "dlq_length": dlq_length,
                    "timestamp": datetime.utcnow().isoformat()
                }
                
                await self.redis_client.set("processor_metrics", json.dumps(metrics), ex=60)
                
                if queue_length > 10000:
                    logger.warning(f"High queue length: {queue_length}")
                
                await asyncio.sleep(30)
                
            except Exception as e:
                logger.error(f"Metrics collection error: {e}")
                await asyncio.sleep(30)

async def main():
    processor = DataProcessor()
    await processor.initialize()
    await processor.start_processing()

if __name__ == "__main__":
    asyncio.run(main())
```

## 🐳 Docker 구성

### Docker Compose (docker-compose.yml)
```yaml
version: '3.8'

services:
  postgresql:
    image: postgres:15-alpine
    environment:
      POSTGRES_DB: okx_trading_data
      POSTGRES_USER: postgres
      POSTGRES_PASSWORD: ${DB_PASSWORD}
    ports:
      - "5432:5432"
    volumes:
      - postgres_data:/var/lib/postgresql/data
      - ./sql/init:/docker-entrypoint-initdb.d/
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U postgres"]
      interval: 10s
      timeout: 5s
      retries: 5

  redis:
    image: redis:7-alpine
    command: redis-server --appendonly yes
    ports:
      - "6379:6379"
    volumes:
      - redis_data:/data

  gateway:
    build:
      context: ./services/gateway
    ports:
      - "8000:8000"
    environment:
      - REDIS_HOST=redis
      - DB_HOST=postgresql
    depends_on:
      postgresql:
        condition: service_healthy
      redis:
        condition: service_started

  collector-btc:
    build:
      context: ./services/collector
    environment:
      - SYMBOL=BTC-USDT
      - REDIS_HOST=redis
    depends_on:
      - redis

  collector-eth:
    build:
      context: ./services/collector
    environment:
      - SYMBOL=ETH-USDT
      - REDIS_HOST=redis
    depends_on:
      - redis

  processor:
    build:
      context: ./services/processor
    environment:
      - REDIS_HOST=redis
      - DB_HOST=postgresql
    depends_on:
      postgresql:
        condition: service_healthy
      redis:
        condition: service_started

volumes:
  postgres_data:
  redis_data:
```

## 🚀 실행 방법

### 1. 개발 환경 실행
```bash
# 환경 변수 설정
cp .env.example .env
# .env 파일 편집

# Docker Compose로 실행
docker-compose up -d

# 로그 확인
docker-compose logs -f
```

### 2. 구독 요청 테스트
```bash
# API를 통한 구독 요청
curl -X POST "http://localhost:8000/api/v1/subscribe" \
     -H "Content-Type: application/json" \
     -d '{
       "symbols": ["BTC-USDT", "ETH-USDT"],
       "timeframes": ["1m", "5m", "1H"]
     }'

# 상태 확인
curl "http://localhost:8000/api/v1/status/BTC-USDT"
```

### 3. 데이터 확인
```sql
-- PostgreSQL에서 수집된 데이터 확인
SELECT 
    s.symbol,
    tf.name as timeframe,
    COUNT(*) as record_count,
    MIN(cd.timestamp) as first_record,
    MAX(cd.timestamp) as last_record
FROM candlestick_data cd
JOIN symbols s ON cd.symbol_id = s.id
JOIN timeframes tf ON cd.timeframe_id = tf.id
GROUP BY s.symbol, tf.name
ORDER BY s.symbol, tf.sort_order;
```

## 📊 모니터링 및 운영

### 주요 메트릭
1. **처리량**: 초당 처리된 메시지 수
2. **지연시간**: WebSocket → DB 저장 시간
3. **큐 길이**: Redis 큐 백로그
4. **에러율**: 실패한 메시지 비율
5. **데이터 품질**: 누락/중복 데이터 감지

### 알림 설정
- 큐 길이 > 10,000개
- 에러율 > 5%
- WebSocket 연결 끊김 > 5분
- 데이터베이스 연결 실패

## 🔧 문제해결 가이드

### 자주 발생하는 문제
1. **WebSocket 연결 끊김**: 재연결 로직 확인, API 키 유효성 검증
2. **데이터베이스 성능**: 파티션 및 인덱스 최적화
3. **메모리 부족**: 배치 크기 조정, 연결 풀 최적화
4. **중복 데이터**: UPSERT 쿼리 및 유니크 제약조건 확인

### 로그 분석
```bash
# 서비스별 로그 확인
docker-compose logs collector-btc
docker-compose logs processor
docker-compose logs gateway

# 에러 로그 필터링
docker-compose logs | grep ERROR
```

## 📈 성능 최적화

### 데이터베이스 튜닝
```sql
-- PostgreSQL 성능 설정
ALTER SYSTEM SET shared_buffers = '256MB';
ALTER SYSTEM SET effective_cache_size = '1GB';
ALTER SYSTEM SET maintenance_work_mem = '64MB';
ALTER SYSTEM SET checkpoint_completion_target = 0.9;
ALTER SYSTEM SET wal_buffers = '16MB';
SELECT pg_reload_conf();
```

### 시스템 모니터링
```bash
# Redis 메트릭
redis-cli info memory
redis-cli info stats

# PostgreSQL 메트릭
psql -c "SELECT * FROM pg_stat_activity WHERE state = 'active';"
psql -c "SELECT schemaname, tablename, n_tup_ins, n_tup_del FROM pg_stat_user_tables;"
```

## 🔐 보안 고려사항

### API 키 관리
- 환경 변수로 관리
- Kubernetes Secret 사용
- 정기적 키 로테이션

### 네트워크 보안
- VPC 내부 통신
- TLS/SSL 암호화
- 방화벽 규칙 설정

### 데이터 보안
- 데이터베이스 암호화
- 접근 권한 최소화
- 로그 민감정보 제거

## 📚 확장 가능성

### 스케일링 옵션
1. **수직 스케일링**: CPU/메모리 증설
2. **수평 스케일링**: 컨테이너 복제
3. **데이터베이스 샤딩**: 심볼별 분산
4. **캐싱 레이어**: Redis Cluster 도입

### 추가 기능
- 실시간 알림 시스템
- 데이터 분석 API
- 백테스팅 엔진
- ML 모델 통합

이 문서를 통해 Claude Code가 단계적으로 OKX 실시간 캔들 데이터 수집 시스템을 구현할 수 있습니다. 각 컴포넌트는 독립적으로 개발하고 테스트할 수 있도록 설계되었습니다.
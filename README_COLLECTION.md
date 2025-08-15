# BTC-USDT 무기한 선물 실시간 캔들 데이터 수집 시스템

이 시스템은 OKX API를 통해 BTC-USDT 무기한 선물의 5m, 15m, 1h, 4h, 1d 타임프레임에서 실시간 캔들 데이터를 수집하여 PostgreSQL에 저장합니다.

## 🏗️ 시스템 아키텍처

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   Gateway API   │    │   Collector     │    │   Processor     │
│   (FastAPI)     │    │  (WebSocket)    │    │ (Batch Process) │
│                 │    │                 │    │                 │
│ - 구독 관리      │◄──►│ - OKX 연결      │    │ - 데이터 처리    │
│ - 상태 모니터링  │    │ - 실시간 수집    │    │ - DB 저장       │
│ - REST API      │    │ - Redis 큐 전송  │    │ - 배치 처리     │
└─────────────────┘    └─────────────────┘    └─────────────────┘
         │                       │                       │
         └───────────────────────┼───────────────────────┘
                                 │
                    ┌─────────────────┐
                    │      Redis      │
                    │  (Message Queue)│
                    │                 │
                    │ - 캔들 데이터 큐 │
                    │ - 상태 정보     │
                    │ - 구독 정보     │
                    └─────────────────┘
                                 │
                    ┌─────────────────┐
                    │   PostgreSQL    │
                    │ (Data Storage)  │
                    │                 │
                    │ - 월별 파티셔닝  │
                    │ - 캔들 데이터    │
                    │ - 배치 상태     │
                    └─────────────────┘
```

## 🚀 빠른 시작

### 1. 원클릭 실행 (권장)

```bash
# 모든 서비스 시작 + 자동 데이터 수집 시작
./run_collection.sh

# 모니터링과 함께 시작
./run_collection.sh --monitor

# 데이터 검증과 함께 시작
./run_collection.sh --validate
```

### 2. 수동 실행

```bash
# 1. Docker 서비스 시작 (PostgreSQL, Redis)
docker-compose -f docker-compose.local.yml up -d

# 2. Python 서비스들 시작 (3개 터미널)
# Terminal 1: Gateway
cd services/gateway && python main.py

# Terminal 2: Collector  
cd services/collector && python main.py

# Terminal 3: Processor
cd services/processor && python main.py

# 3. 데이터 수집 시작
python start_collection.py
```

## 📊 모니터링 및 관리

### 실시간 모니터링
```bash
# 실시간 시스템 상태 모니터링
python monitor_collection.py

# 사용자 정의 설정으로 모니터링
python monitor_collection.py --refresh 5 --redis-host localhost
```

### 데이터 품질 검증
```bash
# 데이터 품질 및 연속성 검증
python validate_data.py

# 특정 심볼 검증
python validate_data.py --symbol BTC-USDT-SWAP
```

### API를 통한 관리
```bash
# 구독 상태 확인
curl http://localhost:8000/api/v1/subscriptions

# 특정 심볼 상태 확인
curl http://localhost:8000/api/v1/status/BTC-USDT-SWAP

# 헬스체크
curl http://localhost:8000/health
```

## ⚙️ 설정

### 환경 변수 (.env)
```bash
# BTC-USDT 무기한 선물 실시간 수집 설정
DEFAULT_SYMBOL=BTC-USDT-SWAP
DEFAULT_TIMEFRAMES=5m,15m,1h,4h,1d
AUTO_START=true

# 데이터베이스 설정
DB_HOST=localhost
DB_PORT=5432
DB_NAME=trading_bot
DB_USER=trading_bot
DB_PASSWORD=trading_bot_password

# Redis 설정
REDIS_HOST=localhost
REDIS_PORT=6379
REDIS_PASSWORD=redis_password

# OKX API 설정 (실제 키 필요시)
OKX_SANDBOX=true
# OKX_API_KEY=your_api_key_here
# OKX_SECRET_KEY=your_secret_key_here
# OKX_PASSPHRASE=your_passphrase_here
```

### 수집 대상 수정
Collector 설정에서 기본 심볼과 타임프레임을 변경할 수 있습니다:

```python
# services/collector/app/core/config.py
DEFAULT_SYMBOL: str = Field(default="BTC-USDT-SWAP")
DEFAULT_TIMEFRAMES: str = Field(default="5m,15m,1h,4h,1d") 
```

## 📁 프로젝트 구조

```
ai-trading-bot/
├── services/
│   ├── gateway/          # REST API Gateway
│   ├── collector/        # WebSocket Data Collector  
│   └── processor/        # Batch Data Processor
├── scripts/
│   └── init-db.sql       # 데이터베이스 초기화
├── logs/                 # 서비스 로그 파일
├── start_collection.py   # 자동 구독 시작 스크립트
├── monitor_collection.py # 실시간 모니터링 도구
├── validate_data.py      # 데이터 품질 검증 도구
├── run_collection.sh     # 통합 실행 스크립트
├── docker-compose.local.yml  # 로컬 개발용
├── docker-compose.auto.yml   # 자동 실행용 (Docker 전체)
└── README_COLLECTION.md  # 이 파일
```

## 📈 수집되는 데이터

### 타임프레임
- **5m**: 5분봉
- **15m**: 15분봉  
- **1h**: 1시간봉
- **4h**: 4시간봉
- **1d**: 일봉

### 캔들 데이터 구조
```json
{
  "symbol": "BTC-USDT-SWAP",
  "timeframe": "5m", 
  "timestamp_ms": 1693401600000,
  "open_price": 26250.5,
  "high_price": 26275.0,
  "low_price": 26240.0,
  "close_price": 26260.8,
  "volume": 145.23,
  "volume_currency": 3812547.12,
  "confirm": true,
  "received_at": "2023-08-30T12:00:05.123Z",
  "source": "okx_websocket"
}
```

## 🗄️ 데이터베이스 스키마

### 캔들스틱 테이블 (월별 파티셔닝)
```sql
-- 메인 테이블
CREATE TABLE trading.candlesticks (
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

-- 월별 파티션 자동 생성
-- candlesticks_2023_08, candlesticks_2023_09, ...
```

## 🔍 모니터링 대시보드

모니터링 도구 실행시 다음과 같은 정보를 실시간으로 확인할 수 있습니다:

```
================================================================================
🚀 BTC-USDT Collection Monitor - 2023-08-30 12:00:00
================================================================================
📊 Monitor Uptime: 1h 23m

📦 REDIS QUEUE STATUS
----------------------------------------
Queue Length: 1,234 messages
Processed: 98,765 total  
Errors: 12 total
Processing Rate: 45.67 msg/sec
Error Rate: 0.02 err/sec

📡 ACTIVE SUBSCRIPTIONS
----------------------------------------
Symbol: BTC-USDT-SWAP
  Status: active
  Timeframes: 5m, 15m, 1h, 4h, 1d

🔌 COLLECTOR STATUS
----------------------------------------
Symbol: BTC-USDT-SWAP
  Connection: 🟢 Connected
  Messages: 98,765
  Errors: 12
  Reconnects: 2
  Uptime: 1h 22m
  Channels: candle5m, candle15m, candle1h, candle4h, candle1d

🟢 SYSTEM HEALTH: 98%
================================================================================
```

## 🛠️ 문제 해결

### 일반적인 문제들

1. **WebSocket 연결 실패**
   ```bash
   # OKX 서버 연결 확인
   curl -I https://ws.okx.com
   
   # 방화벽/프록시 설정 확인
   # Sandbox URL 사용 여부 확인
   ```

2. **데이터베이스 연결 문제**
   ```bash
   # PostgreSQL 컨테이너 상태 확인
   docker ps | grep postgres
   
   # 데이터베이스 연결 테스트
   psql -h localhost -U trading_bot -d trading_bot
   ```

3. **Redis 연결 문제**
   ```bash
   # Redis 컨테이너 상태 확인
   docker ps | grep redis
   
   # Redis 연결 테스트
   redis-cli -h localhost -p 6379 -a redis_password ping
   ```

### 로그 확인
```bash
# 서비스별 로그 확인
tail -f logs/gateway.log
tail -f logs/collector.log  
tail -f logs/processor.log

# Docker 로그 확인
docker-compose -f docker-compose.local.yml logs -f
```

## 🚨 중요 사항

### 실제 거래 환경 사용시 주의점
1. **OKX API 키 설정**: 실제 API 키를 환경변수로 설정
2. **Sandbox 모드 비활성화**: `OKX_SANDBOX=false` 설정
3. **Rate Limit 주의**: OKX API 요청 제한 준수
4. **데이터 백업**: 중요한 데이터는 정기적으로 백업

### 성능 최적화
- **PostgreSQL 튜닝**: 대용량 데이터 처리를 위한 설정 최적화
- **Redis 메모리 관리**: 큐 크기 모니터링 및 메모리 사용량 관리
- **네트워크 안정성**: 안정적인 인터넷 연결 확보

## 📞 지원

문제가 발생하거나 개선사항이 있다면:

1. **로그 파일 확인**: `logs/` 디렉토리의 로그 파일 검토
2. **시스템 상태 확인**: `python monitor_collection.py` 실행
3. **데이터 품질 확인**: `python validate_data.py` 실행
4. **API 상태 확인**: `curl http://localhost:8000/health`

---

**이 시스템을 통해 BTC-USDT 무기한 선물의 안정적이고 지속적인 실시간 캔들 데이터 수집이 가능합니다!** 🚀📈
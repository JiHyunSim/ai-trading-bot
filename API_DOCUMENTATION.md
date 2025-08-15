# OKX 실시간 캔들 데이터 수집 시스템 API 문서

## 📚 API 개요

이 문서는 OKX 실시간 캔들 데이터 수집 시스템의 REST API 명세서입니다. Claude Code를 통해 구현할 수 있는 모든 엔드포인트와 사용법을 제공합니다.

### Base URL
```
http://localhost:8000/api/v1
```

### Authentication
현재 버전에서는 API 키 인증을 사용하지 않습니다. 프로덕션 환경에서는 JWT 토큰 또는 API 키 인증을 권장합니다.

## 📋 엔드포인트 목록

### 1. 구독 관리

#### POST /subscribe
심볼과 시간프레임 구독을 시작합니다.

**Request Body:**
```json
{
  "symbols": ["BTC-USDT", "ETH-USDT"],
  "timeframes": ["1m", "5m", "1H"],
  "webhook_url": "https://your-webhook.com/callback" // 선택사항
}
```

**Response (200):**
```json
{
  "status": "success",
  "message": "Subscribed to 2 symbols",
  "symbols": ["BTC-USDT", "ETH-USDT"],
  "subscription_id": "sub_12345",
  "created_at": "2024-08-15T10:30:00Z"
}
```

**Response (400) - 잘못된 요청:**
```json
{
  "status": "error",
  "message": "Invalid symbols or timeframes",
  "details": {
    "invalid_symbols": ["INVALID-SYMBOL"],
    "invalid_timeframes": ["invalid_tf"]
  }
}
```

**cURL 예시:**
```bash
curl -X POST "http://localhost:8000/api/v1/subscribe" \
     -H "Content-Type: application/json" \
     -d '{
       "symbols": ["BTC-USDT", "ETH-USDT"],
       "timeframes": ["1m", "5m", "1H"]
     }'
```

#### DELETE /subscribe/{symbol}
특정 심볼의 구독을 중지합니다.

**Parameters:**
- `symbol` (path): 구독 중지할 심볼 (예: BTC-USDT)

**Response (200):**
```json
{
  "status": "success",
  "message": "Unsubscribed from BTC-USDT",
  "symbol": "BTC-USDT",
  "stopped_at": "2024-08-15T10:35:00Z"
}
```

#### GET /subscriptions
현재 활성 구독 목록을 조회합니다.

**Response (200):**
```json
{
  "status": "success",
  "total": 2,
  "subscriptions": [
    {
      "symbol": "BTC-USDT",
      "timeframes": ["1m", "5m", "1H"],
      "status": "active",
      "started_at": "2024-08-15T10:30:00Z",
      "last_message": "2024-08-15T10:45:30Z"
    },
    {
      "symbol": "ETH-USDT",
      "timeframes": ["1m", "5m", "1H"],
      "status": "active",
      "started_at": "2024-08-15T10:30:00Z",
      "last_message": "2024-08-15T10:45:28Z"
    }
  ]
}
```

### 2. 상태 모니터링

#### GET /status/{symbol}
특정 심볼의 수집 상태를 조회합니다.

**Parameters:**
- `symbol` (path): 조회할 심볼 (예: BTC-USDT)

**Response (200):**
```json
{
  "symbol": "BTC-USDT",
  "status": "connected",
  "last_update": "2024-08-15T10:45:30Z",
  "timeframes": ["1m", "5m", "1H"],
  "statistics": {
    "messages_received": 1547,
    "messages_processed": 1545,
    "messages_failed": 2,
    "uptime_seconds": 3600,
    "last_price": 45234.56
  },
  "connection_info": {
    "websocket_connected": true,
    "last_reconnect": "2024-08-15T09:30:00Z",
    "reconnect_count": 0
  }
}
```

**Response (404) - 심볼을 찾을 수 없음:**
```json
{
  "status": "error",
  "message": "Symbol not found",
  "symbol": "UNKNOWN-SYMBOL"
}
```

#### GET /status
모든 심볼의 전체 시스템 상태를 조회합니다.

**Response (200):**
```json
{
  "system_status": "healthy",
  "timestamp": "2024-08-15T10:45:30Z",
  "services": {
    "gateway": "healthy",
    "redis": "healthy",
    "database": "healthy",
    "collectors": {
      "total": 5,
      "healthy": 5,
      "unhealthy": 0
    },
    "processors": {
      "total": 2,
      "healthy": 2,
      "unhealthy": 0
    }
  },
  "metrics": {
    "total_symbols": 5,
    "active_subscriptions": 3,
    "messages_per_second": 25.4,
    "queue_length": 156,
    "database_connections": 8
  },
  "symbols": [
    {
      "symbol": "BTC-USDT",
      "status": "connected",
      "last_message": "2024-08-15T10:45:29Z"
    },
    {
      "symbol": "ETH-USDT", 
      "status": "connected",
      "last_message": "2024-08-15T10:45:30Z"
    }
  ]
}
```

### 3. 데이터 조회

#### GET /data/{symbol}/{timeframe}
특정 심볼과 시간프레임의 캔들 데이터를 조회합니다.

**Parameters:**
- `symbol` (path): 심볼 (예: BTC-USDT)
- `timeframe` (path): 시간프레임 (예: 1m, 5m, 1H, 1D)

**Query Parameters:**
- `limit` (int): 조회할 레코드 수 (기본값: 100, 최대: 1000)
- `start_time` (timestamp): 시작 시간 (ISO 8601 형식)
- `end_time` (timestamp): 종료 시간 (ISO 8601 형식)
- `sort` (string): 정렬 순서 (asc/desc, 기본값: desc)

**Response (200):**
```json
{
  "symbol": "BTC-USDT",
  "timeframe": "1m",
  "count": 100,
  "data": [
    {
      "timestamp": "2024-08-15T10:45:00Z",
      "open": 45234.56,
      "high": 45245.67,
      "low": 45220.34,
      "close": 45238.90,
      "volume": 12.34567,
      "volume_currency": 558234.12,
      "confirm": true
    },
    {
      "timestamp": "2024-08-15T10:44:00Z", 
      "open": 45230.12,
      "high": 45238.90,
      "low": 45225.45,
      "close": 45234.56,
      "volume": 8.76543,
      "volume_currency": 396789.34,
      "confirm": true
    }
  ],
  "pagination": {
    "has_more": true,
    "next_timestamp": "2024-08-15T10:43:00Z"
  }
}
```

**cURL 예시:**
```bash
# 최근 50개 1분 캔들 조회
curl "http://localhost:8000/api/v1/data/BTC-USDT/1m?limit=50"

# 특정 시간 범위 조회
curl "http://localhost:8000/api/v1/data/BTC-USDT/1H?start_time=2024-08-15T09:00:00Z&end_time=2024-08-15T10:00:00Z"
```

#### GET /data/{symbol}/latest
특정 심볼의 모든 시간프레임 최신 데이터를 조회합니다.

**Response (200):**
```json
{
  "symbol": "BTC-USDT",
  "timestamp": "2024-08-15T10:45:30Z",
  "latest_data": {
    "1m": {
      "timestamp": "2024-08-15T10:45:00Z",
      "open": 45234.56,
      "high": 45245.67,
      "low": 45220.34,
      "close": 45238.90,
      "volume": 12.34567,
      "confirm": true
    },
    "5m": {
      "timestamp": "2024-08-15T10:45:00Z",
      "open": 45200.12,
      "high": 45250.34,
      "low": 45195.67,
      "close": 45238.90,
      "volume": 67.89123,
      "confirm": false
    },
    "1H": {
      "timestamp": "2024-08-15T10:00:00Z",
      "open": 45150.00,
      "high": 45280.45,
      "low": 45120.78,
      "close": 45238.90,
      "volume": 234.56789,
      "confirm": false
    }
  }
}
```

### 4. 통계 및 분석

#### GET /statistics/{symbol}
특정 심볼의 통계 정보를 조회합니다.

**Query Parameters:**
- `period` (string): 통계 기간 (1h, 24h, 7d, 30d, 기본값: 24h)
- `timeframe` (string): 기준 시간프레임 (기본값: 1H)

**Response (200):**
```json
{
  "symbol": "BTC-USDT",
  "period": "24h",
  "timeframe": "1H",
  "statistics": {
    "total_candles": 24,
    "confirmed_candles": 23,
    "price_change": 234.56,
    "price_change_percent": 0.52,
    "volume_24h": 12345.67,
    "volume_currency_24h": 558234567.89,
    "high_24h": 45890.12,
    "low_24h": 44567.89,
    "vwap_24h": 45123.45,
    "first_timestamp": "2024-08-14T10:00:00Z",
    "last_timestamp": "2024-08-15T10:00:00Z"
  }
}
```

#### GET /market-overview
전체 마켓 개요를 조회합니다.

**Response (200):**
```json
{
  "timestamp": "2024-08-15T10:45:30Z",
  "total_symbols": 5,
  "market_summary": [
    {
      "symbol": "BTC-USDT",
      "price": 45238.90,
      "change_24h": 234.56,
      "change_percent_24h": 0.52,
      "volume_24h": 12345.67,
      "status": "active"
    },
    {
      "symbol": "ETH-USDT",
      "price": 2456.78,
      "change_24h": -12.34,
      "change_percent_24h": -0.50,
      "volume_24h": 5678.90,
      "status": "active"
    }
  ],
  "system_metrics": {
    "total_messages_24h": 2147483,
    "avg_processing_time_ms": 15.6,
    "error_rate_percent": 0.02,
    "uptime_percent": 99.95
  }
}
```

### 5. 시스템 관리

#### GET /health
시스템 헬스 체크를 수행합니다.

**Response (200) - 정상:**
```json
{
  "status": "healthy",
  "timestamp": "2024-08-15T10:45:30Z",
  "version": "1.0.0",
  "uptime_seconds": 86400,
  "checks": {
    "database": "healthy",
    "redis": "healthy", 
    "websocket_connections": "healthy",
    "message_queue": "healthy"
  }
}
```

**Response (503) - 비정상:**
```json
{
  "status": "unhealthy",
  "timestamp": "2024-08-15T10:45:30Z",
  "checks": {
    "database": "healthy",
    "redis": "unhealthy",
    "websocket_connections": "degraded",
    "message_queue": "unhealthy"
  },
  "errors": [
    "Redis connection timeout",
    "Message queue backlog too high"
  ]
}
```

#### GET /metrics
Prometheus 형식의 메트릭을 조회합니다.

**Response (200):**
```
# HELP okx_messages_total Total number of messages received
# TYPE okx_messages_total counter
okx_messages_total{symbol="BTC-USDT",timeframe="1m"} 15473

# HELP okx_processing_duration_seconds Time spent processing messages
# TYPE okx_processing_duration_seconds histogram
okx_processing_duration_seconds_bucket{le="0.1"} 10234
okx_processing_duration_seconds_bucket{le="0.5"} 12456
okx_processing_duration_seconds_sum 1234.56
okx_processing_duration_seconds_count 12456

# HELP okx_queue_length Current queue length
# TYPE okx_queue_length gauge
okx_queue_length{queue="candle_data"} 156
okx_queue_length{queue="dead_letter"} 3
```

## 🔧 에러 처리

### 표준 에러 응답 형식
```json
{
  "status": "error",
  "error_code": "INVALID_REQUEST",
  "message": "Human readable error message",
  "details": {
    "field": "Additional error details"
  },
  "timestamp": "2024-08-15T10:45:30Z",
  "request_id": "req_12345"
}
```

### 일반적인 HTTP 상태 코드
- **200**: 성공
- **400**: 잘못된 요청 (파라미터 오류)
- **401**: 인증 실패 (향후 사용)
- **404**: 리소스를 찾을 수 없음
- **429**: 요청 제한 초과
- **500**: 내부 서버 오류
- **503**: 서비스 사용 불가

### 에러 코드 목록
- `INVALID_REQUEST`: 잘못된 요청 형식
- `SYMBOL_NOT_FOUND`: 심볼을 찾을 수 없음
- `INVALID_TIMEFRAME`: 지원하지 않는 시간프레임
- `SUBSCRIPTION_EXISTS`: 이미 구독 중인 심볼
- `SUBSCRIPTION_NOT_FOUND`: 구독을 찾을 수 없음
- `RATE_LIMIT_EXCEEDED`: 요청 한도 초과
- `DATABASE_ERROR`: 데이터베이스 연결 오류
- `WEBSOCKET_ERROR`: WebSocket 연결 오류
- `SERVICE_UNAVAILABLE`: 서비스 일시 중단

## 🔒 보안 및 제한사항

### Rate Limiting
- **기본 제한**: IP당 분당 100 요청
- **데이터 조회**: IP당 분당 30 요청  
- **구독 요청**: IP당 시간당 10 요청

### 데이터 제한
- **최대 구독 심볼**: 클라이언트당 50개
- **최대 조회 레코드**: 요청당 1000개
- **히스토리 데이터**: 최대 30일

## 📝 사용 예시

### Python 클라이언트 예시
```python
import requests
import json

class OKXAPIClient:
    def __init__(self, base_url="http://localhost:8000/api/v1"):
        self.base_url = base_url
    
    def subscribe_symbols(self, symbols, timeframes):
        """심볼 구독"""
        response = requests.post(
            f"{self.base_url}/subscribe",
            json={
                "symbols": symbols,
                "timeframes": timeframes
            }
        )
        return response.json()
    
    def get_latest_data(self, symbol):
        """최신 데이터 조회"""
        response = requests.get(f"{self.base_url}/data/{symbol}/latest")
        return response.json()
    
    def get_candle_data(self, symbol, timeframe, limit=100):
        """캔들 데이터 조회"""
        response = requests.get(
            f"{self.base_url}/data/{symbol}/{timeframe}",
            params={"limit": limit}
        )
        return response.json()

# 사용 예시
client = OKXAPIClient()

# 구독 시작
result = client.subscribe_symbols(
    symbols=["BTC-USDT", "ETH-USDT"],
    timeframes=["1m", "5m", "1H"]
)
print(f"Subscription result: {result}")

# 최신 데이터 조회
latest = client.get_latest_data("BTC-USDT")
print(f"Latest BTC price: {latest['latest_data']['1m']['close']}")

# 히스토리 데이터 조회
candles = client.get_candle_data("BTC-USDT", "1H", limit=24)
print(f"Retrieved {candles['count']} hourly candles")
```

### JavaScript/Node.js 예시
```javascript
const axios = require('axios');

class OKXAPIClient {
    constructor(baseURL = 'http://localhost:8000/api/v1') {
        this.client = axios.create({ baseURL });
    }
    
    async subscribeSymbols(symbols, timeframes) {
        const response = await this.client.post('/subscribe', {
            symbols,
            timeframes
        });
        return response.data;
    }
    
    async getLatestData(symbol) {
        const response = await this.client.get(`/data/${symbol}/latest`);
        return response.data;
    }
    
    async getCandleData(symbol, timeframe, limit = 100) {
        const response = await this.client.get(`/data/${symbol}/${timeframe}`, {
            params: { limit }
        });
        return response.data;
    }
}

// 사용 예시
(async () => {
    const client = new OKXAPIClient();
    
    try {
        // 구독 시작
        const subscription = await client.subscribeSymbols(
            ['BTC-USDT', 'ETH-USDT'],
            ['1m', '5m', '1H']
        );
        console.log('Subscription result:', subscription);
        
        // 최신 데이터 조회
        const latest = await client.getLatestData('BTC-USDT');
        console.log('Latest BTC price:', latest.latest_data['1m'].close);
        
    } catch (error) {
        console.error('API Error:', error.response?.data || error.message);
    }
})();
```

이 API 문서를 통해 Claude Code가 OKX 실시간 캔들 데이터 수집 시스템과 효과적으로 상호작용할 수 있습니다. 모든 엔드포인트는 RESTful 원칙을 따르며, 명확한 에러 처리와 상태 코드를 제공합니다.
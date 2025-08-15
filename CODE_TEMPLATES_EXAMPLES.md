# 코드 템플릿 및 구현 예시

## 📋 개요

이 문서는 OKX 실시간 캔들 데이터 수집 시스템 구현을 위한 완전한 코드 템플릿, 설정 파일, 구현 예시를 제공합니다. Claude Code를 통해 즉시 사용 가능한 프로덕션 레벨의 코드를 포함합니다.

## 🏗️ 프로젝트 구조

```
okx-trading-system/
├── services/
│   ├── gateway/
│   │   ├── Dockerfile
│   │   ├── requirements.txt
│   │   ├── main.py
│   │   ├── app/
│   │   │   ├── __init__.py
│   │   │   ├── api/
│   │   │   │   ├── __init__.py
│   │   │   │   ├── routes.py
│   │   │   │   └── models.py
│   │   │   ├── core/
│   │   │   │   ├── __init__.py
│   │   │   │   ├── config.py
│   │   │   │   └── database.py
│   │   │   └── utils/
│   │   │       ├── __init__.py
│   │   │       └── redis_client.py
│   │   └── tests/
│   ├── collector/
│   │   ├── Dockerfile
│   │   ├── requirements.txt
│   │   ├── main.py
│   │   ├── app/
│   │   │   ├── __init__.py
│   │   │   ├── websocket/
│   │   │   │   ├── __init__.py
│   │   │   │   ├── client.py
│   │   │   │   └── handlers.py
│   │   │   ├── core/
│   │   │   │   ├── __init__.py
│   │   │   │   └── config.py
│   │   │   └── utils/
│   │   │       ├── __init__.py
│   │   │       ├── auth.py
│   │   │       └── reconnect.py
│   │   └── tests/
│   └── processor/
│       ├── Dockerfile
│       ├── requirements.txt
│       ├── main.py
│       ├── app/
│       │   ├── __init__.py
│       │   ├── processors/
│       │   │   ├── __init__.py
│       │   │   ├── batch.py
│       │   │   └── validator.py
│       │   ├── core/
│       │   │   ├── __init__.py
│       │   │   ├── config.py
│       │   │   └── database.py
│       │   └── utils/
│       │       ├── __init__.py
│       │       └── metrics.py
│       └── tests/
├── sql/
│   ├── init/
│   │   ├── 01_extensions.sql
│   │   ├── 02_schema.sql
│   │   ├── 03_functions.sql
│   │   └── 04_initial_data.sql
│   └── migrations/
├── config/
│   ├── postgresql.conf
│   ├── redis.conf
│   └── logging.conf
├── k8s/
├── monitoring/
├── tests/
├── docs/
├── scripts/
├── docker-compose.yml
├── docker-compose.dev.yml
├── requirements.txt
├── .env.example
├── .gitignore
└── README.md
```

## ⚙️ 핵심 서비스 구현

### 1. Gateway Service 구현

#### requirements.txt
```txt
# Gateway Service 의존성
fastapi==0.104.1
uvicorn[standard]==0.24.0
pydantic==2.5.0
pydantic-settings==2.1.0
asyncpg==0.29.0
redis[hiredis]==5.0.1
prometheus-client==0.19.0
python-multipart==0.0.6
python-jose[cryptography]==3.3.0
passlib[bcrypt]==1.7.4
python-dotenv==1.0.0
structlog==23.2.0
```

#### app/core/config.py
```python
# services/gateway/app/core/config.py
from pydantic_settings import BaseSettings
from typing import Optional, List
import os

class Settings(BaseSettings):
    # 앱 설정
    app_name: str = "OKX Gateway API"
    app_version: str = "1.0.0"
    environment: str = "development"
    debug: bool = False
    
    # 서버 설정
    host: str = "0.0.0.0"
    port: int = 8000
    workers: int = 1
    
    # 데이터베이스 설정
    db_host: str = "localhost"
    db_port: int = 5432
    db_name: str = "okx_trading_data"
    db_user: str = "postgres"
    db_password: str = "password"
    db_pool_size: int = 20
    db_pool_min_size: int = 5
    
    # Redis 설정
    redis_host: str = "localhost"
    redis_port: int = 6379
    redis_db: int = 0
    redis_password: Optional[str] = None
    redis_max_connections: int = 100
    
    # API 설정
    api_v1_prefix: str = "/api/v1"
    cors_origins: List[str] = ["*"]
    cors_methods: List[str] = ["*"]
    cors_headers: List[str] = ["*"]
    
    # 인증 설정 (향후 사용)
    secret_key: str = "your-secret-key-here"
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 30
    
    # 로깅 설정
    log_level: str = "INFO"
    log_format: str = "json"
    
    # 메트릭 설정
    metrics_enabled: bool = True
    metrics_port: int = 8080
    
    # 비즈니스 로직 설정
    max_symbols_per_subscription: int = 50
    max_timeframes_per_subscription: int = 10
    default_query_limit: int = 100
    max_query_limit: int = 1000
    
    @property
    def database_url(self) -> str:
        return f"postgresql://{self.db_user}:{self.db_password}@{self.db_host}:{self.db_port}/{self.db_name}"
    
    @property
    def redis_url(self) -> str:
        if self.redis_password:
            return f"redis://:{self.redis_password}@{self.redis_host}:{self.redis_port}/{self.redis_db}"
        return f"redis://{self.redis_host}:{self.redis_port}/{self.redis_db}"
    
    class Config:
        env_file = ".env"
        case_sensitive = False

# 전역 설정 인스턴스
settings = Settings()
```

#### app/core/database.py
```python
# services/gateway/app/core/database.py
import asyncpg
from typing import Optional
import logging
from .config import settings

logger = logging.getLogger(__name__)

class DatabaseManager:
    def __init__(self):
        self.pool: Optional[asyncpg.Pool] = None
    
    async def initialize(self):
        """데이터베이스 연결 풀 초기화"""
        try:
            self.pool = await asyncpg.create_pool(
                host=settings.db_host,
                port=settings.db_port,
                database=settings.db_name,
                user=settings.db_user,
                password=settings.db_password,
                min_size=settings.db_pool_min_size,
                max_size=settings.db_pool_size,
                command_timeout=60,
                server_settings={
                    'application_name': 'okx_gateway',
                    'timezone': 'UTC',
                }
            )
            logger.info("데이터베이스 연결 풀이 초기화되었습니다.")
        except Exception as e:
            logger.error(f"데이터베이스 연결 풀 초기화 실패: {e}")
            raise
    
    async def close(self):
        """데이터베이스 연결 풀 종료"""
        if self.pool:
            await self.pool.close()
            logger.info("데이터베이스 연결 풀이 종료되었습니다.")
    
    async def health_check(self) -> bool:
        """데이터베이스 연결 상태 확인"""
        try:
            async with self.pool.acquire() as conn:
                await conn.fetchval("SELECT 1")
            return True
        except Exception as e:
            logger.error(f"데이터베이스 헬스체크 실패: {e}")
            return False
    
    async def get_symbols(self, active_only: bool = True):
        """활성 심볼 목록 조회"""
        query = """
            SELECT s.id, s.symbol, s.base_currency, s.quote_currency, 
                   s.instrument_type, s.status
            FROM symbols s
            WHERE ($1::boolean = false OR s.status = 'ACTIVE')
            ORDER BY s.symbol
        """
        async with self.pool.acquire() as conn:
            return await conn.fetch(query, active_only)
    
    async def get_timeframes(self, active_only: bool = True):
        """활성 시간프레임 목록 조회"""
        query = """
            SELECT tf.id, tf.name, tf.display_name, tf.seconds, tf.sort_order
            FROM timeframes tf
            WHERE ($1::boolean = false OR tf.is_active = true)
            ORDER BY tf.sort_order
        """
        async with self.pool.acquire() as conn:
            return await conn.fetch(query, active_only)
    
    async def get_candle_data(self, symbol: str, timeframe: str, 
                             limit: int = 100, start_time=None, end_time=None):
        """캔들스틱 데이터 조회"""
        query = """
            SELECT cd.timestamp, cd.open_price, cd.high_price, cd.low_price,
                   cd.close_price, cd.volume, cd.volume_currency, cd.confirm,
                   cd.trade_count, cd.vwap
            FROM candlestick_data cd
            JOIN symbols s ON cd.symbol_id = s.id
            JOIN timeframes tf ON cd.timeframe_id = tf.id
            WHERE s.symbol = $1 AND tf.name = $2
            AND ($3::timestamp IS NULL OR cd.timestamp >= $3)
            AND ($4::timestamp IS NULL OR cd.timestamp <= $4)
            ORDER BY cd.timestamp DESC
            LIMIT $5
        """
        async with self.pool.acquire() as conn:
            return await conn.fetch(query, symbol, timeframe, start_time, end_time, limit)

# 전역 데이터베이스 매니저 인스턴스
db_manager = DatabaseManager()
```

#### app/utils/redis_client.py
```python
# services/gateway/app/utils/redis_client.py
import redis.asyncio as redis
import json
import logging
from typing import Optional, Dict, Any, List
from ..core.config import settings

logger = logging.getLogger(__name__)

class RedisManager:
    def __init__(self):
        self.redis: Optional[redis.Redis] = None
    
    async def initialize(self):
        """Redis 연결 초기화"""
        try:
            self.redis = await redis.from_url(
                settings.redis_url,
                max_connections=settings.redis_max_connections,
                decode_responses=True,
                health_check_interval=30
            )
            # 연결 테스트
            await self.redis.ping()
            logger.info("Redis 연결이 초기화되었습니다.")
        except Exception as e:
            logger.error(f"Redis 연결 초기화 실패: {e}")
            raise
    
    async def close(self):
        """Redis 연결 종료"""
        if self.redis:
            await self.redis.close()
            logger.info("Redis 연결이 종료되었습니다.")
    
    async def health_check(self) -> bool:
        """Redis 연결 상태 확인"""
        try:
            await self.redis.ping()
            return True
        except Exception as e:
            logger.error(f"Redis 헬스체크 실패: {e}")
            return False
    
    async def publish_subscription(self, symbol: str, config: Dict[str, Any]):
        """구독 요청을 컬렉터에 발행"""
        try:
            channel = f"collector:{symbol}"
            message = json.dumps(config)
            await self.redis.publish(channel, message)
            logger.info(f"구독 요청 발행: {symbol}")
        except Exception as e:
            logger.error(f"구독 요청 발행 실패 - {symbol}: {e}")
            raise
    
    async def set_subscription(self, symbol: str, config: Dict[str, Any], ttl: int = 3600):
        """구독 설정 저장"""
        try:
            key = f"subscription:{symbol}"
            value = json.dumps(config)
            await self.redis.setex(key, ttl, value)
        except Exception as e:
            logger.error(f"구독 설정 저장 실패 - {symbol}: {e}")
            raise
    
    async def get_subscription(self, symbol: str) -> Optional[Dict[str, Any]]:
        """구독 설정 조회"""
        try:
            key = f"subscription:{symbol}"
            value = await self.redis.get(key)
            if value:
                return json.loads(value)
            return None
        except Exception as e:
            logger.error(f"구독 설정 조회 실패 - {symbol}: {e}")
            return None
    
    async def delete_subscription(self, symbol: str):
        """구독 설정 삭제"""
        try:
            key = f"subscription:{symbol}"
            await self.redis.delete(key)
            # 구독 중지 신호 발송
            stop_config = {"action": "unsubscribe", "symbol": symbol}
            await self.publish_subscription(symbol, stop_config)
        except Exception as e:
            logger.error(f"구독 설정 삭제 실패 - {symbol}: {e}")
            raise
    
    async def get_all_subscriptions(self) -> List[Dict[str, Any]]:
        """모든 구독 설정 조회"""
        try:
            pattern = "subscription:*"
            keys = await self.redis.keys(pattern)
            
            subscriptions = []
            for key in keys:
                symbol = key.split(":", 1)[1]
                value = await self.redis.get(key)
                if value:
                    config = json.loads(value)
                    config["symbol"] = symbol
                    subscriptions.append(config)
            
            return subscriptions
        except Exception as e:
            logger.error(f"전체 구독 조회 실패: {e}")
            return []
    
    async def get_status(self, symbol: str) -> Optional[Dict[str, Any]]:
        """심볼 상태 조회"""
        try:
            key = f"status:{symbol}"
            value = await self.redis.get(key)
            if value:
                return json.loads(value)
            return None
        except Exception as e:
            logger.error(f"상태 조회 실패 - {symbol}: {e}")
            return None
    
    async def get_metrics(self) -> Dict[str, Any]:
        """시스템 메트릭 조회"""
        try:
            metrics = {}
            
            # 큐 길이 확인
            metrics["queue_length"] = await self.redis.llen("candle_data_queue")
            metrics["dlq_length"] = await self.redis.llen("dead_letter_queue")
            
            # 프로세서 메트릭
            processor_metrics = await self.redis.get("processor_metrics")
            if processor_metrics:
                metrics.update(json.loads(processor_metrics))
            
            # 활성 구독 수
            subscription_keys = await self.redis.keys("subscription:*")
            metrics["active_subscriptions"] = len(subscription_keys)
            
            return metrics
        except Exception as e:
            logger.error(f"메트릭 조회 실패: {e}")
            return {}

# 전역 Redis 매니저 인스턴스
redis_manager = RedisManager()
```

#### app/api/models.py
```python
# services/gateway/app/api/models.py
from pydantic import BaseModel, Field, validator
from typing import List, Optional, Dict, Any
from datetime import datetime
from enum import Enum

class SubscriptionRequest(BaseModel):
    symbols: List[str] = Field(..., min_items=1, max_items=50, description="구독할 심볼 목록")
    timeframes: List[str] = Field(..., min_items=1, max_items=10, description="시간프레임 목록")
    webhook_url: Optional[str] = Field(None, description="웹훅 URL (선택사항)")
    
    @validator('symbols')
    def validate_symbols(cls, v):
        for symbol in v:
            if not symbol or len(symbol.strip()) == 0:
                raise ValueError("빈 심볼은 허용되지 않습니다")
            if not symbol.replace('-', '').replace('_', '').isalnum():
                raise ValueError(f"잘못된 심볼 형식: {symbol}")
        return [s.strip().upper() for s in v]
    
    @validator('timeframes')
    def validate_timeframes(cls, v):
        valid_timeframes = {'1m', '3m', '5m', '15m', '30m', '1H', '2H', '4H', '6H', '12H', '1D', '1W', '1M'}
        for tf in v:
            if tf not in valid_timeframes:
                raise ValueError(f"지원하지 않는 시간프레임: {tf}")
        return v

class SubscriptionResponse(BaseModel):
    status: str
    message: str
    symbols: List[str]
    subscription_id: Optional[str] = None
    created_at: datetime

class UnsubscribeResponse(BaseModel):
    status: str
    message: str
    symbol: str
    stopped_at: datetime

class SymbolStatus(BaseModel):
    symbol: str
    status: str
    last_update: datetime
    timeframes: List[str]
    statistics: Optional[Dict[str, Any]] = None
    connection_info: Optional[Dict[str, Any]] = None

class CandleData(BaseModel):
    timestamp: datetime
    open: float = Field(alias="open_price")
    high: float = Field(alias="high_price") 
    low: float = Field(alias="low_price")
    close: float = Field(alias="close_price")
    volume: float
    volume_currency: Optional[float] = None
    confirm: bool = False
    trade_count: Optional[int] = None
    vwap: Optional[float] = None

class CandleDataResponse(BaseModel):
    symbol: str
    timeframe: str
    count: int
    data: List[CandleData]
    pagination: Optional[Dict[str, Any]] = None

class SystemStatus(BaseModel):
    system_status: str
    timestamp: datetime
    services: Dict[str, Any]
    metrics: Dict[str, Any]
    symbols: List[Dict[str, Any]]

class HealthResponse(BaseModel):
    status: str
    timestamp: datetime
    version: str
    uptime_seconds: Optional[int] = None
    checks: Dict[str, str]
    errors: Optional[List[str]] = None

class ErrorResponse(BaseModel):
    status: str = "error"
    error_code: str
    message: str
    details: Optional[Dict[str, Any]] = None
    timestamp: datetime
    request_id: Optional[str] = None

class StatisticsResponse(BaseModel):
    symbol: str
    period: str
    timeframe: str
    statistics: Dict[str, Any]

class MarketOverviewResponse(BaseModel):
    timestamp: datetime
    total_symbols: int
    market_summary: List[Dict[str, Any]]
    system_metrics: Dict[str, Any]

class SortOrder(str, Enum):
    ASC = "asc"
    DESC = "desc"

class QueryParams(BaseModel):
    limit: int = Field(default=100, ge=1, le=1000, description="조회할 레코드 수")
    start_time: Optional[datetime] = Field(None, description="시작 시간")
    end_time: Optional[datetime] = Field(None, description="종료 시간")
    sort: SortOrder = Field(default=SortOrder.DESC, description="정렬 순서")
```

#### app/api/routes.py
```python
# services/gateway/app/api/routes.py
from fastapi import APIRouter, HTTPException, Depends, Query, Path, status
from fastapi.responses import PlainTextResponse
from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta
import uuid
import logging

from ..core.database import db_manager
from ..utils.redis_client import redis_manager
from .models import *

logger = logging.getLogger(__name__)
router = APIRouter()

# 의존성 함수들
async def get_db():
    return db_manager

async def get_redis():
    return redis_manager

def generate_request_id():
    return str(uuid.uuid4())[:8]

# 구독 관리 엔드포인트
@router.post("/subscribe", response_model=SubscriptionResponse, status_code=status.HTTP_201_CREATED)
async def subscribe_to_symbols(
    request: SubscriptionRequest,
    db=Depends(get_db),
    redis=Depends(get_redis)
):
    """심볼과 시간프레임 구독 시작"""
    request_id = generate_request_id()
    
    try:
        # 심볼 유효성 검사
        valid_symbols = await db.get_symbols(active_only=True)
        valid_symbol_names = {s['symbol'] for s in valid_symbols}
        
        invalid_symbols = [s for s in request.symbols if s not in valid_symbol_names]
        if invalid_symbols:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "error_code": "INVALID_SYMBOLS",
                    "message": "잘못된 심볼이 포함되어 있습니다",
                    "invalid_symbols": invalid_symbols,
                    "request_id": request_id
                }
            )
        
        # 시간프레임 유효성 검사
        valid_timeframes = await db.get_timeframes(active_only=True)
        valid_tf_names = {tf['name'] for tf in valid_timeframes}
        
        invalid_timeframes = [tf for tf in request.timeframes if tf not in valid_tf_names]
        if invalid_timeframes:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "error_code": "INVALID_TIMEFRAMES",
                    "message": "잘못된 시간프레임이 포함되어 있습니다",
                    "invalid_timeframes": invalid_timeframes,
                    "request_id": request_id
                }
            )
        
        # 구독 설정 생성
        subscription_config = {
            "action": "subscribe",
            "symbols": request.symbols,
            "timeframes": request.timeframes,
            "webhook_url": request.webhook_url,
            "created_at": datetime.utcnow().isoformat(),
            "request_id": request_id
        }
        
        # 각 심볼별로 구독 설정 저장 및 신호 발송
        for symbol in request.symbols:
            await redis.set_subscription(symbol, subscription_config)
            await redis.publish_subscription(symbol, subscription_config)
        
        logger.info(f"구독 생성 완료: {request.symbols} - {request_id}")
        
        return SubscriptionResponse(
            status="success",
            message=f"Subscribed to {len(request.symbols)} symbols",
            symbols=request.symbols,
            subscription_id=request_id,
            created_at=datetime.utcnow()
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"구독 생성 실패: {e} - {request_id}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "error_code": "SUBSCRIPTION_FAILED",
                "message": "구독 생성 중 오류가 발생했습니다",
                "request_id": request_id
            }
        )

@router.delete("/subscribe/{symbol}", response_model=UnsubscribeResponse)
async def unsubscribe_from_symbol(
    symbol: str = Path(..., description="구독 취소할 심볼"),
    redis=Depends(get_redis)
):
    """특정 심볼의 구독 취소"""
    request_id = generate_request_id()
    
    try:
        # 기존 구독 확인
        existing_subscription = await redis.get_subscription(symbol)
        if not existing_subscription:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={
                    "error_code": "SUBSCRIPTION_NOT_FOUND",
                    "message": f"심볼 {symbol}의 구독을 찾을 수 없습니다",
                    "request_id": request_id
                }
            )
        
        # 구독 삭제
        await redis.delete_subscription(symbol)
        
        logger.info(f"구독 취소 완료: {symbol} - {request_id}")
        
        return UnsubscribeResponse(
            status="success",
            message=f"Unsubscribed from {symbol}",
            symbol=symbol,
            stopped_at=datetime.utcnow()
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"구독 취소 실패: {e} - {request_id}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "error_code": "UNSUBSCRIBE_FAILED",
                "message": "구독 취소 중 오류가 발생했습니다",
                "request_id": request_id
            }
        )

@router.get("/subscriptions")
async def get_all_subscriptions(redis=Depends(get_redis)):
    """현재 활성 구독 목록 조회"""
    try:
        subscriptions = await redis.get_all_subscriptions()
        
        # 각 구독의 상태 정보 추가
        for sub in subscriptions:
            symbol = sub.get("symbol")
            if symbol:
                status_info = await redis.get_status(symbol)
                if status_info:
                    sub.update({
                        "status": status_info.get("status", "unknown"),
                        "last_message": status_info.get("last_update")
                    })
        
        return {
            "status": "success",
            "total": len(subscriptions),
            "subscriptions": subscriptions
        }
        
    except Exception as e:
        logger.error(f"구독 목록 조회 실패: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "error_code": "SUBSCRIPTIONS_QUERY_FAILED",
                "message": "구독 목록 조회 중 오류가 발생했습니다"
            }
        )

# 상태 모니터링 엔드포인트
@router.get("/status/{symbol}", response_model=SymbolStatus)
async def get_symbol_status(
    symbol: str = Path(..., description="조회할 심볼"),
    redis=Depends(get_redis)
):
    """특정 심볼의 수집 상태 조회"""
    try:
        status_info = await redis.get_status(symbol)
        
        if not status_info:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={
                    "error_code": "SYMBOL_NOT_FOUND",
                    "message": f"심볼 {symbol}의 상태를 찾을 수 없습니다"
                }
            )
        
        # 구독 정보 추가
        subscription_info = await redis.get_subscription(symbol)
        timeframes = subscription_info.get("timeframes", []) if subscription_info else []
        
        return SymbolStatus(
            symbol=symbol,
            status=status_info.get("status", "unknown"),
            last_update=datetime.fromisoformat(status_info.get("last_update")),
            timeframes=timeframes,
            statistics=status_info.get("statistics"),
            connection_info=status_info.get("connection_info")
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"심볼 상태 조회 실패: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "error_code": "STATUS_QUERY_FAILED",
                "message": "상태 조회 중 오류가 발생했습니다"
            }
        )

@router.get("/status", response_model=SystemStatus)
async def get_system_status(
    db=Depends(get_db),
    redis=Depends(get_redis)
):
    """전체 시스템 상태 조회"""
    try:
        # 서비스 상태 확인
        db_healthy = await db.health_check()
        redis_healthy = await redis.health_check()
        
        services = {
            "gateway": "healthy",
            "database": "healthy" if db_healthy else "unhealthy",
            "redis": "healthy" if redis_healthy else "unhealthy"
        }
        
        # 시스템 메트릭 수집
        metrics = await redis.get_metrics()
        
        # 심볼별 상태 수집
        subscriptions = await redis.get_all_subscriptions()
        symbol_statuses = []
        
        for sub in subscriptions:
            symbol = sub.get("symbol")
            if symbol:
                status_info = await redis.get_status(symbol)
                if status_info:
                    symbol_statuses.append({
                        "symbol": symbol,
                        "status": status_info.get("status", "unknown"),
                        "last_message": status_info.get("last_update")
                    })
        
        # 전체 시스템 상태 결정
        system_status = "healthy"
        if not db_healthy or not redis_healthy:
            system_status = "unhealthy"
        elif len([s for s in symbol_statuses if s["status"] != "connected"]) > 0:
            system_status = "degraded"
        
        return SystemStatus(
            system_status=system_status,
            timestamp=datetime.utcnow(),
            services=services,
            metrics=metrics,
            symbols=symbol_statuses
        )
        
    except Exception as e:
        logger.error(f"시스템 상태 조회 실패: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "error_code": "SYSTEM_STATUS_FAILED",
                "message": "시스템 상태 조회 중 오류가 발생했습니다"
            }
        )

# 데이터 조회 엔드포인트
@router.get("/data/{symbol}/{timeframe}", response_model=CandleDataResponse)
async def get_candle_data(
    symbol: str = Path(..., description="조회할 심볼"),
    timeframe: str = Path(..., description="시간프레임"),
    limit: int = Query(default=100, ge=1, le=1000, description="조회할 레코드 수"),
    start_time: Optional[datetime] = Query(None, description="시작 시간"),
    end_time: Optional[datetime] = Query(None, description="종료 시간"),
    sort: SortOrder = Query(default=SortOrder.DESC, description="정렬 순서"),
    db=Depends(get_db)
):
    """특정 심볼과 시간프레임의 캔들 데이터 조회"""
    try:
        # 심볼과 시간프레임 유효성 검사는 DB 쿼리에서 자연스럽게 처리됨
        raw_data = await db.get_candle_data(symbol, timeframe, limit, start_time, end_time)
        
        if not raw_data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={
                    "error_code": "NO_DATA_FOUND",
                    "message": f"{symbol} {timeframe} 데이터를 찾을 수 없습니다"
                }
            )
        
        # 데이터 정렬 (필요시)
        if sort == SortOrder.ASC:
            raw_data = list(reversed(raw_data))
        
        # 응답 모델로 변환
        candles = []
        for row in raw_data:
            candles.append(CandleData(
                timestamp=row['timestamp'],
                open_price=float(row['open_price']),
                high_price=float(row['high_price']),
                low_price=float(row['low_price']),
                close_price=float(row['close_price']),
                volume=float(row['volume']),
                volume_currency=float(row['volume_currency']) if row['volume_currency'] else None,
                confirm=row['confirm'],
                trade_count=row['trade_count'],
                vwap=float(row['vwap']) if row['vwap'] else None
            ))
        
        # 페이지네이션 정보
        pagination = None
        if len(candles) == limit:
            last_timestamp = candles[-1].timestamp
            pagination = {
                "has_more": True,
                "next_timestamp": last_timestamp.isoformat()
            }
        
        return CandleDataResponse(
            symbol=symbol,
            timeframe=timeframe,
            count=len(candles),
            data=candles,
            pagination=pagination
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"캔들 데이터 조회 실패: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "error_code": "DATA_QUERY_FAILED",
                "message": "데이터 조회 중 오류가 발생했습니다"
            }
        )

# 헬스체크 엔드포인트
@router.get("/health", response_model=HealthResponse)
async def health_check(
    db=Depends(get_db),
    redis=Depends(get_redis)
):
    """시스템 헬스체크"""
    start_time = datetime.utcnow()
    
    checks = {}
    errors = []
    
    # 데이터베이스 체크
    try:
        db_healthy = await db.health_check()
        checks["database"] = "healthy" if db_healthy else "unhealthy"
        if not db_healthy:
            errors.append("Database connection failed")
    except Exception as e:
        checks["database"] = "unhealthy"
        errors.append(f"Database error: {str(e)}")
    
    # Redis 체크
    try:
        redis_healthy = await redis.health_check()
        checks["redis"] = "healthy" if redis_healthy else "unhealthy" 
        if not redis_healthy:
            errors.append("Redis connection failed")
    except Exception as e:
        checks["redis"] = "unhealthy"
        errors.append(f"Redis error: {str(e)}")
    
    # 메시지 큐 체크
    try:
        metrics = await redis.get_metrics()
        queue_length = metrics.get("queue_length", 0)
        dlq_length = metrics.get("dlq_length", 0)
        
        if queue_length > 50000:  # 높은 임계값
            checks["message_queue"] = "degraded"
            errors.append(f"High queue length: {queue_length}")
        elif dlq_length > 1000:  # DLQ 임계값
            checks["message_queue"] = "degraded"
            errors.append(f"High DLQ length: {dlq_length}")
        else:
            checks["message_queue"] = "healthy"
    except Exception as e:
        checks["message_queue"] = "unhealthy"
        errors.append(f"Queue check error: {str(e)}")
    
    # 전체 상태 결정
    overall_status = "healthy"
    if any(status == "unhealthy" for status in checks.values()):
        overall_status = "unhealthy"
    elif any(status == "degraded" for status in checks.values()):
        overall_status = "degraded"
    
    response_status = status.HTTP_200_OK if overall_status == "healthy" else status.HTTP_503_SERVICE_UNAVAILABLE
    
    return HealthResponse(
        status=overall_status,
        timestamp=datetime.utcnow(),
        version="1.0.0",
        uptime_seconds=None,  # 실제 구현에서는 시작 시간 추적
        checks=checks,
        errors=errors if errors else None
    )

@router.get("/metrics", response_class=PlainTextResponse)
async def get_prometheus_metrics(redis=Depends(get_redis)):
    """Prometheus 형식의 메트릭 조회"""
    try:
        metrics = await redis.get_metrics()
        
        prometheus_metrics = []
        
        # 큐 길이 메트릭
        queue_length = metrics.get("queue_length", 0)
        dlq_length = metrics.get("dlq_length", 0)
        
        prometheus_metrics.extend([
            "# HELP okx_queue_length Current queue length",
            "# TYPE okx_queue_length gauge",
            f'okx_queue_length{{queue="candle_data"}} {queue_length}',
            f'okx_queue_length{{queue="dead_letter"}} {dlq_length}',
            "",
            "# HELP okx_active_subscriptions Number of active subscriptions",
            "# TYPE okx_active_subscriptions gauge",
            f'okx_active_subscriptions {metrics.get("active_subscriptions", 0)}',
        ])
        
        return "\n".join(prometheus_metrics)
        
    except Exception as e:
        logger.error(f"메트릭 조회 실패: {e}")
        return "# Error retrieving metrics"
```

#### main.py
```python
# services/gateway/main.py
import asyncio
import logging
import signal
import sys
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from prometheus_client import make_asgi_app
import structlog

from app.core.config import settings
from app.core.database import db_manager
from app.utils.redis_client import redis_manager
from app.api.routes import router as api_router
from app.api.models import ErrorResponse

# 로깅 설정
def setup_logging():
    if settings.log_format == "json":
        structlog.configure(
            processors=[
                structlog.stdlib.filter_by_level,
                structlog.stdlib.add_logger_name,
                structlog.stdlib.add_log_level,
                structlog.stdlib.PositionalArgumentsFormatter(),
                structlog.processors.TimeStamper(fmt="iso"),
                structlog.processors.StackInfoRenderer(),
                structlog.processors.format_exc_info,
                structlog.processors.JSONRenderer()
            ],
            context_class=dict,
            logger_factory=structlog.stdlib.LoggerFactory(),
            wrapper_class=structlog.stdlib.BoundLogger,
            cache_logger_on_first_use=True,
        )
    
    logging.basicConfig(
        level=getattr(logging, settings.log_level.upper()),
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )

setup_logging()
logger = logging.getLogger(__name__)

# 애플리케이션 생명주기 관리
@asynccontextmanager
async def lifespan(app: FastAPI):
    # 시작 시
    logger.info("🚀 OKX Gateway API 시작 중...")
    
    try:
        # 데이터베이스 연결 초기화
        await db_manager.initialize()
        
        # Redis 연결 초기화
        await redis_manager.initialize()
        
        logger.info("✅ 모든 서비스 초기화 완료")
        
    except Exception as e:
        logger.error(f"❌ 초기화 실패: {e}")
        raise
    
    yield
    
    # 종료 시
    logger.info("🛑 OKX Gateway API 종료 중...")
    
    try:
        await redis_manager.close()
        await db_manager.close()
        logger.info("✅ 모든 연결 종료 완료")
    except Exception as e:
        logger.error(f"❌ 종료 처리 실패: {e}")

# FastAPI 애플리케이션 생성
app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description="OKX 실시간 캔들 데이터 수집 시스템 Gateway API",
    lifespan=lifespan
)

# CORS 미들웨어 설정
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=settings.cors_methods,
    allow_headers=settings.cors_headers,
)

# 글로벌 예외 처리기
@app.exception_handler(HTTPException)
async def http_exception_handler(request, exc):
    return JSONResponse(
        status_code=exc.status_code,
        content=exc.detail if isinstance(exc.detail, dict) else {
            "error_code": "HTTP_ERROR",
            "message": str(exc.detail),
            "timestamp": structlog.get_logger().info("timestamp")
        }
    )

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request, exc):
    return JSONResponse(
        status_code=422,
        content={
            "error_code": "VALIDATION_ERROR",
            "message": "요청 데이터가 올바르지 않습니다",
            "details": exc.errors(),
            "timestamp": structlog.get_logger().info("timestamp")
        }
    )

@app.exception_handler(Exception)
async def general_exception_handler(request, exc):
    logger.error(f"예상치 못한 오류: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={
            "error_code": "INTERNAL_ERROR",
            "message": "내부 서버 오류가 발생했습니다",
            "timestamp": structlog.get_logger().info("timestamp")
        }
    )

# API 라우터 등록
app.include_router(
    api_router,
    prefix=settings.api_v1_prefix,
    tags=["OKX Trading API"]
)

# 루트 엔드포인트
@app.get("/", tags=["Root"])
async def root():
    return {
        "message": "OKX Trading System Gateway API",
        "version": settings.app_version,
        "environment": settings.environment,
        "docs_url": "/docs"
    }

# Prometheus 메트릭 엔드포인트 (별도 포트)
if settings.metrics_enabled:
    metrics_app = make_asgi_app()
    app.mount("/metrics", metrics_app)

# 프로덕션에서 실행될 때의 신호 처리
def signal_handler(signum, frame):
    logger.info(f"신호 {signum} 수신, 정상 종료 중...")
    sys.exit(0)

if __name__ == "__main__":
    # 개발 환경에서의 실행
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    uvicorn.run(
        "main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.debug,
        workers=settings.workers if not settings.debug else 1,
        log_level=settings.log_level.lower()
    )
```

#### Dockerfile
```dockerfile
# services/gateway/Dockerfile
FROM python:3.11-slim

# 메타데이터
LABEL maintainer="OKX Trading System"
LABEL version="1.0.0"
LABEL description="OKX Trading Gateway API Service"

# 환경 변수
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
ENV PIP_NO_CACHE_DIR=1
ENV PIP_DISABLE_PIP_VERSION_CHECK=1

# 시스템 패키지 업데이트 및 필수 패키지 설치
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    && rm -rf /var/lib/apt/lists/*

# 작업 디렉토리 설정
WORKDIR /app

# Python 의존성 설치
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 애플리케이션 코드 복사
COPY . .

# 비root 사용자 생성
RUN groupadd -r appuser && useradd -r -g appuser appuser
RUN chown -R appuser:appuser /app
USER appuser

# 헬스체크
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# 포트 노출
EXPOSE 8000 8080

# 애플리케이션 실행
CMD ["python", "main.py"]
```

### 2. Data Collector Service 구현

#### app/core/config.py
```python
# services/collector/app/core/config.py
from pydantic_settings import BaseSettings
from typing import Optional, List
import os

class Settings(BaseSettings):
    # 서비스 설정
    service_name: str = "OKX Data Collector"
    service_version: str = "1.0.0"
    environment: str = "development"
    debug: bool = False
    
    # OKX API 설정
    okx_api_key: str = ""
    okx_secret_key: str = ""
    okx_passphrase: str = ""
    okx_websocket_url: str = "wss://ws.okx.com:8443/ws/v5/public"
    okx_rest_api_url: str = "https://www.okx.com/api/v5"
    
    # Redis 설정
    redis_host: str = "localhost"
    redis_port: int = 6379
    redis_db: int = 0
    redis_password: Optional[str] = None
    redis_max_connections: int = 50
    
    # WebSocket 설정
    websocket_ping_interval: int = 20
    websocket_ping_timeout: int = 10
    websocket_close_timeout: int = 10
    
    # 재연결 설정
    initial_reconnect_delay: int = 5
    max_reconnect_delay: int = 300
    reconnect_backoff_factor: float = 1.5
    max_reconnect_attempts: int = -1  # -1은 무제한
    
    # 메시지 처리 설정
    message_queue_name: str = "candle_data_queue"
    dead_letter_queue_name: str = "dead_letter_queue"
    message_timeout: int = 30
    
    # 심볼 및 시간프레임 설정
    symbol: str = "BTC-USDT"  # 개별 컬렉터당 하나의 심볼
    default_timeframes: List[str] = ["1m", "5m", "15m", "1H", "1D"]
    
    # 로깅 설정
    log_level: str = "INFO"
    log_format: str = "json"
    
    # 메트릭 설정
    metrics_enabled: bool = True
    metrics_update_interval: int = 30
    
    @property
    def redis_url(self) -> str:
        if self.redis_password:
            return f"redis://:{self.redis_password}@{self.redis_host}:{self.redis_port}/{self.redis_db}"
        return f"redis://{self.redis_host}:{self.redis_port}/{self.redis_db}"
    
    class Config:
        env_file = ".env"
        case_sensitive = False

settings = Settings()
```

#### app/websocket/client.py
```python
# services/collector/app/websocket/client.py
import asyncio
import json
import logging
import websockets
import hmac
import hashlib
import base64
from datetime import datetime
from typing import Dict, List, Optional, Callable
import redis.asyncio as redis

from ..core.config import settings

logger = logging.getLogger(__name__)

class OKXWebSocketClient:
    def __init__(self, symbol: str):
        self.symbol = symbol
        self.websocket: Optional[websockets.WebSocketServerProtocol] = None
        self.redis_client: Optional[redis.Redis] = None
        self.is_running = False
        self.is_connected = False
        
        # 재연결 설정
        self.reconnect_delay = settings.initial_reconnect_delay
        self.reconnect_attempts = 0
        
        # 구독 상태
        self.current_timeframes: List[str] = []
        self.subscription_id: Optional[str] = None
        
        # 통계
        self.stats = {
            "messages_received": 0,
            "messages_processed": 0,
            "messages_failed": 0,
            "last_message_time": None,
            "connection_start_time": None,
            "reconnect_count": 0
        }
    
    async def initialize(self):
        """클라이언트 초기화"""
        try:
            # Redis 연결 초기화
            self.redis_client = await redis.from_url(
                settings.redis_url,
                max_connections=settings.redis_max_connections,
                decode_responses=True
            )
            
            # 연결 테스트
            await self.redis_client.ping()
            logger.info(f"Redis 연결 초기화 완료: {self.symbol}")
            
            # 구독 요청 리스너 시작
            asyncio.create_task(self.listen_for_subscriptions())
            
        except Exception as e:
            logger.error(f"클라이언트 초기화 실패: {e}")
            raise
    
    async def listen_for_subscriptions(self):
        """Gateway로부터 구독 요청 수신"""
        pubsub = self.redis_client.pubsub()
        channel = f"collector:{self.symbol}"
        
        try:
            await pubsub.subscribe(channel)
            logger.info(f"구독 채널 리스닝 시작: {channel}")
            
            async for message in pubsub.listen():
                if message['type'] == 'message':
                    try:
                        config = json.loads(message['data'])
                        action = config.get('action')
                        
                        if action == 'subscribe':
                            await self.handle_subscribe_request(config)
                        elif action == 'unsubscribe':
                            await self.handle_unsubscribe_request()
                            
                    except Exception as e:
                        logger.error(f"구독 요청 처리 실패: {e}")
                        
        except Exception as e:
            logger.error(f"구독 리스너 오류: {e}")
            # 재시작 로직
            await asyncio.sleep(5)
            asyncio.create_task(self.listen_for_subscriptions())
    
    async def handle_subscribe_request(self, config: Dict):
        """구독 요청 처리"""
        try:
            symbols = config.get('symbols', [])
            if self.symbol not in symbols:
                return
            
            new_timeframes = config.get('timeframes', settings.default_timeframes)
            self.subscription_id = config.get('request_id')
            
            # 이미 연결되어 있고 같은 시간프레임이면 무시
            if (self.is_connected and 
                set(new_timeframes) == set(self.current_timeframes)):
                logger.info(f"동일한 구독 요청 무시: {self.symbol}")
                return
            
            # 새로운 구독 시작
            self.current_timeframes = new_timeframes
            
            if not self.is_running:
                self.is_running = True
                asyncio.create_task(self.start_connection_loop())
                
            logger.info(f"구독 시작: {self.symbol} - {new_timeframes}")
            
        except Exception as e:
            logger.error(f"구독 요청 처리 오류: {e}")
    
    async def handle_unsubscribe_request(self):
        """구독 취소 처리"""
        try:
            self.is_running = False
            
            if self.websocket and not self.websocket.closed:
                await self.websocket.close()
            
            await self.update_status("disconnected", "unsubscribed by request")
            logger.info(f"구독 취소 완료: {self.symbol}")
            
        except Exception as e:
            logger.error(f"구독 취소 처리 오류: {e}")
    
    async def start_connection_loop(self):
        """WebSocket 연결 루프"""
        while self.is_running:
            try:
                await self.connect_and_collect()
                
            except Exception as e:
                logger.error(f"연결 오류: {self.symbol} - {e}")
                await self.handle_connection_error()
            
            if self.is_running:
                await asyncio.sleep(self.reconnect_delay)
    
    async def connect_and_collect(self):
        """WebSocket 연결 및 데이터 수집"""
        try:
            logger.info(f"WebSocket 연결 시작: {self.symbol}")
            
            async with websockets.connect(
                settings.okx_websocket_url,
                ping_interval=settings.websocket_ping_interval,
                ping_timeout=settings.websocket_ping_timeout,
                close_timeout=settings.websocket_close_timeout
            ) as websocket:
                
                self.websocket = websocket
                self.is_connected = True
                self.stats["connection_start_time"] = datetime.utcnow().isoformat()
                
                # 구독 메시지 전송
                await self.send_subscription_message()
                
                # 상태 업데이트
                await self.update_status("connected")
                
                # 재연결 설정 초기화
                self.reconnect_delay = settings.initial_reconnect_delay
                self.reconnect_attempts = 0
                
                logger.info(f"WebSocket 연결 성공: {self.symbol}")
                
                # 메시지 수신 루프
                async for message in websocket:
                    await self.process_message(json.loads(message))
                    
        except websockets.exceptions.ConnectionClosed as e:
            logger.warning(f"WebSocket 연결 종료: {self.symbol} - {e}")
            self.is_connected = False
            raise
            
        except Exception as e:
            logger.error(f"WebSocket 연결 실패: {self.symbol} - {e}")
            self.is_connected = False
            raise
    
    async def send_subscription_message(self):
        """구독 메시지 전송"""
        try:
            subscription_args = []
            for timeframe in self.current_timeframes:
                subscription_args.append({
                    "channel": f"candle{timeframe}",
                    "instId": self.symbol
                })
            
            subscribe_msg = {
                "op": "subscribe",
                "args": subscription_args
            }
            
            await self.websocket.send(json.dumps(subscribe_msg))
            logger.info(f"구독 메시지 전송: {self.symbol} - {self.current_timeframes}")
            
        except Exception as e:
            logger.error(f"구독 메시지 전송 실패: {e}")
            raise
    
    async def process_message(self, data: Dict):
        """수신된 메시지 처리"""
        try:
            self.stats["messages_received"] += 1
            self.stats["last_message_time"] = datetime.utcnow().isoformat()
            
            # 메시지 타입 확인
            if 'event' in data:
                await self.handle_event_message(data)
                return
            
            if 'data' not in data:
                return
            
            # 캔들 데이터 처리
            for candle_data in data['data']:
                await self.process_candle_data(candle_data, data.get('arg', {}))
                
            self.stats["messages_processed"] += 1
            
        except Exception as e:
            self.stats["messages_failed"] += 1
            logger.error(f"메시지 처리 실패: {e} - {data}")
    
    async def handle_event_message(self, data: Dict):
        """이벤트 메시지 처리"""
        event = data.get('event')
        
        if event == 'subscribe':
            if data.get('code') == '0':
                logger.info(f"구독 성공: {self.symbol}")
            else:
                logger.error(f"구독 실패: {data}")
                
        elif event == 'error':
            logger.error(f"서버 오류: {data}")
    
    async def process_candle_data(self, candle_data: List, channel_info: Dict):
        """캔들 데이터 처리 및 Redis 큐 전송"""
        try:
            # OKX 캔들 데이터 형식:
            # [timestamp, open, high, low, close, volume, volume_currency, confirm, trade_count]
            
            timeframe = channel_info.get('channel', '').replace('candle', '')
            
            processed_data = {
                "symbol": self.symbol,
                "timeframe": timeframe,
                "timestamp": int(candle_data[0]),
                "open": float(candle_data[1]),
                "high": float(candle_data[2]),
                "low": float(candle_data[3]),
                "close": float(candle_data[4]),
                "volume": float(candle_data[5]),
                "volume_currency": float(candle_data[6]),
                "confirm": candle_data[8] == "1",
                "trade_count": int(candle_data[7]) if len(candle_data) > 7 else 0,
                "received_at": datetime.utcnow().isoformat(),
                "collector_id": self.subscription_id,
                "raw_data": candle_data
            }
            
            # Redis 큐에 전송
            await self.redis_client.lpush(
                settings.message_queue_name,
                json.dumps(processed_data)
            )
            
            # 디버그 로그 (개발환경에서만)
            if settings.debug:
                logger.debug(f"캔들 데이터 큐 전송: {self.symbol} {timeframe} {processed_data['close']}")
            
        except Exception as e:
            logger.error(f"캔들 데이터 처리 실패: {e}")
            raise
    
    async def handle_connection_error(self):
        """연결 오류 처리"""
        self.is_connected = False
        self.reconnect_attempts += 1
        self.stats["reconnect_count"] += 1
        
        # 지수 백오프 적용
        self.reconnect_delay = min(
            self.reconnect_delay * settings.reconnect_backoff_factor,
            settings.max_reconnect_delay
        )
        
        await self.update_status(
            "disconnected", 
            f"reconnection attempt {self.reconnect_attempts}"
        )
        
        logger.warning(
            f"재연결 대기: {self.symbol} - "
            f"시도 {self.reconnect_attempts}, 지연 {self.reconnect_delay}초"
        )
    
    async def update_status(self, status: str, message: str = ""):
        """상태 정보 업데이트"""
        try:
            status_data = {
                "symbol": self.symbol,
                "status": status,
                "message": message,
                "last_update": datetime.utcnow().isoformat(),
                "timeframes": self.current_timeframes,
                "subscription_id": self.subscription_id,
                "statistics": self.stats.copy(),
                "connection_info": {
                    "websocket_connected": self.is_connected,
                    "reconnect_attempts": self.reconnect_attempts,
                    "current_delay": self.reconnect_delay
                }
            }
            
            await self.redis_client.setex(
                f"status:{self.symbol}",
                300,  # 5분 TTL
                json.dumps(status_data)
            )
            
        except Exception as e:
            logger.error(f"상태 업데이트 실패: {e}")
    
    async def close(self):
        """클라이언트 종료"""
        logger.info(f"클라이언트 종료: {self.symbol}")
        
        self.is_running = False
        
        if self.websocket and not self.websocket.closed:
            await self.websocket.close()
        
        if self.redis_client:
            await self.redis_client.close()
        
        await self.update_status("stopped")
```

#### main.py
```python
# services/collector/main.py
import asyncio
import logging
import signal
import sys
import os

from app.core.config import settings
from app.websocket.client import OKXWebSocketClient

# 로깅 설정
logging.basicConfig(
    level=getattr(logging, settings.log_level.upper()),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)

logger = logging.getLogger(__name__)

# 전역 클라이언트 인스턴스
client: OKXWebSocketClient = None

async def main():
    global client
    
    logger.info(f"🚀 OKX Data Collector 시작: {settings.symbol}")
    
    try:
        # WebSocket 클라이언트 초기화
        client = OKXWebSocketClient(settings.symbol)
        await client.initialize()
        
        logger.info(f"✅ 클라이언트 초기화 완료: {settings.symbol}")
        
        # 무한 실행
        while True:
            await asyncio.sleep(1)
            
    except KeyboardInterrupt:
        logger.info("키보드 인터럽트 수신")
    except Exception as e:
        logger.error(f"예상치 못한 오류: {e}")
        raise
    finally:
        if client:
            await client.close()
        logger.info("🛑 Data Collector 종료")

def signal_handler(signum, frame):
    logger.info(f"신호 {signum} 수신, 종료 중...")
    if client:
        asyncio.create_task(client.close())
    sys.exit(0)

if __name__ == "__main__":
    # 신호 처리 설정
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    # 환경변수에서 심볼 확인
    symbol = os.getenv('SYMBOL', settings.symbol)
    if symbol != settings.symbol:
        settings.symbol = symbol
    
    logger.info(f"수집 대상 심볼: {settings.symbol}")
    
    # 이벤트 루프 실행
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("프로그램이 중단되었습니다.")
    except Exception as e:
        logger.error(f"치명적 오류: {e}")
        sys.exit(1)
```

이 문서는 OKX 실시간 캔들 데이터 수집 시스템의 완전한 코드 템플릿과 구현 예시를 제공합니다. Claude Code가 이 템플릿을 기반으로 즉시 프로덕션 레벨의 시스템을 구현할 수 있습니다.
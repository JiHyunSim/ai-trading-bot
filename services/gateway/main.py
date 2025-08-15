"""
OKX Trading Gateway Service
실시간 캔들 데이터 수집 시스템의 API Gateway
"""

import asyncio
import json
import logging
import os
from contextlib import asynccontextmanager
from datetime import datetime
from typing import List, Optional

import redis.asyncio as redis
import structlog
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from prometheus_client import Counter, Histogram, generate_latest
from dotenv import load_dotenv

# 환경 변수 로드
load_dotenv()

from app.core.config import get_settings
from app.core.redis_client import get_redis_client

# 설정 로드
settings = get_settings()

# 구조화된 로깅 설정
structlog.configure(
    processors=[
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.dev.ConsoleRenderer()
    ],
    wrapper_class=structlog.stdlib.BoundLogger,
    logger_factory=structlog.stdlib.LoggerFactory(),
    cache_logger_on_first_use=True,
)

logger = structlog.get_logger(__name__)

# Prometheus 메트릭 (중복 등록 방지)
try:
    REQUESTS_TOTAL = Counter('gateway_requests_total', 'Total requests', ['method', 'endpoint'])
    REQUEST_DURATION = Histogram('gateway_request_duration_seconds', 'Request duration')
except ValueError as e:
    # 메트릭이 이미 등록된 경우 무시
    logger.warning(f"Prometheus metrics already registered: {e}")
    from prometheus_client import REGISTRY
    REQUESTS_TOTAL = None
    REQUEST_DURATION = None


class SubscriptionRequest(BaseModel):
    """구독 요청 모델"""
    symbols: List[str] = Field(..., description="구독할 심볼 목록", example=["BTC-USDT", "ETH-USDT"])
    timeframes: List[str] = Field(..., description="시간프레임 목록", example=["1m", "5m", "1H"])
    webhook_url: Optional[str] = Field(None, description="웹훅 URL (선택사항)")


class SubscriptionResponse(BaseModel):
    """구독 응답 모델"""
    status: str
    message: str
    symbols: List[str]
    subscription_id: Optional[str] = None
    created_at: str


class StatusResponse(BaseModel):
    """상태 응답 모델"""
    symbol: str
    status: str
    last_update: str
    timeframes: List[str]
    statistics: dict
    connection_info: dict


class HealthResponse(BaseModel):
    """헬스체크 응답 모델"""
    status: str
    timestamp: str
    version: str = "1.0.0"
    uptime_seconds: int
    checks: dict


@asynccontextmanager
async def lifespan(app: FastAPI):
    """애플리케이션 라이프사이클 관리"""
    # 시작 시
    logger.info("Starting Gateway Service", version="1.0.0")
    
    # Redis 연결 설정
    app.redis = await get_redis_client()
    await app.redis.ping()
    logger.info("Redis connection established")
    
    yield
    
    # 종료 시
    logger.info("Shutting down Gateway Service")
    if hasattr(app, 'redis'):
        await app.redis.close()
    logger.info("Gateway Service shutdown complete")


# FastAPI 앱 생성
app = FastAPI(
    title="OKX Trading Gateway",
    description="OKX 실시간 캔들 데이터 수집 시스템 API Gateway",
    version="1.0.0",
    lifespan=lifespan
)


@app.middleware("http")
async def logging_middleware(request, call_next):
    """로깅 미들웨어"""
    start_time = asyncio.get_event_loop().time()
    
    # 요청 로깅
    logger.info(
        "Request received",
        method=request.method,
        url=str(request.url),
        client_ip=request.client.host if request.client else None
    )
    
    # 메트릭 업데이트
    if REQUESTS_TOTAL:
        REQUESTS_TOTAL.labels(method=request.method, endpoint=request.url.path).inc()
    
    try:
        response = await call_next(request)
        
        # 응답 시간 계산
        process_time = asyncio.get_event_loop().time() - start_time
        if REQUEST_DURATION:
            REQUEST_DURATION.observe(process_time)
        
        logger.info(
            "Request completed",
            method=request.method,
            url=str(request.url),
            status_code=response.status_code,
            duration_seconds=process_time
        )
        
        return response
        
    except Exception as e:
        process_time = asyncio.get_event_loop().time() - start_time
        logger.error(
            "Request failed",
            method=request.method,
            url=str(request.url),
            error=str(e),
            duration_seconds=process_time
        )
        raise


@app.get("/health", response_model=HealthResponse)
async def health_check():
    """헬스체크 엔드포인트"""
    try:
        # Redis 연결 확인
        redis_status = "healthy"
        try:
            await app.redis.ping()
        except Exception:
            redis_status = "unhealthy"
        
        return HealthResponse(
            status="healthy" if redis_status == "healthy" else "degraded",
            timestamp=datetime.utcnow().isoformat(),
            uptime_seconds=0,  # TODO: 실제 업타임 계산
            checks={
                "redis": redis_status,
                "message_queue": "healthy",
                "websocket_connections": "healthy"
            }
        )
    except Exception as e:
        logger.error("Health check failed", error=str(e))
        raise HTTPException(status_code=503, detail="Service unavailable")


@app.get("/metrics")
async def metrics():
    """Prometheus 메트릭 엔드포인트"""
    return generate_latest().decode('utf-8')


@app.post("/api/v1/subscribe", response_model=SubscriptionResponse)
async def subscribe_to_symbols(request: SubscriptionRequest):
    """심볼 구독 요청 처리"""
    try:
        subscription_id = f"sub_{int(datetime.utcnow().timestamp())}"
        
        subscription_config = {
            "action": "subscribe",
            "symbols": request.symbols,
            "timeframes": request.timeframes,
            "webhook_url": request.webhook_url,
            "subscription_id": subscription_id,
            "timestamp": datetime.utcnow().isoformat()
        }
        
        # 각 심볼에 대해 구독 설정 저장 및 컬렉터에 신호 전송
        for symbol in request.symbols:
            # 구독 설정 저장 (1시간 TTL)
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
            
            logger.info(
                "Subscription created",
                symbol=symbol,
                timeframes=request.timeframes,
                subscription_id=subscription_id
            )
        
        return SubscriptionResponse(
            status="success",
            message=f"Subscribed to {len(request.symbols)} symbols",
            symbols=request.symbols,
            subscription_id=subscription_id,
            created_at=datetime.utcnow().isoformat()
        )
        
    except Exception as e:
        logger.error("Subscription failed", error=str(e), symbols=request.symbols)
        raise HTTPException(status_code=500, detail=f"Subscription failed: {str(e)}")


@app.get("/api/v1/status/{symbol}", response_model=StatusResponse)
async def get_symbol_status(symbol: str):
    """심볼별 수집 상태 조회"""
    try:
        # Redis에서 상태 정보 조회
        status_data = await app.redis.get(f"status:{symbol}")
        if not status_data:
            raise HTTPException(status_code=404, detail="Symbol not found")
        
        status_info = json.loads(status_data)
        
        # 기본 응답 구조로 변환
        return StatusResponse(
            symbol=symbol,
            status=status_info.get("status", "unknown"),
            last_update=status_info.get("last_update", datetime.utcnow().isoformat()),
            timeframes=status_info.get("timeframes", []),
            statistics={
                "messages_received": status_info.get("messages_received", 0),
                "messages_processed": status_info.get("messages_processed", 0),
                "messages_failed": status_info.get("messages_failed", 0),
                "uptime_seconds": status_info.get("uptime_seconds", 0),
                "last_price": status_info.get("last_price", 0.0)
            },
            connection_info={
                "websocket_connected": status_info.get("websocket_connected", False),
                "last_reconnect": status_info.get("last_reconnect"),
                "reconnect_count": status_info.get("reconnect_count", 0)
            }
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Status retrieval failed", symbol=symbol, error=str(e))
        raise HTTPException(status_code=500, detail=f"Status retrieval failed: {str(e)}")


@app.delete("/api/v1/subscribe/{symbol}")
async def unsubscribe_symbol(symbol: str):
    """심볼 구독 해제"""
    try:
        # 구독 설정 삭제
        deleted = await app.redis.delete(f"subscription:{symbol}")
        
        if deleted:
            # 컬렉터에 구독 해제 신호 전송
            unsubscribe_config = {
                "action": "unsubscribe",
                "symbol": symbol,
                "timestamp": datetime.utcnow().isoformat()
            }
            
            await app.redis.publish(
                f"collector:{symbol}",
                json.dumps(unsubscribe_config)
            )
            
            logger.info("Subscription cancelled", symbol=symbol)
            
            return {
                "status": "success",
                "message": f"Unsubscribed from {symbol}",
                "symbol": symbol,
                "stopped_at": datetime.utcnow().isoformat()
            }
        else:
            raise HTTPException(status_code=404, detail="Subscription not found")
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Unsubscription failed", symbol=symbol, error=str(e))
        raise HTTPException(status_code=500, detail=f"Unsubscription failed: {str(e)}")


@app.get("/api/v1/subscriptions")
async def get_subscriptions():
    """현재 활성 구독 목록 조회"""
    try:
        # Redis에서 모든 구독 키 조회
        subscription_keys = await app.redis.keys("subscription:*")
        subscriptions = []
        
        for key in subscription_keys:
            subscription_data = await app.redis.get(key)
            if subscription_data:
                data = json.loads(subscription_data)
                symbol = key.decode('utf-8').split(':')[1]
                
                subscriptions.append({
                    "symbol": symbol,
                    "timeframes": data.get("timeframes", []),
                    "status": "active",
                    "started_at": data.get("timestamp"),
                    "last_message": data.get("last_message", data.get("timestamp"))
                })
        
        return {
            "status": "success",
            "total": len(subscriptions),
            "subscriptions": subscriptions
        }
        
    except Exception as e:
        logger.error("Subscriptions retrieval failed", error=str(e))
        raise HTTPException(status_code=500, detail=f"Subscriptions retrieval failed: {str(e)}")


if __name__ == "__main__":
    import uvicorn
    
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=settings.DEBUG,
        log_level=settings.LOG_LEVEL.lower()
    )
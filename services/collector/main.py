"""
OKX Data Collector Service
OKX WebSocket API를 통한 실시간 캔들스틱 데이터 수집
"""

import asyncio
import json
import logging
import os
import signal
import sys
from datetime import datetime

import structlog
from dotenv import load_dotenv

# 환경 변수 로드
load_dotenv()

from app.core.config import get_settings
from app.websocket.okx_client import OKXDataCollector

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

# 전역 변수
collectors = {}
shutdown_event = asyncio.Event()


async def signal_handler(signum, frame):
    """시그널 핸들러"""
    logger.info(f"Received signal {signum}, initiating shutdown...")
    shutdown_event.set()


async def create_collector_for_symbol(symbol: str):
    """심볼별 컬렉터 생성 및 시작"""
    try:
        if symbol in collectors:
            logger.warning(f"Collector for {symbol} already exists")
            return
        
        collector = OKXDataCollector(symbol)
        await collector.initialize()
        
        collectors[symbol] = collector
        
        # 백그라운드에서 컬렉터 실행
        task = asyncio.create_task(collector.run())
        collectors[f"{symbol}_task"] = task
        
        logger.info(f"Collector created and started for {symbol}")
        
    except Exception as e:
        logger.error(f"Failed to create collector for {symbol}", error=str(e))


async def stop_collector_for_symbol(symbol: str):
    """심볼별 컬렉터 중지"""
    try:
        if symbol in collectors:
            collector = collectors[symbol]
            await collector.stop()
            del collectors[symbol]
            
            # 태스크도 정리
            task_key = f"{symbol}_task"
            if task_key in collectors:
                task = collectors[task_key]
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
                del collectors[task_key]
            
            logger.info(f"Collector stopped for {symbol}")
        
    except Exception as e:
        logger.error(f"Failed to stop collector for {symbol}", error=str(e))


async def subscription_listener():
    """구독 요청 리스너"""
    import redis.asyncio as redis
    
    try:
        redis_client = redis.Redis(
            host=settings.REDIS_HOST,
            port=settings.REDIS_PORT,
            db=settings.REDIS_DB,
            password=settings.REDIS_PASSWORD,
            decode_responses=True
        )
        
        # Redis 연결 확인
        await redis_client.ping()
        logger.info("Connected to Redis for subscription listening")
        
        # 패턴 구독 (모든 심볼의 컬렉터 채널)
        pubsub = redis_client.pubsub()
        await pubsub.psubscribe("collector:*")
        
        async for message in pubsub.listen():
            if shutdown_event.is_set():
                break
                
            if message['type'] == 'pmessage':
                try:
                    # 채널에서 심볼 추출
                    channel = message['channel']
                    symbol = channel.split(':')[1]
                    
                    # 메시지 파싱
                    data = json.loads(message['data'])
                    action = data.get('action')
                    
                    if action == 'subscribe':
                        logger.info(f"Received subscription request for {symbol}")
                        await create_collector_for_symbol(symbol)
                    elif action == 'unsubscribe':
                        logger.info(f"Received unsubscription request for {symbol}")
                        await stop_collector_for_symbol(symbol)
                    
                except Exception as e:
                    logger.error("Failed to process subscription message", error=str(e))
        
        await pubsub.unsubscribe()
        await redis_client.close()
        
    except Exception as e:
        logger.error("Subscription listener failed", error=str(e))


async def health_reporter():
    """헬스 상태 보고"""
    import redis.asyncio as redis
    
    try:
        redis_client = redis.Redis(
            host=settings.REDIS_HOST,
            port=settings.REDIS_PORT,
            db=settings.REDIS_DB,
            password=settings.REDIS_PASSWORD,
            decode_responses=True
        )
        
        while not shutdown_event.is_set():
            try:
                # 각 컬렉터의 상태 보고
                for symbol, collector in collectors.items():
                    if not symbol.endswith('_task') and hasattr(collector, 'get_status'):
                        status = await collector.get_status()
                        await redis_client.set(
                            f"collector_status:{symbol}",
                            json.dumps(status),
                            ex=120  # 2분 TTL
                        )
                
                # 전체 컬렉터 서비스 상태
                service_status = {
                    "service": "collector",
                    "active_collectors": len([k for k in collectors.keys() if not k.endswith('_task')]),
                    "timestamp": datetime.utcnow().isoformat(),
                    "status": "healthy"
                }
                
                await redis_client.set(
                    "collector_service_status",
                    json.dumps(service_status),
                    ex=120
                )
                
                await asyncio.sleep(30)  # 30초마다 보고
                
            except Exception as e:
                logger.error("Health reporting failed", error=str(e))
                await asyncio.sleep(10)
        
        await redis_client.close()
        
    except Exception as e:
        logger.error("Health reporter failed", error=str(e))


async def main():
    """메인 함수"""
    logger.info("Starting OKX Data Collector Service")
    
    # 시그널 핸들러 설정
    for signum in [signal.SIGTERM, signal.SIGINT]:
        signal.signal(signum, lambda s, f: asyncio.create_task(signal_handler(s, f)))
    
    # 자동 시작 설정 확인
    if settings.AUTO_START:
        # 기본 심볼로 BTC-USDT 무기한 선물 자동 시작
        initial_symbol = settings.DEFAULT_SYMBOL
        logger.info(f"Auto-starting collection for {initial_symbol} with timeframes: {settings.DEFAULT_TIMEFRAMES}")
        await create_collector_for_symbol(initial_symbol)
    
    # 환경변수에서 추가 심볼 설정 확인 (하위 호환성)
    additional_symbol = os.getenv('SYMBOL') or settings.SYMBOL
    if additional_symbol and additional_symbol != settings.DEFAULT_SYMBOL:
        logger.info(f"Starting additional symbol: {additional_symbol}")
        await create_collector_for_symbol(additional_symbol)
    
    # 백그라운드 태스크 시작
    tasks = [
        asyncio.create_task(subscription_listener()),
        asyncio.create_task(health_reporter()),
    ]
    
    try:
        # 종료 신호까지 대기
        await shutdown_event.wait()
        
    except KeyboardInterrupt:
        logger.info("Received keyboard interrupt")
    finally:
        logger.info("Shutting down collectors...")
        
        # 모든 컬렉터 중지
        for symbol in list(collectors.keys()):
            if not symbol.endswith('_task'):
                await stop_collector_for_symbol(symbol)
        
        # 백그라운드 태스크 취소
        for task in tasks:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        
        logger.info("OKX Data Collector Service shutdown complete")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Service interrupted by user")
    except Exception as e:
        logger.error("Service failed", error=str(e))
        sys.exit(1)
"""
OKX Data Processor Service
Redis 큐에서 캔들 데이터를 가져와 PostgreSQL에 배치 처리하여 저장
"""

import asyncio
import json
import signal
import sys
from datetime import datetime

import structlog
from dotenv import load_dotenv

# 환경 변수 로드
load_dotenv()

from app.core.config import get_settings
from app.processors.batch_processor import BatchProcessor

# 설정 로드
settings = get_settings()

# 로깅 설정
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

# 글로벌 변수
shutdown_event = asyncio.Event()
processor = None

async def signal_handler(signum, frame):
    """시그널 핸들러"""
    logger.info(f"Received signal {signum}, initiating shutdown...")
    shutdown_event.set()

async def main():
    """메인 함수"""
    global processor
    
    logger.info("Starting OKX Data Processor Service")
    
    # 시그널 핸들러 설정
    for signum in [signal.SIGTERM, signal.SIGINT]:
        signal.signal(signum, lambda s, f: asyncio.create_task(signal_handler(s, f)))
    
    try:
        # 배치 프로세서 초기화
        processor = BatchProcessor()
        await processor.initialize()
        
        # 프로세싱 시작
        processing_task = asyncio.create_task(processor.start_processing())
        
        # 종료 신호까지 대기
        await shutdown_event.wait()
        
        logger.info("Shutdown signal received, stopping processor...")
        
        # 프로세서 중지
        await processor.stop()
        
        # 처리 태스크 취소
        processing_task.cancel()
        try:
            await processing_task
        except asyncio.CancelledError:
            pass
        
        logger.info("OKX Data Processor Service shutdown complete")
        
    except Exception as e:
        logger.error("Service failed", error=str(e))
        if processor:
            await processor.stop()
        sys.exit(1)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Service interrupted by user")
    except Exception as e:
        logger.error("Service failed", error=str(e))
        sys.exit(1)
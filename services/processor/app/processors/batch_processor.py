"""Batch Data Processor for PostgreSQL"""

import asyncio
import json
from datetime import datetime
from typing import Dict, List

import asyncpg
import redis.asyncio as redis
import structlog

from app.core.config import get_settings

logger = structlog.get_logger(__name__)


class BatchProcessor:
    """배치 데이터 처리기"""
    
    def __init__(self):
        self.settings = get_settings()
        self.redis_client = None
        self.db_pool = None
        self.is_running = False
        
    async def initialize(self):
        """프로세서 초기화"""
        try:
            # Redis 클라이언트 초기화
            self.redis_client = redis.Redis(
                host=self.settings.REDIS_HOST,
                port=self.settings.REDIS_PORT,
                db=self.settings.REDIS_DB,
                password=self.settings.REDIS_PASSWORD,
                decode_responses=True,
                retry_on_timeout=True
            )
            
            # Redis 연결 테스트
            ping_result = await self.redis_client.ping()
            if not ping_result:
                raise ConnectionError("Failed to connect to Redis")
            logger.info("Redis connection established")
            
            # PostgreSQL 연결 풀 생성
            self.db_pool = await asyncpg.create_pool(
                host=self.settings.DB_HOST,
                port=self.settings.DB_PORT,
                database=self.settings.DB_NAME,
                user=self.settings.DB_USER,
                password=self.settings.DB_PASSWORD,
                min_size=5,
                max_size=self.settings.DB_POOL_SIZE,
                command_timeout=60
            )
            
            logger.info("PostgreSQL connection pool created")
            
            # 데이터베이스 테이블 존재 확인 (기본 테이블만)
            await self.verify_database_schema()
            
        except Exception as e:
            logger.error("Failed to initialize processor", error=str(e))
            raise
    
    async def verify_database_schema(self):
        """데이터베이스 스키마 확인"""
        try:
            async with self.db_pool.acquire() as conn:
                # 기본 테이블 존재 확인
                tables = await conn.fetch("""
                    SELECT table_name 
                    FROM information_schema.tables 
                    WHERE table_schema = 'public'
                    AND table_name IN ('symbols', 'timeframes', 'candlestick_data')
                """)
                
                existing_tables = [row['table_name'] for row in tables]
                
                if 'symbols' not in existing_tables:
                    logger.warning("symbols table not found - creating basic structure")
                    await self.create_basic_tables(conn)
                
                logger.info("Database schema verified", tables=existing_tables)
                
        except Exception as e:
            logger.error("Database schema verification failed", error=str(e))
            # 프로덕션에서는 테이블이 이미 존재해야 하므로 에러를 발생시킵니다
            # 개발 환경에서는 기본 테이블을 생성할 수 있습니다
            if self.settings.ENV == "development":
                logger.warning("Development mode: attempting to create basic tables")
            else:
                raise
    
    async def create_basic_tables(self, conn):
        """기본 테이블 생성 (개발 환경용)"""
        try:
            # 기본 symbols 테이블
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS symbols (
                    id SERIAL PRIMARY KEY,
                    symbol VARCHAR(20) UNIQUE NOT NULL,
                    base_currency VARCHAR(10) NOT NULL,
                    quote_currency VARCHAR(10) NOT NULL,
                    instrument_type VARCHAR(20) NOT NULL DEFAULT 'SPOT',
                    status VARCHAR(10) DEFAULT 'ACTIVE',
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # 기본 timeframes 테이블
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS timeframes (
                    id SERIAL PRIMARY KEY,
                    name VARCHAR(10) UNIQUE NOT NULL,
                    display_name VARCHAR(20) NOT NULL,
                    seconds INTEGER NOT NULL,
                    sort_order INTEGER DEFAULT 0,
                    is_active BOOLEAN DEFAULT true,
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # 기본 데이터 삽입
            await conn.execute("""
                INSERT INTO symbols (symbol, base_currency, quote_currency) VALUES
                ('BTC-USDT', 'BTC', 'USDT'),
                ('ETH-USDT', 'ETH', 'USDT')
                ON CONFLICT (symbol) DO NOTHING
            """)
            
            await conn.execute("""
                INSERT INTO timeframes (name, display_name, seconds, sort_order) VALUES
                ('1m', '1 Minute', 60, 1),
                ('5m', '5 Minutes', 300, 2),
                ('1H', '1 Hour', 3600, 3)
                ON CONFLICT (name) DO NOTHING
            """)
            
            logger.info("Basic tables created successfully")
            
        except Exception as e:
            logger.error("Failed to create basic tables", error=str(e))
            raise
    
    async def start_processing(self):
        """배치 처리 시작"""
        self.is_running = True
        
        tasks = [
            asyncio.create_task(self.batch_processor()),
            asyncio.create_task(self.dead_letter_processor()),
            asyncio.create_task(self.metrics_collector())
        ]
        
        try:
            await asyncio.gather(*tasks)
        except Exception as e:
            logger.error("Processing failed", error=str(e))
        finally:
            # 태스크 정리
            for task in tasks:
                if not task.done():
                    task.cancel()
                    try:
                        await task
                    except asyncio.CancelledError:
                        pass
    
    async def batch_processor(self):
        """배치 처리 메인 루프"""
        while self.is_running:
            try:
                batch = []
                
                # 첫 번째 메시지 대기
                message = await self.redis_client.brpop(
                    "candle_data_queue", 
                    timeout=self.settings.BATCH_TIMEOUT
                )
                
                if not message:
                    continue
                
                # brpop returns (queue_name, value) tuple
                queue_name, message_data = message
                batch.append(json.loads(message_data))
                
                # 배치 크기만큼 추가 메시지 수집
                for _ in range(self.settings.BATCH_SIZE - 1):
                    message = await self.redis_client.rpop("candle_data_queue")
                    if not message:
                        break
                    batch.append(json.loads(message))
                
                # 배치 처리
                if batch:
                    await self.process_batch(batch)
                
            except Exception as e:
                logger.error("Batch processing error", error=str(e))
                await asyncio.sleep(1)
    
    async def process_batch(self, batch: List[Dict]):
        """배치 데이터 PostgreSQL 저장"""
        if not batch:
            return
            
        try:
            async with self.db_pool.acquire() as conn:
                async with conn.transaction():
                    # 심볼과 시간프레임 ID 매핑 캐시
                    symbol_cache = {}
                    timeframe_cache = {}
                    
                    # 배치 데이터 준비
                    insert_data = []
                    
                    for item in batch:
                        try:
                            symbol = item['symbol']
                            timeframe = item['timeframe']
                            
                            # 심볼 ID 조회/캐싱
                            if symbol not in symbol_cache:
                                symbol_id = await conn.fetchval(
                                    "SELECT id FROM symbols WHERE symbol = $1", symbol
                                )
                                if not symbol_id:
                                    # 심볼이 없으면 생성
                                    symbol_parts = symbol.split('-')
                                    if len(symbol_parts) >= 2:
                                        base = symbol_parts[0]
                                        quote = symbol_parts[1]
                                        # SWAP 등 추가 정보는 instrument_type으로 처리
                                        instrument_type = 'SWAP' if 'SWAP' in symbol else 'SPOT'
                                    else:
                                        base = symbol
                                        quote = 'USDT'  # 기본값
                                        instrument_type = 'SPOT'
                                    
                                    symbol_id = await conn.fetchval(
                                        "INSERT INTO symbols (symbol, base_currency, quote_currency, instrument_type) "
                                        "VALUES ($1, $2, $3, $4) RETURNING id",
                                        symbol, base, quote, instrument_type
                                    )
                                symbol_cache[symbol] = symbol_id
                            
                            # 시간프레임 ID 조회/캐싱
                            if timeframe not in timeframe_cache:
                                tf_id = await conn.fetchval(
                                    "SELECT id FROM timeframes WHERE name = $1", timeframe
                                )
                                if not tf_id:
                                    # 시간프레임이 없으면 생성
                                    tf_seconds = self.parse_timeframe_seconds(timeframe)
                                    tf_id = await conn.fetchval(
                                        "INSERT INTO timeframes (name, display_name, seconds) "
                                        "VALUES ($1, $2, $3) RETURNING id",
                                        timeframe, timeframe, tf_seconds
                                    )
                                timeframe_cache[timeframe] = tf_id
                            
                            insert_data.append((
                                symbol,  # symbol 문자열 직접 사용
                                timeframe,  # timeframe 문자열 직접 사용
                                item['timestamp'],  # timestamp_ms로 삽입
                                float(item['open']),
                                float(item['high']),
                                float(item['low']),
                                float(item['close']),
                                float(item['volume'])
                            ))
                            
                        except Exception as e:
                            logger.error("Failed to prepare batch item", error=str(e), item=item)
                            continue
                    
                    if insert_data:
                        # 배치 삽입 (테이블이 존재하지 않을 수 있으므로 try-catch)
                        try:
                            # 중복 방지를 위한 ON CONFLICT 처리
                            await conn.executemany(
                                """
                                INSERT INTO trading.candlesticks 
                                (symbol, timeframe, timestamp_ms, open_price, high_price, 
                                 low_price, close_price, volume)
                                VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                                ON CONFLICT (symbol, timeframe, timestamp_ms) 
                                DO UPDATE SET
                                    open_price = EXCLUDED.open_price,
                                    high_price = EXCLUDED.high_price,
                                    low_price = EXCLUDED.low_price,
                                    close_price = EXCLUDED.close_price,
                                    volume = EXCLUDED.volume,
                                    created_at = CURRENT_TIMESTAMP
                                """,
                                insert_data
                            )
                            
                            logger.info(f"Processed batch of {len(insert_data)} records")
                            
                        except asyncpg.UndefinedTableError:
                            logger.warning("candlestick_data table does not exist - sending to DLQ")
                            await self.send_to_dlq(batch, "candlestick_data table not found")
                        
        except Exception as e:
            logger.error("Database batch processing failed", error=str(e))
            await self.send_to_dlq(batch, str(e))
    
    def parse_timeframe_seconds(self, timeframe: str) -> int:
        """시간프레임을 초 단위로 변환"""
        if timeframe.endswith('m'):
            return int(timeframe[:-1]) * 60
        elif timeframe.endswith('H'):
            return int(timeframe[:-1]) * 3600
        elif timeframe.endswith('D'):
            return int(timeframe[:-1]) * 86400
        else:
            return 60  # 기본값
    
    async def send_to_dlq(self, batch: List[Dict], error: str):
        """Dead Letter Queue로 실패 데이터 전송"""
        try:
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
            
            logger.warning(f"Sent {len(batch)} items to DLQ", error=error)
            
        except Exception as e:
            logger.error("Failed to send items to DLQ", error=str(e))
    
    async def dead_letter_processor(self):
        """Dead Letter Queue 처리"""
        while self.is_running:
            try:
                message = await self.redis_client.brpop("dead_letter_queue", timeout=30)
                if not message:
                    continue
                
                item = json.loads(message[1])
                retry_count = item.get("retry_count", 0)
                
                if retry_count < self.settings.MAX_RETRIES:
                    # 재시도
                    await asyncio.sleep(retry_count * 10)  # 지수 백오프
                    await self.redis_client.lpush("candle_data_queue", json.dumps(item))
                    logger.info("Retrying DLQ item", symbol=item.get('symbol'), retry=retry_count)
                else:
                    # 영구 실패
                    logger.error("Permanent DLQ failure", item=item)
                    
            except Exception as e:
                logger.error("DLQ processing error", error=str(e))
                await asyncio.sleep(5)
    
    async def metrics_collector(self):
        """메트릭 수집"""
        while self.is_running:
            try:
                queue_length = await self.redis_client.llen("candle_data_queue")
                dlq_length = await self.redis_client.llen("dead_letter_queue")
                
                metrics = {
                    "service": "processor",
                    "queue_length": queue_length,
                    "dlq_length": dlq_length,
                    "timestamp": datetime.utcnow().isoformat(),
                    "status": "healthy" if queue_length < 10000 else "degraded"
                }
                
                await self.redis_client.set("processor_metrics", json.dumps(metrics), ex=60)
                
                if queue_length > 10000:
                    logger.warning(f"High queue length: {queue_length}")
                
                await asyncio.sleep(30)
                
            except Exception as e:
                logger.error("Metrics collection error", error=str(e))
                await asyncio.sleep(30)
    
    async def stop(self):
        """프로세서 중지"""
        logger.info("Stopping batch processor")
        
        self.is_running = False
        
        if self.db_pool:
            await self.db_pool.close()
        
        if self.redis_client:
            await self.redis_client.close()
        
        logger.info("Batch processor stopped")
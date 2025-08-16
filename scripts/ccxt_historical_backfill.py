#!/usr/bin/env python3
"""
CCXT 기반 과거 데이터 백필 스크립트
심볼별 지정 기간 캔들 데이터 일괄 수집 (CCXT 라이브러리 활용)
"""

import asyncio
import sys
import argparse
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
import asyncpg
import ccxt.async_support as ccxt
from dotenv import load_dotenv
import structlog
from dataclasses import dataclass
import os

# 환경 변수 로드
load_dotenv()

# 로깅 설정
logging.basicConfig(level=logging.INFO)

structlog.configure(
    processors=[
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_log_level,
        structlog.dev.ConsoleRenderer()
    ],
    wrapper_class=structlog.stdlib.BoundLogger,
    logger_factory=structlog.stdlib.LoggerFactory(),
    cache_logger_on_first_use=True,
)

logger = structlog.get_logger(__name__)


@dataclass
class BackfillProgress:
    """백필 진행상황 추적"""
    symbol: str
    timeframe: str
    total_expected: int = 0
    total_fetched: int = 0
    total_inserted: int = 0
    total_duplicates: int = 0
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    status: str = "pending"  # pending, in_progress, completed, failed


class CCXTHistoricalBackfill:
    """CCXT 기반 과거 데이터 백필 시스템"""
    
    def __init__(self, 
                 db_host: str = "localhost",
                 db_port: int = 5432,
                 db_name: str = "trading_bot",
                 db_user: str = "trading_bot",
                 db_password: str = "trading_bot_password",
                 exchange_id: str = "okx"):
        
        self.db_host = db_host
        self.db_port = db_port
        self.db_name = db_name
        self.db_user = db_user
        self.db_password = db_password
        self.db_pool = None
        
        # CCXT 거래소 설정
        self.exchange_id = exchange_id
        self.exchange = None
        
        # 타임프레임별 설정
        self.timeframe_config = {
            "1m": {"records_per_batch": 1000},
            "5m": {"records_per_batch": 1000},
            "15m": {"records_per_batch": 1000},
            "1h": {"records_per_batch": 1000},
            "4h": {"records_per_batch": 1000},
            "1d": {"records_per_batch": 1000}
        }
        
        # 진행상황 추적
        self.progress_tracker = {}
        
        # 통계
        self.total_stats = {
            "symbols_processed": 0,
            "timeframes_processed": 0,
            "total_api_calls": 0,
            "total_candles_fetched": 0,
            "total_candles_inserted": 0,
            "total_duplicates_skipped": 0,
            "total_errors": 0
        }
    
    async def initialize(self):
        """초기화"""
        try:
            # 데이터베이스 연결 풀 생성
            self.db_pool = await asyncpg.create_pool(
                host=self.db_host,
                port=self.db_port,
                database=self.db_name,
                user=self.db_user,
                password=self.db_password,
                min_size=2,
                max_size=20,
                command_timeout=300
            )
            
            # 연결 테스트
            async with self.db_pool.acquire() as conn:
                await conn.fetchval("SELECT 1")
            
            # CCXT 거래소 초기화
            exchange_class = getattr(ccxt, self.exchange_id)
            self.exchange = exchange_class({
                'apiKey': os.getenv('OKX_API_KEY'),
                'secret': os.getenv('OKX_SECRET_KEY'),
                'password': os.getenv('OKX_PASSPHRASE'),
                'sandbox': os.getenv('OKX_SANDBOX', 'False').lower() == 'true',
                'enableRateLimit': True,
                'options': {
                    'defaultType': 'swap',
                },
            })
            
            logger.info(f"CCXT backfill system initialized with {self.exchange_id}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to initialize CCXT backfill system: {e}")
            return False
    
    async def close(self):
        """리소스 정리"""
        if self.exchange:
            await self.exchange.close()
        if self.db_pool:
            await self.db_pool.close()
    
    async def fetch_historical_ohlcv(self, symbol: str, timeframe: str, 
                                   since: int, limit: int = 1000) -> List[List]:
        """CCXT를 통한 과거 OHLCV 데이터 조회"""
        try:
            if not self.exchange.has['fetchOHLCV']:
                logger.error(f"Exchange {self.exchange_id} does not support fetchOHLCV")
                return []
            
            # CCXT fetchOHLCV 호출
            ohlcv = await self.exchange.fetch_ohlcv(
                symbol=symbol,
                timeframe=timeframe,
                since=since,
                limit=limit
            )
            
            self.total_stats["total_api_calls"] += 1
            self.total_stats["total_candles_fetched"] += len(ohlcv)
            
            return ohlcv
            
        except Exception as e:
            logger.error(f"Failed to fetch OHLCV for {symbol}/{timeframe}: {e}")
            self.total_stats["total_errors"] += 1
            return []
    
    async def insert_candles_batch(self, symbol: str, timeframe: str, 
                                  ohlcv_data: List[List]) -> Tuple[int, int]:
        """캔들 데이터 배치 삽입 (trading.candlesticks 테이블)"""
        try:
            if not ohlcv_data:
                return 0, 0
            
            inserted_count = 0
            duplicate_count = 0
            
            async with self.db_pool.acquire() as conn:
                async with conn.transaction():
                    for candle in ohlcv_data:
                        try:
                            timestamp_ms = int(candle[0])
                            open_price = float(candle[1])
                            high_price = float(candle[2])
                            low_price = float(candle[3])
                            close_price = float(candle[4])
                            volume = float(candle[5])
                            
                            # 데이터 유효성 검사
                            if volume <= 0 or close_price <= 0:
                                continue
                            
                            result = await conn.execute("""
                                INSERT INTO trading.candlesticks 
                                (symbol, timeframe, timestamp_ms, open_price, high_price, 
                                 low_price, close_price, volume)
                                VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                                ON CONFLICT (symbol, timeframe, timestamp_ms) 
                                DO NOTHING
                            """, symbol, timeframe, timestamp_ms,
                                 open_price, high_price, low_price,
                                 close_price, volume)
                            
                            if result == "INSERT 0 1":
                                inserted_count += 1
                            else:
                                duplicate_count += 1
                                
                        except Exception as e:
                            logger.error(f"Failed to insert candle {candle}: {e}")
                            continue
            
            self.total_stats["total_candles_inserted"] += inserted_count
            self.total_stats["total_duplicates_skipped"] += duplicate_count
            
            return inserted_count, duplicate_count
            
        except Exception as e:
            logger.error(f"Failed to insert candles batch for {symbol}/{timeframe}: {e}")
            self.total_stats["total_errors"] += 1
            return 0, 0
    
    async def get_existing_data_range(self, symbol: str, timeframe: str) -> Tuple[Optional[int], Optional[int]]:
        """기존 데이터 범위 조회"""
        try:
            async with self.db_pool.acquire() as conn:
                result = await conn.fetchrow("""
                    SELECT MIN(timestamp_ms) as min_ts, MAX(timestamp_ms) as max_ts
                    FROM trading.candlesticks 
                    WHERE symbol = $1 AND timeframe = $2
                """, symbol, timeframe)
                
                return result['min_ts'], result['max_ts']
                
        except Exception as e:
            logger.error(f"Failed to get existing data range for {symbol}/{timeframe}: {e}")
            return None, None
    
    async def backfill_symbol_timeframe(self, symbol: str, timeframe: str, 
                                       days_back: int = 30) -> BackfillProgress:
        """특정 심볼/타임프레임 백필"""
        progress_key = f"{symbol}_{timeframe}"
        progress = BackfillProgress(symbol=symbol, timeframe=timeframe)
        progress.start_time = datetime.now()
        progress.status = "in_progress"
        
        self.progress_tracker[progress_key] = progress
        
        try:
            # 시간 범위 계산
            end_time = datetime.now()
            start_time = end_time - timedelta(days=days_back)
            
            end_ts = int(end_time.timestamp() * 1000)
            start_ts = int(start_time.timestamp() * 1000)
            
            # 기존 데이터 범위 확인
            existing_min, existing_max = await self.get_existing_data_range(symbol, timeframe)
            
            logger.info(f"Starting CCXT backfill for {symbol}/{timeframe}")
            logger.info(f"Target range: {start_time} to {end_time}")
            if existing_min and existing_max:
                existing_start = datetime.fromtimestamp(existing_min / 1000)
                existing_end = datetime.fromtimestamp(existing_max / 1000)
                logger.info(f"Existing range: {existing_start} to {existing_end}")
            
            # CCXT 타임프레임 간격 계산
            timeframe_duration_ms = self.exchange.parse_timeframe(timeframe) * 1000
            expected_candles = (end_ts - start_ts) // timeframe_duration_ms
            progress.total_expected = expected_candles
            
            # 페이지네이션을 통한 데이터 수집
            current_since = start_ts
            batch_limit = self.timeframe_config.get(timeframe, {}).get("records_per_batch", 1000)
            
            while current_since < end_ts:
                # CCXT fetchOHLCV 호출
                ohlcv_data = await self.fetch_historical_ohlcv(
                    symbol, timeframe, current_since, batch_limit
                )
                
                if not ohlcv_data:
                    logger.warning(f"No more data for {symbol}/{timeframe} at {current_since}")
                    break
                
                # 데이터베이스 삽입
                inserted, duplicates = await self.insert_candles_batch(
                    symbol, timeframe, ohlcv_data
                )
                
                progress.total_fetched += len(ohlcv_data)
                progress.total_inserted += inserted
                progress.total_duplicates += duplicates
                
                logger.info(f"{symbol}/{timeframe}: fetched {len(ohlcv_data)}, "
                           f"inserted {inserted}, duplicates {duplicates}")
                
                # 다음 배치의 시작점 설정
                if len(ohlcv_data) > 0:
                    last_candle_time = ohlcv_data[-1][0]
                    current_since = last_candle_time + timeframe_duration_ms
                else:
                    break
                
                # API 레이트 리미트 준수
                await asyncio.sleep(self.exchange.rateLimit / 1000)
            
            progress.end_time = datetime.now()
            progress.status = "completed"
            
            duration = (progress.end_time - progress.start_time).total_seconds()
            logger.info(f"Completed CCXT backfill {symbol}/{timeframe} in {duration:.1f}s: "
                       f"fetched {progress.total_fetched}, "
                       f"inserted {progress.total_inserted}")
            
        except Exception as e:
            progress.status = "failed"
            progress.end_time = datetime.now()
            logger.error(f"Failed to backfill {symbol}/{timeframe}: {e}")
        
        return progress
    
    async def backfill_symbol(self, symbol: str, timeframes: List[str], 
                             days_back: int = 30) -> Dict[str, BackfillProgress]:
        """심볼의 모든 타임프레임 백필"""
        logger.info(f"Starting CCXT backfill for symbol: {symbol}")
        
        results = {}
        for timeframe in timeframes:
            progress = await self.backfill_symbol_timeframe(symbol, timeframe, days_back)
            results[timeframe] = progress
            self.total_stats["timeframes_processed"] += 1
        
        self.total_stats["symbols_processed"] += 1
        return results
    
    def print_progress_report(self):
        """진행상황 리포트 출력"""
        print("\n" + "="*80)
        print("📈 CCXT HISTORICAL DATA BACKFILL PROGRESS")
        print("="*80)
        
        for key, progress in self.progress_tracker.items():
            status_emoji = {
                "pending": "⏳",
                "in_progress": "🔄", 
                "completed": "✅",
                "failed": "❌"
            }.get(progress.status, "❓")
            
            completion_rate = 0
            if progress.total_expected > 0:
                completion_rate = (progress.total_inserted / progress.total_expected) * 100
            
            print(f"{status_emoji} {progress.symbol}/{progress.timeframe}")
            print(f"    Expected: {progress.total_expected:,}")
            print(f"    Fetched: {progress.total_fetched:,}")
            print(f"    Inserted: {progress.total_inserted:,}")
            print(f"    Duplicates: {progress.total_duplicates:,}")
            print(f"    Completion: {completion_rate:.1f}%")
            if progress.start_time and progress.end_time:
                duration = (progress.end_time - progress.start_time).total_seconds()
                print(f"    Duration: {duration:.1f}s")
        
        print("\n📊 OVERALL STATISTICS")
        print("-"*40)
        for key, value in self.total_stats.items():
            print(f"{key.replace('_', ' ').title()}: {value:,}")
        print("="*80)
    
    async def run_backfill(self, symbols: List[str], timeframes: List[str], 
                          days_back: int = 30):
        """백필 프로세스 실행"""
        start_time = datetime.now()
        logger.info(f"Starting CCXT historical data backfill for {len(symbols)} symbols")
        logger.info(f"Symbols: {symbols}")
        logger.info(f"Timeframes: {timeframes}")
        logger.info(f"Period: {days_back} days back")
        
        try:
            # 병렬 처리를 위한 세마포어 (동시 2개 심볼)
            semaphore = asyncio.Semaphore(2)
            
            async def process_symbol_with_semaphore(symbol):
                async with semaphore:
                    return await self.backfill_symbol(symbol, timeframes, days_back)
            
            # 모든 심볼 병렬 처리
            tasks = [process_symbol_with_semaphore(symbol) for symbol in symbols]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            # 결과 처리
            for i, result in enumerate(results):
                if isinstance(result, Exception):
                    logger.error(f"Failed to process {symbols[i]}: {result}")
                    self.total_stats["total_errors"] += 1
            
            end_time = datetime.now()
            total_duration = (end_time - start_time).total_seconds()
            
            # 최종 리포트
            self.print_progress_report()
            
            print(f"\n🎉 CCXT BACKFILL COMPLETED in {total_duration:.1f} seconds")
            print(f"Total API calls: {self.total_stats['total_api_calls']:,}")
            print(f"Total data fetched: {self.total_stats['total_candles_fetched']:,}")
            print(f"Total data inserted: {self.total_stats['total_candles_inserted']:,}")
            
            # 성공률 계산
            total_operations = len(symbols) * len(timeframes)
            completed_operations = sum(1 for p in self.progress_tracker.values() 
                                     if p.status == "completed")
            success_rate = (completed_operations / total_operations) * 100 if total_operations > 0 else 0
            print(f"Success rate: {success_rate:.1f}%")
            
        except Exception as e:
            logger.error(f"CCXT backfill process failed: {e}")
            raise


async def main():
    """메인 함수"""
    parser = argparse.ArgumentParser(description="CCXT Historical Data Backfill Script")
    parser.add_argument("symbol", help="Symbol to backfill (e.g., BTC/USDT:USDT)")
    parser.add_argument("--timeframes", default="5m,15m,1h,4h,1d", 
                       help="Comma-separated timeframes")
    parser.add_argument("--days", type=int, default=30, 
                       help="Number of days to backfill (default: 30)")
    parser.add_argument("--exchange", default="okx", 
                       help="Exchange ID (default: okx)")
    parser.add_argument("--db-host", default=os.getenv('DB_HOST', 'localhost'), help="Database host")
    parser.add_argument("--db-port", type=int, default=int(os.getenv('DB_PORT', '5432')), help="Database port")
    parser.add_argument("--db-name", default=os.getenv('DB_NAME', 'trading_bot'), help="Database name")
    parser.add_argument("--db-user", default=os.getenv('DB_USER', 'trading_bot'), help="Database user")
    parser.add_argument("--db-password", default=os.getenv('DB_PASSWORD'), help="Database password")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be done")
    
    args = parser.parse_args()
    
    # 타임프레임 파싱
    timeframes = [tf.strip() for tf in args.timeframes.split(",")]
    
    # 심볼 목록
    symbols = [args.symbol.strip()]
    
    backfill = CCXTHistoricalBackfill(
        db_host=args.db_host,
        db_port=args.db_port,
        db_name=args.db_name,
        db_user=args.db_user,
        db_password=args.db_password or "trading_bot_password",
        exchange_id=args.exchange
    )
    
    try:
        # 초기화
        if not await backfill.initialize():
            logger.error("Failed to initialize CCXT backfill system")
            sys.exit(1)
        
        if args.dry_run:
            print("🔍 DRY RUN MODE - No data will be fetched or inserted")
            print(f"📈 Would backfill {args.symbol} for {args.days} days")
            print(f"📊 Timeframes: {timeframes}")
            print(f"🏪 Exchange: {args.exchange}")
            print(f"🗄️  Database: {args.db_host}:{args.db_port}/{args.db_name}")
            print(f"⏱️  Expected process: Initialize → CCXT fetch → Database insert → Report")
            print("✅ Dry run completed - CCXT script is ready for execution")
            return
        
        # 백필 실행
        await backfill.run_backfill(symbols, timeframes, args.days)
        
        logger.info("CCXT historical data backfill completed successfully")
        
    except KeyboardInterrupt:
        logger.info("CCXT backfill interrupted by user")
        sys.exit(1)
    except Exception as e:
        logger.error(f"CCXT backfill failed: {e}")
        sys.exit(1)
    finally:
        await backfill.close()


if __name__ == "__main__":
    asyncio.run(main())
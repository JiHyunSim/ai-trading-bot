#!/usr/bin/env python3
"""
CCXT 기반 일일 데이터 유지보수 스크립트
매일 지난 25시간 동안의 데이터 무결성 검사 및 자동 수정
"""

import asyncio
import sys
import argparse
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Set, Tuple
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
class MaintenanceStats:
    """유지보수 통계"""
    symbols_processed: int = 0
    timeframes_processed: int = 0
    gaps_found: int = 0
    gaps_filled: int = 0
    duplicates_removed: int = 0
    invalid_data_fixed: int = 0
    api_calls_made: int = 0
    total_errors: int = 0
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None


@dataclass
class DataGap:
    """데이터 갭 정보"""
    symbol: str
    timeframe: str
    start_ts: int
    end_ts: int
    expected_count: int
    missing_count: int


class CCXTDailyMaintenance:
    """CCXT 기반 일일 데이터 유지보수 시스템"""
    
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
        
        # 타임프레임별 간격 (분 단위)
        self.timeframe_intervals = {
            "1m": 1,
            "5m": 5,
            "15m": 15,
            "1h": 60,
            "4h": 240,
            "1d": 1440
        }
        
        # 검사 대상 타임프레임
        self.target_timeframes = ["5m", "15m", "1h", "4h", "1d"]
        
        # 통계
        self.stats = MaintenanceStats()
    
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
                max_size=10,
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
            
            logger.info(f"CCXT daily maintenance system initialized with {self.exchange_id}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to initialize CCXT maintenance system: {e}")
            return False
    
    async def close(self):
        """리소스 정리"""
        if self.exchange:
            await self.exchange.close()
        if self.db_pool:
            await self.db_pool.close()
    
    async def get_active_symbols(self, hours_back: int = 25) -> List[str]:
        """지난 N시간 내 데이터가 있는 활성 심볼 목록 조회"""
        try:
            cutoff_time = datetime.now() - timedelta(hours=hours_back)
            cutoff_ts = int(cutoff_time.timestamp() * 1000)
            
            async with self.db_pool.acquire() as conn:
                result = await conn.fetch("""
                    SELECT DISTINCT symbol
                    FROM trading.candlesticks
                    WHERE timestamp_ms >= $1
                    ORDER BY symbol
                """, cutoff_ts)
                
                symbols = [row['symbol'] for row in result]
                logger.info(f"Found {len(symbols)} active symbols in last {hours_back} hours")
                return symbols
                
        except Exception as e:
            logger.error(f"Failed to get active symbols: {e}")
            return []
    
    async def detect_data_gaps(self, symbol: str, timeframe: str, 
                             hours_back: int = 25) -> List[DataGap]:
        """데이터 갭 탐지"""
        try:
            # 검사 시간 범위 계산
            end_time = datetime.now()
            start_time = end_time - timedelta(hours=hours_back)
            
            end_ts = int(end_time.timestamp() * 1000)
            start_ts = int(start_time.timestamp() * 1000)
            
            # 타임프레임 간격 (밀리초)
            interval_minutes = self.timeframe_intervals.get(timeframe, 5)
            interval_ms = interval_minutes * 60 * 1000
            
            # 기존 데이터 조회
            async with self.db_pool.acquire() as conn:
                existing_data = await conn.fetch("""
                    SELECT timestamp_ms
                    FROM trading.candlesticks
                    WHERE symbol = $1 AND timeframe = $2
                    AND timestamp_ms BETWEEN $3 AND $4
                    ORDER BY timestamp_ms
                """, symbol, timeframe, start_ts, end_ts)
            
            existing_timestamps = {row['timestamp_ms'] for row in existing_data}
            
            # 예상 타임스탬프 생성
            expected_timestamps = set()
            current_ts = start_ts
            while current_ts <= end_ts:
                expected_timestamps.add(current_ts)
                current_ts += interval_ms
            
            # 누락된 타임스탬프 찾기
            missing_timestamps = expected_timestamps - existing_timestamps
            
            if not missing_timestamps:
                return []
            
            # 연속된 갭을 그룹화
            gaps = []
            sorted_missing = sorted(missing_timestamps)
            
            if sorted_missing:
                gap_start = sorted_missing[0]
                gap_end = sorted_missing[0]
                
                for i in range(1, len(sorted_missing)):
                    if sorted_missing[i] == gap_end + interval_ms:
                        gap_end = sorted_missing[i]
                    else:
                        # 갭 완료
                        missing_count = (gap_end - gap_start) // interval_ms + 1
                        gaps.append(DataGap(
                            symbol=symbol,
                            timeframe=timeframe,
                            start_ts=gap_start,
                            end_ts=gap_end,
                            expected_count=len(expected_timestamps),
                            missing_count=missing_count
                        ))
                        gap_start = sorted_missing[i]
                        gap_end = sorted_missing[i]
                
                # 마지막 갭 추가
                missing_count = (gap_end - gap_start) // interval_ms + 1
                gaps.append(DataGap(
                    symbol=symbol,
                    timeframe=timeframe,
                    start_ts=gap_start,
                    end_ts=gap_end,
                    expected_count=len(expected_timestamps),
                    missing_count=missing_count
                ))
            
            if gaps:
                total_missing = sum(gap.missing_count for gap in gaps)
                logger.info(f"Found {len(gaps)} gaps for {symbol}/{timeframe} "
                           f"(total missing: {total_missing})")
            
            return gaps
            
        except Exception as e:
            logger.error(f"Failed to detect gaps for {symbol}/{timeframe}: {e}")
            return []
    
    async def fill_data_gap(self, gap: DataGap) -> int:
        """데이터 갭 채우기"""
        try:
            logger.info(f"Filling gap for {gap.symbol}/{gap.timeframe}: "
                       f"{datetime.fromtimestamp(gap.start_ts/1000)} to "
                       f"{datetime.fromtimestamp(gap.end_ts/1000)}")
            
            # CCXT를 통해 누락 데이터 조회
            if not self.exchange.has['fetchOHLCV']:
                logger.error(f"Exchange {self.exchange_id} does not support fetchOHLCV")
                return 0
            
            # 약간 더 넓은 범위로 데이터 조회 (경계 데이터 확보)
            interval_ms = self.timeframe_intervals.get(gap.timeframe, 5) * 60 * 1000
            fetch_start = gap.start_ts - interval_ms
            fetch_end = gap.end_ts + interval_ms
            
            ohlcv_data = await self.exchange.fetch_ohlcv(
                symbol=gap.symbol,
                timeframe=gap.timeframe,
                since=fetch_start,
                limit=1000
            )
            
            self.stats.api_calls_made += 1
            
            if not ohlcv_data:
                logger.warning(f"No data received from exchange for {gap.symbol}/{gap.timeframe}")
                return 0
            
            # 갭 범위 내의 데이터만 필터링
            gap_data = [
                candle for candle in ohlcv_data
                if gap.start_ts <= candle[0] <= gap.end_ts
            ]
            
            if not gap_data:
                logger.warning(f"No data in gap range for {gap.symbol}/{gap.timeframe}")
                return 0
            
            # 데이터베이스에 삽입
            inserted_count = 0
            async with self.db_pool.acquire() as conn:
                async with conn.transaction():
                    for candle in gap_data:
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
                            """, gap.symbol, gap.timeframe, timestamp_ms,
                                 open_price, high_price, low_price,
                                 close_price, volume)
                            
                            if result == "INSERT 0 1":
                                inserted_count += 1
                                
                        except Exception as e:
                            logger.error(f"Failed to insert gap candle {candle}: {e}")
                            continue
            
            logger.info(f"Filled gap for {gap.symbol}/{gap.timeframe}: {inserted_count} candles inserted")
            return inserted_count
            
        except Exception as e:
            logger.error(f"Failed to fill gap for {gap.symbol}/{gap.timeframe}: {e}")
            self.stats.total_errors += 1
            return 0
    
    async def remove_duplicates(self, symbol: str, timeframe: str, 
                              hours_back: int = 25) -> int:
        """중복 데이터 제거"""
        try:
            cutoff_time = datetime.now() - timedelta(hours=hours_back)
            cutoff_ts = int(cutoff_time.timestamp() * 1000)
            
            async with self.db_pool.acquire() as conn:
                # 중복 데이터 조회
                duplicates = await conn.fetch("""
                    SELECT symbol, timeframe, timestamp_ms, COUNT(*) as count
                    FROM trading.candlesticks
                    WHERE symbol = $1 AND timeframe = $2 AND timestamp_ms >= $3
                    GROUP BY symbol, timeframe, timestamp_ms
                    HAVING COUNT(*) > 1
                """, symbol, timeframe, cutoff_ts)
                
                if not duplicates:
                    return 0
                
                removed_count = 0
                async with conn.transaction():
                    for dup in duplicates:
                        # 가장 오래된 레코드 하나만 남기고 나머지 삭제
                        result = await conn.execute("""
                            DELETE FROM trading.candlesticks
                            WHERE symbol = $1 AND timeframe = $2 AND timestamp_ms = $3
                            AND id NOT IN (
                                SELECT MIN(id) 
                                FROM trading.candlesticks 
                                WHERE symbol = $1 AND timeframe = $2 AND timestamp_ms = $3
                            )
                        """, dup['symbol'], dup['timeframe'], dup['timestamp_ms'])
                        
                        removed_count += int(result.split()[-1]) if result.split() else 0
                
                if removed_count > 0:
                    logger.info(f"Removed {removed_count} duplicate records for {symbol}/{timeframe}")
                
                return removed_count
                
        except Exception as e:
            logger.error(f"Failed to remove duplicates for {symbol}/{timeframe}: {e}")
            self.stats.total_errors += 1
            return 0
    
    async def fix_invalid_data(self, symbol: str, timeframe: str, 
                             hours_back: int = 25) -> int:
        """잘못된 데이터 수정"""
        try:
            cutoff_time = datetime.now() - timedelta(hours=hours_back)
            cutoff_ts = int(cutoff_time.timestamp() * 1000)
            
            async with self.db_pool.acquire() as conn:
                # 잘못된 데이터 조회 (가격이 0이거나 음수, 볼륨이 0 이하)
                invalid_data = await conn.fetch("""
                    SELECT id, symbol, timeframe, timestamp_ms
                    FROM trading.candlesticks
                    WHERE symbol = $1 AND timeframe = $2 AND timestamp_ms >= $3
                    AND (open_price <= 0 OR high_price <= 0 OR low_price <= 0 
                         OR close_price <= 0 OR volume <= 0
                         OR high_price < low_price
                         OR high_price < open_price
                         OR high_price < close_price
                         OR low_price > open_price
                         OR low_price > close_price)
                """, symbol, timeframe, cutoff_ts)
                
                if not invalid_data:
                    return 0
                
                fixed_count = 0
                async with conn.transaction():
                    for invalid in invalid_data:
                        # 잘못된 데이터 삭제 (재수집으로 대체)
                        await conn.execute("""
                            DELETE FROM trading.candlesticks
                            WHERE id = $1
                        """, invalid['id'])
                        fixed_count += 1
                
                if fixed_count > 0:
                    logger.info(f"Fixed {fixed_count} invalid records for {symbol}/{timeframe}")
                
                return fixed_count
                
        except Exception as e:
            logger.error(f"Failed to fix invalid data for {symbol}/{timeframe}: {e}")
            self.stats.total_errors += 1
            return 0
    
    async def check_data_integrity(self, symbol: str, timeframe: str, 
                                 hours_back: int = 25) -> Dict[str, int]:
        """특정 심볼/타임프레임의 데이터 무결성 검사 및 수정"""
        logger.info(f"Checking data integrity for {symbol}/{timeframe}")
        
        results = {
            "gaps_found": 0,
            "gaps_filled": 0,
            "duplicates_removed": 0,
            "invalid_data_fixed": 0
        }
        
        try:
            # 1. 중복 데이터 제거
            removed = await self.remove_duplicates(symbol, timeframe, hours_back)
            results["duplicates_removed"] = removed
            self.stats.duplicates_removed += removed
            
            # 2. 잘못된 데이터 수정
            fixed = await self.fix_invalid_data(symbol, timeframe, hours_back)
            results["invalid_data_fixed"] = fixed
            self.stats.invalid_data_fixed += fixed
            
            # 3. 데이터 갭 탐지 및 채우기
            gaps = await self.detect_data_gaps(symbol, timeframe, hours_back)
            results["gaps_found"] = len(gaps)
            self.stats.gaps_found += len(gaps)
            
            filled_count = 0
            for gap in gaps:
                filled = await self.fill_data_gap(gap)
                filled_count += filled
                
                # API 레이트 리미트 준수
                await asyncio.sleep(self.exchange.rateLimit / 1000)
            
            results["gaps_filled"] = filled_count
            self.stats.gaps_filled += filled_count
            
            logger.info(f"Integrity check completed for {symbol}/{timeframe}: "
                       f"gaps {results['gaps_found']}/{results['gaps_filled']}, "
                       f"duplicates {results['duplicates_removed']}, "
                       f"invalid {results['invalid_data_fixed']}")
            
        except Exception as e:
            logger.error(f"Failed integrity check for {symbol}/{timeframe}: {e}")
            self.stats.total_errors += 1
        
        return results
    
    async def run_maintenance(self, target_symbols: Optional[List[str]] = None, 
                            hours_back: int = 25, dry_run: bool = False):
        """일일 데이터 유지보수 실행"""
        self.stats.start_time = datetime.now()
        
        logger.info(f"Starting CCXT daily data maintenance")
        logger.info(f"Target period: last {hours_back} hours")
        logger.info(f"Dry run mode: {dry_run}")
        
        if dry_run:
            print("🔍 DRY RUN MODE - No actual changes will be made")
            print(f"📅 Would check data integrity for last {hours_back} hours")
            print(f"📊 Target timeframes: {self.target_timeframes}")
            print("✅ Dry run completed - maintenance script is ready")
            return
        
        try:
            # 대상 심볼 결정
            if target_symbols:
                symbols = target_symbols
                logger.info(f"Using provided symbols: {symbols}")
            else:
                symbols = await self.get_active_symbols(hours_back)
                logger.info(f"Auto-detected {len(symbols)} active symbols")
            
            if not symbols:
                logger.warning("No symbols to process")
                return
            
            # 각 심볼과 타임프레임에 대해 무결성 검사
            for symbol in symbols:
                logger.info(f"Processing symbol: {symbol}")
                
                for timeframe in self.target_timeframes:
                    await self.check_data_integrity(symbol, timeframe, hours_back)
                    self.stats.timeframes_processed += 1
                    
                    # 심볼 간 짧은 대기
                    await asyncio.sleep(0.1)
                
                self.stats.symbols_processed += 1
            
            self.stats.end_time = datetime.now()
            self.print_maintenance_report()
            
        except Exception as e:
            logger.error(f"Daily maintenance failed: {e}")
            self.stats.total_errors += 1
            raise
    
    def print_maintenance_report(self):
        """유지보수 리포트 출력"""
        duration = (self.stats.end_time - self.stats.start_time).total_seconds()
        
        print("\n" + "="*60)
        print("📊 CCXT DAILY DATA MAINTENANCE REPORT")
        print("="*60)
        print(f"🕒 Started: {self.stats.start_time}")
        print(f"🕒 Completed: {self.stats.end_time}")
        print(f"⏱️  Duration: {duration:.1f} seconds")
        print(f"📈 Symbols processed: {self.stats.symbols_processed}")
        print(f"📊 Timeframes processed: {self.stats.timeframes_processed}")
        print(f"🔍 Gaps found: {self.stats.gaps_found}")
        print(f"✅ Gaps filled: {self.stats.gaps_filled}")
        print(f"🔄 Duplicates removed: {self.stats.duplicates_removed}")
        print(f"🔧 Invalid data fixed: {self.stats.invalid_data_fixed}")
        print(f"📡 API calls made: {self.stats.api_calls_made}")
        if self.stats.total_errors > 0:
            print(f"❌ Total errors: {self.stats.total_errors}")
        print("="*60)


async def main():
    """메인 함수"""
    parser = argparse.ArgumentParser(description="CCXT Daily Data Maintenance Script")
    parser.add_argument("--symbols", help="Comma-separated symbols to process")
    parser.add_argument("--hours", type=int, default=25, 
                       help="Hours back to check (default: 25)")
    parser.add_argument("--exchange", default="okx", 
                       help="Exchange ID (default: okx)")
    parser.add_argument("--db-host", default=os.getenv('DB_HOST', 'localhost'), help="Database host")
    parser.add_argument("--db-port", type=int, default=int(os.getenv('DB_PORT', '5432')), help="Database port")
    parser.add_argument("--db-name", default=os.getenv('DB_NAME', 'trading_bot'), help="Database name")
    parser.add_argument("--db-user", default=os.getenv('DB_USER', 'trading_bot'), help="Database user")
    parser.add_argument("--db-password", default=os.getenv('DB_PASSWORD'), help="Database password")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be done")
    
    args = parser.parse_args()
    
    # 심볼 파싱
    target_symbols = None
    if args.symbols:
        target_symbols = [s.strip() for s in args.symbols.split(",")]
    
    maintenance = CCXTDailyMaintenance(
        db_host=args.db_host,
        db_port=args.db_port,
        db_name=args.db_name,
        db_user=args.db_user,
        db_password=args.db_password or "trading_bot_password",
        exchange_id=args.exchange
    )
    
    try:
        # 초기화
        if not await maintenance.initialize():
            logger.error("Failed to initialize CCXT maintenance system")
            sys.exit(1)
        
        # 유지보수 실행
        await maintenance.run_maintenance(target_symbols, args.hours, args.dry_run)
        
        logger.info("CCXT daily maintenance completed successfully")
        
    except KeyboardInterrupt:
        logger.info("CCXT maintenance interrupted by user")
        sys.exit(1)
    except Exception as e:
        logger.error(f"CCXT maintenance failed: {e}")
        sys.exit(1)
    finally:
        await maintenance.close()


if __name__ == "__main__":
    asyncio.run(main())
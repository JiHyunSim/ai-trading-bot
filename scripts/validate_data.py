#!/usr/bin/env python3
"""
AI Trading Bot - 데이터 무결성 검증 스크립트
"""

import asyncio
import sys
import argparse
from datetime import datetime, timedelta
from typing import Dict, List
import asyncpg
from dotenv import load_dotenv

# 환경 변수 로드
load_dotenv()

class DataValidator:
    """데이터 무결성 검증 시스템"""
    
    def __init__(self):
        self.db_pool = None
        
        # 타임프레임별 간격 (밀리초)
        self.timeframe_intervals = {
            "1m": 60 * 1000,
            "5m": 5 * 60 * 1000,
            "15m": 15 * 60 * 1000,
            "1h": 60 * 60 * 1000,
            "4h": 4 * 60 * 60 * 1000,
            "1d": 24 * 60 * 60 * 1000
        }
    
    async def initialize(self):
        """초기화"""
        self.db_pool = await asyncpg.create_pool(
            host='localhost',
            port=5432,
            database='trading_bot',
            user='trading_bot',
            password='trading_bot_password',
            min_size=2,
            max_size=5
        )
    
    async def close(self):
        """리소스 정리"""
        if self.db_pool:
            await self.db_pool.close()
    
    async def check_data_integrity(self, symbol: str, timeframes: List[str], hours_back: int = 24) -> Dict:
        """데이터 무결성 검증"""
        
        results = {
            'summary': {},
            'timeframes': {},
            'issues': []
        }
        
        async with self.db_pool.acquire() as conn:
            end_time = datetime.now()
            start_time = end_time - timedelta(hours=hours_back)
            
            start_ts = int(start_time.timestamp() * 1000)
            end_ts = int(end_time.timestamp() * 1000)
            
            print(f"🔍 Validating data integrity for {symbol}")
            print(f"📅 Period: {start_time.strftime('%Y-%m-%d %H:%M')} ~ {end_time.strftime('%Y-%m-%d %H:%M')}")
            print("=" * 60)
            
            total_records = 0
            total_expected = 0
            total_gaps = 0
            total_duplicates = 0
            
            for timeframe in timeframes:
                print(f"\n📊 Analyzing {timeframe}...")
                
                # 기본 통계
                stats = await conn.fetchrow("""
                    SELECT 
                        COUNT(*) as total_records,
                        COUNT(DISTINCT timestamp_ms) as unique_records,
                        MIN(timestamp_ms) as first_timestamp,
                        MAX(timestamp_ms) as last_timestamp,
                        MIN(created_at) as first_created,
                        MAX(created_at) as last_created
                    FROM trading.candlesticks 
                    WHERE symbol = $1 AND timeframe = $2 
                    AND timestamp_ms BETWEEN $3 AND $4
                """, symbol, timeframe, start_ts, end_ts)
                
                if not stats['total_records']:
                    print(f"  ❌ No data found")
                    results['timeframes'][timeframe] = {
                        'status': 'no_data',
                        'records': 0,
                        'expected': 0,
                        'gaps': 0,
                        'duplicates': 0
                    }
                    continue
                
                # 예상 레코드 수 계산
                interval_ms = self.timeframe_intervals[timeframe]
                expected_records = (end_ts - start_ts) // interval_ms
                
                # 중복 검사
                duplicates = stats['total_records'] - stats['unique_records']
                
                # 연속성 검사 (gaps)
                timestamps = await conn.fetch("""
                    SELECT timestamp_ms 
                    FROM trading.candlesticks 
                    WHERE symbol = $1 AND timeframe = $2 
                    AND timestamp_ms BETWEEN $3 AND $4
                    ORDER BY timestamp_ms
                """, symbol, timeframe, start_ts, end_ts)
                
                gaps = 0
                if len(timestamps) > 1:
                    for i in range(1, len(timestamps)):
                        expected_next = timestamps[i-1]['timestamp_ms'] + interval_ms
                        actual_next = timestamps[i]['timestamp_ms']
                        if actual_next > expected_next:
                            gap_size = (actual_next - expected_next) // interval_ms
                            gaps += gap_size
                
                # 데이터 품질 검사
                quality_issues = await conn.fetch("""
                    SELECT 
                        COUNT(*) FILTER (WHERE open_price <= 0) as invalid_open,
                        COUNT(*) FILTER (WHERE high_price <= 0) as invalid_high,
                        COUNT(*) FILTER (WHERE low_price <= 0) as invalid_low,
                        COUNT(*) FILTER (WHERE close_price <= 0) as invalid_close,
                        COUNT(*) FILTER (WHERE volume < 0) as invalid_volume,
                        COUNT(*) FILTER (WHERE high_price < low_price) as invalid_high_low,
                        COUNT(*) FILTER (WHERE high_price < open_price OR high_price < close_price) as invalid_high_range,
                        COUNT(*) FILTER (WHERE low_price > open_price OR low_price > close_price) as invalid_low_range
                    FROM trading.candlesticks 
                    WHERE symbol = $1 AND timeframe = $2 
                    AND timestamp_ms BETWEEN $3 AND $4
                """, symbol, timeframe, start_ts, end_ts)
                
                quality = quality_issues[0]
                
                # 결과 출력
                completeness = (stats['unique_records'] / expected_records * 100) if expected_records > 0 else 0
                
                print(f"  📈 Records: {stats['total_records']:,} (unique: {stats['unique_records']:,})")
                print(f"  📊 Expected: {expected_records:,} ({completeness:.1f}% complete)")
                print(f"  🔄 Duplicates: {duplicates:,}")
                print(f"  ⚠️  Gaps: {gaps:,}")
                
                if stats['first_timestamp'] and stats['last_timestamp']:
                    first_time = datetime.fromtimestamp(stats['first_timestamp'] / 1000)
                    last_time = datetime.fromtimestamp(stats['last_timestamp'] / 1000)
                    print(f"  📅 Data range: {first_time.strftime('%m-%d %H:%M')} ~ {last_time.strftime('%m-%d %H:%M')}")
                
                # 품질 이슈 체크
                quality_issues_found = []
                for field, count in quality.items():
                    if count > 0:
                        quality_issues_found.append(f"{field}: {count}")
                
                if quality_issues_found:
                    print(f"  ❌ Quality issues: {', '.join(quality_issues_found)}")
                else:
                    print(f"  ✅ Data quality: OK")
                
                # 상태 판정
                status = 'ok'
                if completeness < 95:
                    status = 'incomplete'
                if duplicates > 0:
                    status = 'duplicates'
                if quality_issues_found:
                    status = 'quality_issues'
                if stats['total_records'] == 0:
                    status = 'no_data'
                
                results['timeframes'][timeframe] = {
                    'status': status,
                    'records': stats['total_records'],
                    'unique_records': stats['unique_records'],
                    'expected': expected_records,
                    'completeness': completeness,
                    'gaps': gaps,
                    'duplicates': duplicates,
                    'quality_issues': dict(quality),
                    'first_timestamp': stats['first_timestamp'],
                    'last_timestamp': stats['last_timestamp']
                }
                
                total_records += stats['total_records']
                total_expected += expected_records
                total_gaps += gaps
                total_duplicates += duplicates
            
            # 전체 요약
            overall_completeness = (total_records / total_expected * 100) if total_expected > 0 else 0
            
            print(f"\n📊 Overall Summary")
            print("=" * 30)
            print(f"Total records: {total_records:,}")
            print(f"Expected records: {total_expected:,}")
            print(f"Completeness: {overall_completeness:.1f}%")
            print(f"Total duplicates: {total_duplicates:,}")
            print(f"Total gaps: {total_gaps:,}")
            
            results['summary'] = {
                'total_records': total_records,
                'total_expected': total_expected,
                'completeness': overall_completeness,
                'total_duplicates': total_duplicates,
                'total_gaps': total_gaps
            }
            
            # 권장사항
            print(f"\n💡 Recommendations")
            print("=" * 30)
            
            if total_duplicates > 0:
                print(f"🔧 Run deduplication: python scripts/deduplicate_data.py")
                results['issues'].append('duplicates_found')
            
            if total_gaps > 0:
                print(f"📥 Fill gaps: python scripts/fill_gaps.py --hours {hours_back}")
                results['issues'].append('gaps_found')
            
            if overall_completeness < 95:
                print(f"⚠️  Low completeness: Consider extending data collection period")
                results['issues'].append('low_completeness')
            
            if not results['issues']:
                print("✅ Data integrity is good!")
        
        return results

async def main():
    parser = argparse.ArgumentParser(description='AI Trading Bot Data Validation Tool')
    parser.add_argument('--symbol', default='BTC-USDT-SWAP', help='Trading symbol')
    parser.add_argument('--timeframes', default='5m,15m,1h,4h,1d', help='Comma-separated timeframes')
    parser.add_argument('--hours', type=int, default=24, help='Hours to validate')
    parser.add_argument('--json', action='store_true', help='Output results as JSON')
    
    args = parser.parse_args()
    
    timeframes = [tf.strip() for tf in args.timeframes.split(',')]
    
    validator = DataValidator()
    
    try:
        await validator.initialize()
        
        results = await validator.check_data_integrity(
            symbol=args.symbol,
            timeframes=timeframes,
            hours_back=args.hours
        )
        
        if args.json:
            import json
            print(json.dumps(results, indent=2))
        
        # 종료 코드 결정
        if results['issues']:
            return 1  # 이슈가 있음
        else:
            return 0  # 정상
    
    except Exception as e:
        print(f"❌ Error: {e}")
        return 1
    finally:
        await validator.close()

if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
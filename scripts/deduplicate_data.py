#!/usr/bin/env python3
"""
AI Trading Bot - 중복 데이터 제거 스크립트
"""

import asyncio
import asyncpg
import sys
from datetime import datetime

async def deduplicate_data():
    """중복 데이터 제거"""
    
    conn = await asyncpg.connect(
        host='localhost',
        port=5432,
        database='trading_bot',
        user='trading_bot',
        password='trading_bot_password'
    )
    
    try:
        print("🔧 중복 데이터 제거 시작...")
        print("=" * 50)
        
        # 중복 제거 전 통계
        before_count = await conn.fetchval("SELECT COUNT(*) FROM trading.candlesticks")
        print(f"📊 제거 전 총 레코드: {before_count:,}개")
        
        # 중복 제거 쿼리 실행
        print("\n🗑️  중복 레코드 제거 중...")
        
        # 임시 테이블 생성 - 유니크한 데이터만 보관
        await conn.execute("""
            CREATE TEMP TABLE temp_unique_candlesticks AS
            SELECT DISTINCT ON (symbol, timeframe, timestamp_ms)
                symbol,
                timeframe, 
                timestamp_ms,
                open_price,
                high_price,
                low_price,
                close_price,
                volume,
                MIN(created_at) as created_at  -- 가장 먼저 생성된 시간 유지
            FROM trading.candlesticks
            GROUP BY symbol, timeframe, timestamp_ms, open_price, high_price, low_price, close_price, volume
            ORDER BY symbol, timeframe, timestamp_ms, MIN(created_at)
        """)
        
        unique_count = await conn.fetchval("SELECT COUNT(*) FROM temp_unique_candlesticks")
        print(f"📈 유니크 레코드: {unique_count:,}개")
        
        # 기존 테이블 백업
        backup_table = f"candlesticks_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        print(f"💾 백업 테이블 생성: {backup_table}")
        
        await conn.execute(f"""
            CREATE TABLE trading.{backup_table} AS 
            SELECT * FROM trading.candlesticks
        """)
        
        # 원본 테이블 데이터 삭제
        print("🗑️  원본 테이블 데이터 삭제...")
        await conn.execute("DELETE FROM trading.candlesticks")
        
        # 유니크 데이터 삽입
        print("📥 유니크 데이터 삽입...")
        await conn.execute("""
            INSERT INTO trading.candlesticks 
            (symbol, timeframe, timestamp_ms, open_price, high_price, low_price, close_price, volume, created_at)
            SELECT symbol, timeframe, timestamp_ms, open_price, high_price, low_price, close_price, volume, created_at
            FROM temp_unique_candlesticks
            ORDER BY symbol, timeframe, timestamp_ms
        """)
        
        # 최종 통계
        after_count = await conn.fetchval("SELECT COUNT(*) FROM trading.candlesticks")
        removed_count = before_count - after_count
        
        print("\n✅ 중복 제거 완료!")
        print("=" * 50)
        print(f"📊 제거 전: {before_count:,}개")
        print(f"📊 제거 후: {after_count:,}개") 
        print(f"🗑️  제거됨: {removed_count:,}개 ({(removed_count/before_count*100):.1f}%)")
        print(f"💾 백업: trading.{backup_table}")
        
        # 타임프레임별 정리된 통계
        print("\n📈 정리된 데이터 통계:")
        stats = await conn.fetch("""
            SELECT symbol, timeframe, COUNT(*) as count,
                   MIN(timestamp_ms) as first_timestamp,
                   MAX(timestamp_ms) as last_timestamp
            FROM trading.candlesticks 
            GROUP BY symbol, timeframe
            ORDER BY symbol, timeframe
        """)
        
        for row in stats:
            first_time = datetime.fromtimestamp(row['first_timestamp']/1000)
            last_time = datetime.fromtimestamp(row['last_timestamp']/1000)
            print(f"  {row['symbol']} {row['timeframe']:>4}: {row['count']:>4}개 ({first_time.strftime('%m-%d %H:%M')} ~ {last_time.strftime('%m-%d %H:%M')})")
        
    except Exception as e:
        print(f"❌ 오류 발생: {e}")
        await conn.execute("ROLLBACK")
        return False
    finally:
        await conn.close()
    
    return True

if __name__ == "__main__":
    success = asyncio.run(deduplicate_data())
    sys.exit(0 if success else 1)
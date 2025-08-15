#!/usr/bin/env python3
"""
AI Trading Bot Integration Test
로컬 개발 환경에서 전체 시스템의 통합 테스트
"""

import asyncio
import sys
import os
from pathlib import Path

# 환경 변수 설정
os.environ['REDIS_PASSWORD'] = 'redis_password'
os.environ['DB_PASSWORD'] = 'trading_bot_password'
os.environ['DB_NAME'] = 'trading_bot'
os.environ['DB_USER'] = 'trading_bot'
os.environ['OKX_SANDBOX'] = 'true'

# 각 서비스 경로 추가
SERVICES_DIR = Path(__file__).parent / 'services'
sys.path.insert(0, str(SERVICES_DIR / 'gateway'))
sys.path.insert(0, str(SERVICES_DIR / 'collector'))
sys.path.insert(0, str(SERVICES_DIR / 'processor'))


async def test_processor():
    """Processor 서비스 테스트"""
    print("🔄 Processor 서비스 테스트...")
    
    try:
        from app.processors.batch_processor import BatchProcessor
        
        processor = BatchProcessor()
        await processor.initialize()
        
        print("  ✅ Processor 초기화 성공")
        print(f"  ✅ Redis 연결: {processor.redis_client is not None}")
        print(f"  ✅ DB 풀: {processor.db_pool is not None}")
        
        # 타임프레임 파싱 테스트
        test_timeframes = ['1m', '5m', '1H', '1D']
        for tf in test_timeframes:
            seconds = processor.parse_timeframe_seconds(tf)
            print(f"  ✅ {tf} → {seconds}초")
        
        # 정리
        if processor.db_pool:
            await processor.db_pool.close()
        if processor.redis_client:
            await processor.redis_client.close()
        
        print("  ✅ Processor 테스트 완료\n")
        return True
        
    except Exception as e:
        print(f"  ❌ Processor 테스트 실패: {e}")
        return False


async def test_gateway():
    """Gateway 서비스 테스트"""
    print("🌐 Gateway 서비스 테스트...")
    
    try:
        # 모듈 경로 재설정
        sys.path.clear()
        sys.path.extend(['.', str(SERVICES_DIR / 'gateway')])
        
        from app.core.config import get_settings
        from app.core.redis_client import get_redis_client, close_redis_client
        
        settings = get_settings()
        print(f"  ✅ 설정 로드: {settings.API_HOST}:{settings.API_PORT}")
        
        # Redis 연결 테스트
        redis_client = await get_redis_client()
        ping_result = await redis_client.ping()
        print(f"  ✅ Redis 연결: {ping_result}")
        
        await close_redis_client()
        print("  ✅ Gateway 테스트 완료\n")
        return True
        
    except Exception as e:
        print(f"  ❌ Gateway 테스트 실패: {e}")
        return False


async def test_collector():
    """Collector 서비스 테스트"""
    print("📡 Collector 서비스 테스트...")
    
    try:
        # 모듈 경로 재설정
        sys.path.clear()
        sys.path.extend(['.', str(SERVICES_DIR / 'collector')])
        
        from app.core.config import get_settings
        
        settings = get_settings()
        print(f"  ✅ 설정 로드: 샌드박스={settings.OKX_SANDBOX}")
        print(f"  ✅ WebSocket URL: {settings.websocket_url}")
        print(f"  ✅ Redis: {settings.REDIS_HOST}:{settings.REDIS_PORT}")
        
        # WebSocket 클라이언트 초기화 테스트 (실제 연결은 하지 않음)
        from app.websocket.okx_client import OKXWebSocketClient
        
        client = OKXWebSocketClient("BTC-USDT", "1m")
        print(f"  ✅ WebSocket 클라이언트 생성: {client.symbol}-{client.timeframe}")
        
        print("  ✅ Collector 테스트 완료\n")
        return True
        
    except Exception as e:
        print(f"  ❌ Collector 테스트 실패: {e}")
        return False


async def test_database_connection():
    """데이터베이스 연결 테스트"""
    print("🗄️ 데이터베이스 연결 테스트...")
    
    try:
        import asyncpg
        
        conn = await asyncpg.connect(
            host='localhost',
            port=5432,
            database='trading_bot',
            user='trading_bot',
            password='trading_bot_password'
        )
        
        # 스키마 확인
        tables = await conn.fetch("""
            SELECT table_name 
            FROM information_schema.tables 
            WHERE table_schema = 'trading'
            ORDER BY table_name;
        """)
        
        print("  ✅ 데이터베이스 연결 성공")
        print("  ✅ 생성된 테이블:")
        for row in tables:
            print(f"    - {row['table_name']}")
        
        await conn.close()
        print("  ✅ 데이터베이스 테스트 완료\n")
        return True
        
    except Exception as e:
        print(f"  ❌ 데이터베이스 테스트 실패: {e}")
        return False


async def test_redis_connection():
    """Redis 연결 테스트"""
    print("📦 Redis 연결 테스트...")
    
    try:
        import redis.asyncio as redis
        
        client = redis.Redis(
            host='localhost',
            port=6379,
            password='redis_password',
            decode_responses=True
        )
        
        # 연결 테스트
        await client.ping()
        print("  ✅ Redis 연결 성공")
        
        # 기본 작업 테스트
        await client.set('integration_test', 'success')
        value = await client.get('integration_test')
        print(f"  ✅ Redis 읽기/쓰기 테스트: {value}")
        
        await client.delete('integration_test')
        await client.close()
        print("  ✅ Redis 테스트 완료\n")
        return True
        
    except Exception as e:
        print(f"  ❌ Redis 테스트 실패: {e}")
        return False


async def main():
    """통합 테스트 메인 함수"""
    print("🚀 AI Trading Bot 통합 테스트 시작\n")
    
    tests = [
        ("데이터베이스 연결", test_database_connection),
        ("Redis 연결", test_redis_connection),
        ("Processor 서비스", test_processor),
        ("Gateway 서비스", test_gateway),
        ("Collector 서비스", test_collector),
    ]
    
    results = []
    
    for test_name, test_func in tests:
        try:
            result = await test_func()
            results.append((test_name, result))
        except Exception as e:
            print(f"❌ {test_name} 테스트 중 오류: {e}")
            results.append((test_name, False))
    
    # 결과 요약
    print("=" * 50)
    print("📊 통합 테스트 결과 요약:")
    print("=" * 50)
    
    passed = 0
    total = len(results)
    
    for test_name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{status} {test_name}")
        if result:
            passed += 1
    
    print(f"\n총 {total}개 테스트 중 {passed}개 통과 ({passed/total*100:.1f}%)")
    
    if passed == total:
        print("\n🎉 모든 통합 테스트가 성공적으로 완료되었습니다!")
        print("   로컬 개발 환경이 정상적으로 구성되었습니다.")
        return 0
    else:
        print(f"\n⚠️ {total-passed}개의 테스트가 실패했습니다.")
        print("   설정을 확인하고 다시 시도해주세요.")
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
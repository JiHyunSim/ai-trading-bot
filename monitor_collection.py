#!/usr/bin/env python3
"""
BTC-USDT 무기한 선물 실시간 데이터 수집 모니터링 도구
Redis 큐, 수집 상태, 데이터 처리율을 실시간으로 모니터링합니다.
"""

import asyncio
import json
import os
import sys
from datetime import datetime, timedelta
from typing import Dict, List, Optional

import aiohttp
import redis.asyncio as redis
import structlog

# 로깅 설정
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


class CollectionMonitor:
    """실시간 데이터 수집 모니터링"""
    
    def __init__(self, 
                 redis_host: str = "localhost", 
                 redis_port: int = 6379, 
                 redis_password: str = None,
                 gateway_host: str = "localhost", 
                 gateway_port: int = 8000):
        self.redis_host = redis_host
        self.redis_port = redis_port
        self.redis_password = redis_password
        self.gateway_host = gateway_host
        self.gateway_port = gateway_port
        self.redis_client = None
        
        # 모니터링 데이터
        self.previous_stats = {}
        self.start_time = datetime.now()
    
    async def connect_redis(self):
        """Redis 연결 초기화"""
        try:
            self.redis_client = redis.Redis(
                host=self.redis_host,
                port=self.redis_port,
                password=self.redis_password,
                decode_responses=True,
                retry_on_timeout=True
            )
            
            await self.redis_client.ping()
            logger.info("Redis connection established for monitoring")
            return True
            
        except Exception as e:
            logger.error(f"Failed to connect to Redis: {e}")
            return False
    
    async def get_queue_stats(self) -> Dict:
        """Redis 큐 통계 조회"""
        try:
            # 캔들 데이터 큐 길이
            queue_length = await self.redis_client.llen("candle_data_queue")
            
            # 처리 완료 카운터 (있는 경우)
            processed_count = await self.redis_client.get("processed_count") or "0"
            
            # 에러 카운터
            error_count = await self.redis_client.get("error_count") or "0"
            
            return {
                "queue_length": queue_length,
                "processed_count": int(processed_count),
                "error_count": int(error_count),
                "timestamp": datetime.now().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Failed to get queue stats: {e}")
            return {}
    
    async def get_collector_statuses(self) -> Dict:
        """모든 컬렉터 상태 조회"""
        try:
            collector_keys = await self.redis_client.keys("status:*")
            statuses = {}
            
            for key in collector_keys:
                symbol = key.split(":", 1)[1]
                status_data = await self.redis_client.get(key)
                
                if status_data:
                    try:
                        statuses[symbol] = json.loads(status_data)
                    except json.JSONDecodeError:
                        logger.warning(f"Invalid JSON in status key {key}")
            
            return statuses
            
        except Exception as e:
            logger.error(f"Failed to get collector statuses: {e}")
            return {}
    
    async def get_subscription_info(self) -> List[Dict]:
        """Gateway를 통한 구독 정보 조회"""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"http://{self.gateway_host}:{self.gateway_port}/api/v1/subscriptions",
                    timeout=aiohttp.ClientTimeout(total=5)
                ) as response:
                    
                    if response.status == 200:
                        result = await response.json()
                        return result.get("subscriptions", [])
                    else:
                        return []
                        
        except Exception as e:
            logger.debug(f"Failed to get subscription info: {e}")
            return []
    
    async def calculate_processing_rate(self, current_stats: Dict) -> Dict:
        """데이터 처리율 계산"""
        rates = {}
        current_time = datetime.now()
        
        if self.previous_stats:
            time_diff = (current_time - self.previous_stats.get("timestamp", current_time)).total_seconds()
            
            if time_diff > 0:
                # 처리율 계산 (messages per second)
                processed_diff = current_stats.get("processed_count", 0) - self.previous_stats.get("processed_count", 0)
                rates["processing_rate"] = processed_diff / time_diff
                
                # 에러율 계산
                error_diff = current_stats.get("error_count", 0) - self.previous_stats.get("error_count", 0)
                rates["error_rate"] = error_diff / time_diff
        
        # 이전 통계 업데이트
        self.previous_stats = current_stats.copy()
        self.previous_stats["timestamp"] = current_time
        
        return rates
    
    def format_uptime(self, seconds: int) -> str:
        """업타임을 읽기 좋은 형식으로 변환"""
        if seconds < 60:
            return f"{seconds}s"
        elif seconds < 3600:
            return f"{seconds//60}m {seconds%60}s"
        else:
            hours = seconds // 3600
            minutes = (seconds % 3600) // 60
            return f"{hours}h {minutes}m"
    
    def print_status_report(self, queue_stats: Dict, collector_statuses: Dict, 
                           subscriptions: List[Dict], rates: Dict):
        """상태 리포트 출력"""
        print("\n" + "="*80)
        print(f"🚀 BTC-USDT Collection Monitor - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print("="*80)
        
        # 전체 업타임
        monitor_uptime = (datetime.now() - self.start_time).total_seconds()
        print(f"📊 Monitor Uptime: {self.format_uptime(int(monitor_uptime))}")
        
        # Redis 큐 상태
        print("\n📦 REDIS QUEUE STATUS")
        print("-"*40)
        if queue_stats:
            print(f"Queue Length: {queue_stats.get('queue_length', 0):,} messages")
            print(f"Processed: {queue_stats.get('processed_count', 0):,} total")
            print(f"Errors: {queue_stats.get('error_count', 0):,} total")
            
            if rates:
                print(f"Processing Rate: {rates.get('processing_rate', 0):.2f} msg/sec")
                print(f"Error Rate: {rates.get('error_rate', 0):.2f} err/sec")
        else:
            print("❌ Unable to get queue statistics")
        
        # 구독 정보
        print("\n📡 ACTIVE SUBSCRIPTIONS")
        print("-"*40)
        if subscriptions:
            for sub in subscriptions:
                symbol = sub.get("symbol", "Unknown")
                timeframes = sub.get("timeframes", [])
                status = sub.get("status", "unknown")
                print(f"Symbol: {symbol}")
                print(f"  Status: {status}")
                print(f"  Timeframes: {', '.join(timeframes)}")
        else:
            print("❌ No active subscriptions found")
        
        # 컬렉터 상태
        print("\n🔌 COLLECTOR STATUS")
        print("-"*40)
        if collector_statuses:
            for symbol, status in collector_statuses.items():
                is_connected = status.get("is_connected", False)
                connection_status = "🟢 Connected" if is_connected else "🔴 Disconnected"
                
                print(f"Symbol: {symbol}")
                print(f"  Connection: {connection_status}")
                print(f"  Messages: {status.get('message_count', 0):,}")
                print(f"  Errors: {status.get('error_count', 0):,}")
                print(f"  Reconnects: {status.get('reconnect_count', 0)}")
                
                uptime = status.get('uptime_seconds', 0)
                print(f"  Uptime: {self.format_uptime(uptime)}")
                
                channels = status.get('subscribed_channels', [])
                print(f"  Channels: {', '.join(channels) if channels else 'None'}")
        else:
            print("❌ No collector status information available")
        
        # 시스템 건강성 점수
        health_score = self.calculate_health_score(queue_stats, collector_statuses, subscriptions)
        health_emoji = "🟢" if health_score >= 80 else "🟡" if health_score >= 60 else "🔴"
        print(f"\n{health_emoji} SYSTEM HEALTH: {health_score}%")
        
        print("="*80)
    
    def calculate_health_score(self, queue_stats: Dict, collector_statuses: Dict, 
                              subscriptions: List[Dict]) -> int:
        """시스템 건강성 점수 계산 (0-100)"""
        score = 0
        
        # Redis 연결 상태 (20점)
        if queue_stats:
            score += 20
        
        # 활성 구독 존재 (20점)
        if subscriptions:
            score += 20
        
        # 컬렉터 연결 상태 (40점)
        if collector_statuses:
            connected_collectors = sum(1 for status in collector_statuses.values() 
                                     if status.get("is_connected", False))
            total_collectors = len(collector_statuses)
            if total_collectors > 0:
                score += int(40 * (connected_collectors / total_collectors))
        
        # 큐 길이 적정성 (20점)
        if queue_stats:
            queue_length = queue_stats.get("queue_length", 0)
            if queue_length < 1000:  # 1000개 미만이면 양호
                score += 20
            elif queue_length < 5000:  # 5000개 미만이면 보통
                score += 10
            # 5000개 이상이면 0점
        
        return min(score, 100)
    
    async def monitor_loop(self, refresh_interval: int = 10):
        """모니터링 루프"""
        logger.info(f"Starting real-time monitoring (refresh every {refresh_interval}s)")
        print("Press Ctrl+C to stop monitoring")
        
        while True:
            try:
                # 데이터 수집
                queue_stats = await self.get_queue_stats()
                collector_statuses = await self.get_collector_statuses()
                subscriptions = await self.get_subscription_info()
                rates = await self.calculate_processing_rate(queue_stats)
                
                # 상태 리포트 출력
                self.print_status_report(queue_stats, collector_statuses, subscriptions, rates)
                
                # 다음 업데이트까지 대기
                await asyncio.sleep(refresh_interval)
                
            except KeyboardInterrupt:
                logger.info("Monitoring stopped by user")
                break
            except Exception as e:
                logger.error(f"Error in monitoring loop: {e}")
                await asyncio.sleep(refresh_interval)
    
    async def close(self):
        """리소스 정리"""
        if self.redis_client:
            await self.redis_client.close()


async def main():
    """메인 함수"""
    import argparse
    
    parser = argparse.ArgumentParser(description="Monitor BTC-USDT data collection")
    parser.add_argument("--redis-host", default="localhost", help="Redis host (default: localhost)")
    parser.add_argument("--redis-port", type=int, default=6379, help="Redis port (default: 6379)")
    parser.add_argument("--redis-password", help="Redis password")
    parser.add_argument("--gateway-host", default="localhost", help="Gateway host (default: localhost)")
    parser.add_argument("--gateway-port", type=int, default=8000, help="Gateway port (default: 8000)")
    parser.add_argument("--refresh", type=int, default=10, help="Refresh interval in seconds (default: 10)")
    
    args = parser.parse_args()
    
    # 환경 변수에서 Redis 비밀번호 가져오기
    redis_password = args.redis_password or os.getenv("REDIS_PASSWORD")
    
    monitor = CollectionMonitor(
        redis_host=args.redis_host,
        redis_port=args.redis_port,
        redis_password=redis_password,
        gateway_host=args.gateway_host,
        gateway_port=args.gateway_port
    )
    
    try:
        # Redis 연결
        if not await monitor.connect_redis():
            logger.error("Failed to connect to Redis. Please check the connection settings.")
            sys.exit(1)
        
        # 모니터링 시작
        await monitor.monitor_loop(args.refresh)
        
    except KeyboardInterrupt:
        logger.info("Monitoring interrupted by user")
    except Exception as e:
        logger.error(f"Monitoring failed: {e}")
        sys.exit(1)
    finally:
        await monitor.close()


if __name__ == "__main__":
    asyncio.run(main())